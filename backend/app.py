"""Pharmatool API — FastAPI backend that reuses the existing Python engine.

The heavy lifting (data prep, market sizing, DCI matching, opportunity scoring)
stays in `market_engine.py` + `analytics.py`. This module loads the prepared
data once at startup, precomputes the recommendation table, and exposes a clean
JSON API consumed by the Next.js frontend.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from functools import lru_cache
from datetime import date, datetime
from pathlib import Path
from typing import Any, List, Optional

import numpy as np
import pandas as pd

# Make the repo root (market_engine.py) and this folder (analytics.py) importable
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for _p in (str(ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import market_engine as me
from market_engine import (
    CONFIG,
    SRC_IQVIA,
    SRC_PCH,
    build_opportunity_table,
    build_option_universe,
    facet_filter,
    filter_iqvia,
    filter_nomenclature,
    filter_pch,
    get_nomenclature_dci_options,
    iqvia_class_breakdown,
    iqvia_total_market,
    compute_hhi,
    hhi_label,
    load_prepared_data,
    nomenclature_dci_dates,
    nomenclature_origin_for_dci,
    parse_smart_query,
    price_for_dci,
    safe_unique,
)
import analytics

# ------------------------------------------------------------
# JSON-safe serialization for pandas / numpy values
# ------------------------------------------------------------

def _clean(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(v, float):
        return None if (math.isnan(v) or math.isinf(v)) else v
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, pd.Timestamp):
        return None if pd.isna(v) else v.date().isoformat()
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    try:
        if v is pd.NaT:
            return None
    except Exception:
        pass
    return v


def records(df: Optional[pd.DataFrame], cols: Optional[List[str]] = None) -> List[dict]:
    if df is None or len(df) == 0:
        return []
    d = df[[c for c in cols if c in df.columns]] if cols else df
    d = d.replace([np.inf, -np.inf], np.nan)
    return [{k: _clean(val) for k, val in row.items()} for row in d.to_dict(orient="records")]


def num(v: Any, default: float = 0.0) -> float:
    try:
        f = float(v)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except Exception:
        return default


# ------------------------------------------------------------
# Load + precompute once at startup
# ------------------------------------------------------------

class _State:
    data: dict = {}
    recs: pd.DataFrame = pd.DataFrame()
    dci_dates: pd.DataFrame = pd.DataFrame()
    ready: bool = False


S = _State()


# Recommendations are expensive to compute (~20s: DCI matching + scoring over the
# whole market). We cache the result to Parquet, keyed by the source-file signature,
# so cold starts read it in ~1s instead of recomputing. The file is committed to the
# repo, so even a fresh Render container (ephemeral disk) boots fast.
REC_CACHE_VERSION = "r1"


def _rec_paths():
    return me.CACHE_DIR / "recommendations.parquet", me.CACHE_DIR / "recommendations.sig"


def _rec_signature() -> str:
    try:
        base = me._source_signature(None)
    except Exception:
        base = "nosig"
    return f"{REC_CACHE_VERSION}|{base}"


def _load_recommendations(nom, iqvia, pch):
    pq, sigp = _rec_paths()
    want = _rec_signature()
    if pq.exists() and sigp.exists():
        try:
            if sigp.read_text() == want:
                return pd.read_parquet(pq), True
        except Exception:
            pass
    recs, _ = analytics.build_recommendations(nom, iqvia, pch, [SRC_IQVIA, SRC_PCH], active_only=True)
    try:
        me.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        recs.to_parquet(pq, index=False)
        sigp.write_text(want)
    except Exception:
        pass  # read-only FS: degrade gracefully
    return recs, False


def _boot():
    t0 = time.time()
    S.data = load_prepared_data()
    nom, iqvia, pch = S.data["nom"], S.data["iqvia"], S.data["pch"]
    S.recs, cached = _load_recommendations(nom, iqvia, pch)
    S.dci_dates = nomenclature_dci_dates(nom, active_only=True)
    S.ready = True
    print(f"[pharmatool-api] ready in {time.time()-t0:.1f}s "
          f"({len(S.recs)} DCI scored · recommandations {'lues du cache' if cached else 'recalculées'})")


app = FastAPI(title="Pharmatool API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("FRONTEND_ORIGIN", "*").split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    _boot()


# ------------------------------------------------------------
# Meta / health
# ------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok" if S.ready else "loading", "version": app.version}


@app.get("/api/meta")
def meta():
    m = S.data.get("meta", {})
    return {
        "iqvia_file": m.get("iqvia_file"),
        "pch_file": m.get("pch_file"),
        "nom_file": m.get("nom_file"),
        "iqvia_year": m.get("iqvia_year"),
        "dzd_per_usd": CONFIG["DZD_PER_USD"],
        "n_dci_scored": int(len(S.recs)),
    }


# ------------------------------------------------------------
# Overview / dashboard
# ------------------------------------------------------------

@lru_cache(maxsize=1)
def _overview_payload():
    iqvia = S.data["iqvia"]
    iqvia_lab_raw = S.data["iqvia_lab_raw"]
    total = iqvia_total_market(iqvia_lab_raw, iqvia)
    classes = iqvia_class_breakdown(iqvia)
    labs = S.data.get("lab_landscape", pd.DataFrame())

    market_hhi = compute_hhi(labs["Market_Share"]) if not labs.empty and "Market_Share" in labs.columns else float("nan")

    material = classes[classes["Share"] >= 0.003].copy() if not classes.empty else pd.DataFrame()
    if not material.empty:
        material = material[material["Growth_PY"].notna()]
    growers = material.sort_values("Growth_PY", ascending=False).head(12) if not material.empty else pd.DataFrame()
    decliners = material.sort_values("Growth_PY", ascending=True).head(12) if not material.empty else pd.DataFrame()

    class_cols = ["THERAPEUTIC_CLASS", "Value_DZD", "Value_USD", "Share", "Growth_PY", "Players", "Products", "Volume"]
    lab_cols = ["Rank", "LABORATOIRE", "Value_DZD", "Value_USD", "Market_Share", "Growth_PY"]
    mom_cols = ["THERAPEUTIC_CLASS", "Growth_PY", "Share"]

    return {
        "kpis": {
            "value_dzd": num(total.get("value_dzd")),
            "value_usd": num(total.get("value_usd")),
            "growth_py": _clean(total.get("growth_py")),
            "volume": num(total.get("volume")),
            "n_labs": int(num(total.get("n_labs"))),
            "hhi": _clean(market_hhi),
            "hhi_label": hhi_label(market_hhi),
        },
        "classes": records(classes.head(40), class_cols),
        "labs": records(labs.head(40), lab_cols),
        "growers": records(growers, mom_cols),
        "decliners": records(decliners, mom_cols),
    }


@app.get("/api/overview")
def overview():
    return _overview_payload()


# ------------------------------------------------------------
# Radar
# ------------------------------------------------------------

_RADAR_COLS = ["DCI", "Last_registration", "Market value USD", "Market value DZD", "Growth_PY",
               "Concurrents", "Manufacturers", "Importers", "Sources found", "Top market products"]


@app.get("/api/radar/new-registrations")
def radar_new(months: int = Query(6, ge=1, le=60),
              min_usd: float = Query(500_000, ge=0),
              max_competitors: int = Query(2, ge=0, le=50)):
    recs, dates = S.recs, S.dci_dates
    if recs.empty or dates.empty:
        return {"kpis": _empty_kpis(), "rows": []}
    m = recs.merge(dates[["DCI", "Last_registration", "Next_expiry"]], on="DCI", how="left")
    m["Concurrents"] = (pd.to_numeric(m.get("Manufacturers", 0), errors="coerce").fillna(0)
                        + pd.to_numeric(m.get("Importers", 0), errors="coerce").fillna(0))
    cutoff = pd.Timestamp.now() - pd.DateOffset(months=months)
    sel = m[(pd.to_datetime(m["Last_registration"], errors="coerce") >= cutoff)
            & (m["Market value USD"] >= min_usd)
            & (m["Concurrents"] <= max_competitors)].copy()
    sel = sel.sort_values("Market value USD", ascending=False)
    return {
        "kpis": {
            "count": int(len(sel)),
            "market_sum_usd": num(sel["Market value USD"].sum()),
            "white_space": int((sel.get("Manufacturers", pd.Series(dtype=int)) == 0).sum()),
            "market_median_usd": num(sel["Market value USD"].median() if len(sel) else 0),
        },
        "rows": records(sel, _RADAR_COLS),
    }


@app.get("/api/radar/white-spaces")
def radar_white(min_usd: float = Query(300_000, ge=0)):
    recs = S.recs
    if recs.empty:
        return {"kpis": _empty_kpis(), "rows": []}
    sel = recs[(recs.get("Manufacturers", 1) == 0) & (recs["Market value USD"] >= min_usd)].copy()
    sel = sel.sort_values("Market value USD", ascending=False)
    cols = ["DCI", "Market value USD", "Market value DZD", "Growth_PY", "Importers",
            "Importer labs", "Sources found", "Top market products"]
    return {
        "kpis": {
            "count": int(len(sel)),
            "market_sum_usd": num(sel["Market value USD"].sum()),
            "with_import_demand": int((sel.get("Importers", pd.Series(dtype=int)) > 0).sum()),
            "market_median_usd": num(sel["Market value USD"].median() if len(sel) else 0),
        },
        "rows": records(sel, cols),
    }


@app.get("/api/radar/expirations")
def radar_expirations(validity: int = Query(5, ge=1, le=15),
                      horizon: int = Query(24, ge=1, le=60)):
    nom = S.data["nom"]
    if nom is None or nom.empty:
        return {"kpis": _empty_kpis(), "rows": []}
    x = nom.copy()
    if "SOURCE_NOMENCLATURE" in x.columns:
        x = x[x["SOURCE_NOMENCLATURE"].astype(str).str.upper().eq("ACTIVE")].copy()
    last = pd.to_datetime(x.get("DATE_ENR_FINAL"), errors="coerce")
    last = last.fillna(pd.to_datetime(x.get("DATE_ENR_INITIAL"), errors="coerce"))
    x["Echeance_estimee"] = last + pd.DateOffset(years=validity)
    now = pd.Timestamp.now()
    upper = now + pd.DateOffset(months=horizon)
    sel = x[(x["Echeance_estimee"].notna())
            & (x["Echeance_estimee"] >= now - pd.DateOffset(months=6))
            & (x["Echeance_estimee"] <= upper)].copy()
    sel = sel.sort_values("Echeance_estimee")
    sel = sel.rename(columns={
        "BRAND": "Produit", "LABORATOIRE": "Laboratoire", "PAYS": "Pays",
        "FORME": "Forme", "DOSAGE": "Dosage", "ORIGIN": "Origine",
        "DATE_ENR_FINAL": "Derniere_decision", "Echeance_estimee": "Echeance_estimee",
    })
    cols = ["DCI", "Produit", "Laboratoire", "Pays", "Origine", "Forme", "Dosage",
            "Derniere_decision", "Echeance_estimee"]
    return {
        "kpis": {
            "count": int(len(sel)),
            "n_dci": int(sel["DCI"].nunique()) if "DCI" in sel.columns and len(sel) else 0,
            "n_labs": int(sel["Laboratoire"].nunique()) if "Laboratoire" in sel.columns and len(sel) else 0,
            "imported": int((sel.get("Origine", pd.Series(dtype=str)) == "IMPORT").sum()),
        },
        "rows": records(sel, cols),
    }


def _empty_kpis():
    return {"count": 0, "market_sum_usd": 0, "white_space": 0, "market_median_usd": 0}


# ------------------------------------------------------------
# Strategic opportunities
# ------------------------------------------------------------

@app.get("/api/opportunities")
def opportunities(view: str = Query("eligible", regex="^(eligible|import_substitution|all)$"),
                  min_usd: float = Query(0, ge=0),
                  limit: int = Query(120, ge=1, le=500)):
    recs = S.recs
    if recs.empty:
        return {"kpis": {}, "rows": []}
    shown = recs.copy()
    if min_usd:
        shown = shown[shown["Market value USD"] >= min_usd]
    if view == "import_substitution" and "Import substitution" in shown.columns:
        shown = shown[shown["Import substitution"].eq(True)]
    elif view == "eligible" and "Eligible" in shown.columns:
        shown = shown[shown["Eligible"].eq(True)]
    shown = shown.head(limit)
    cols = ["DCI", "Opportunity score", "Recommendation", "Market bucket", "Market value USD",
            "Market value DZD", "Growth_PY", "Manufacturers", "Allowed manufacturers", "Importers",
            "Import substitution", "Eligible", "Sources found", "Manufacturer labs", "Importer labs",
            "Top market products"]
    return {
        "kpis": {
            "count": int(len(shown)),
            "market_sum_usd": num(shown.get("Market value USD", pd.Series(dtype=float)).sum()),
            "import_substitution": int(shown.get("Import substitution", pd.Series(dtype=bool)).sum()),
            "score_median": num(shown.get("Opportunity score", pd.Series(dtype=float)).median()),
        },
        "rows": records(shown, cols),
    }


# ------------------------------------------------------------
# DCI search + connected facets (shared by Pricing & Analysis)
# ------------------------------------------------------------

def _markets(markets: List[str]) -> List[str]:
    if not markets:
        return [SRC_IQVIA, SRC_PCH]
    out = []
    for m in markets:
        k = str(m).strip().lower()
        if k in ("iqvia", "ville", SRC_IQVIA.lower()):
            out.append(SRC_IQVIA)
        elif k in ("pch", "hosp", "hospital", SRC_PCH.lower()):
            out.append(SRC_PCH)
    return out or [SRC_IQVIA, SRC_PCH]


def _clean_list(xs: List[str]) -> List[str]:
    return [x.strip() for x in (xs or []) if str(x).strip()]


# The DCI fuzzy matching is the heavy part (~600ms) and depends only on the DCI(s)
# and chosen markets — not on the dosage/forme/lab filters. We memoize it so that
# tweaking a filter only re-runs the cheap apply_filters / facet_filter step.
@lru_cache(maxsize=64)
def _universe(dci_t: tuple, markets_t: tuple):
    return build_option_universe(", ".join(dci_t), list(markets_t),
                                 S.data["nom"], S.data["iqvia"], S.data["pch"])


@lru_cache(maxsize=64)
def _matched(dci_t: tuple, markets_t: tuple):
    nom, iqvia, pch = S.data["nom"], S.data["iqvia"], S.data["pch"]
    dci_list, mk = list(dci_t), list(markets_t)
    nom_b = filter_nomenclature(nom, dci_list)
    iq_b = filter_iqvia(iqvia, dci_list) if SRC_IQVIA in mk else pd.DataFrame()
    pch_b = filter_pch(pch, dci_list) if SRC_PCH in mk else pd.DataFrame()
    return nom_b, iq_b, pch_b


@app.get("/api/dci/options")
def dci_options(q: str = Query("", max_length=120)):
    """Autocomplete DCI names from the official Nomenclature."""
    return {"candidates": get_nomenclature_dci_options(S.data["nom"], q, limit=50)}


@app.get("/api/dci/facets")
def dci_facets(dci: List[str] = Query(default=[]),
               markets: List[str] = Query(default=[]),
               dosage: List[str] = Query(default=[]),
               forme: List[str] = Query(default=[]),
               lab: List[str] = Query(default=[]),
               statut: List[str] = Query(default=[])):
    """Connected filters: available dosage / forme / lab / statut options for the
    selected DCI(s), each computed against the other current selections."""
    nom, iqvia, pch = S.data["nom"], S.data["iqvia"], S.data["pch"]
    dci_list = _clean_list(dci)
    mk = _markets(markets)
    empty = {"dosage": [], "forme": [], "lab": [], "statut": [],
             "n_candidates": 0, "n_nomenclature": 0, "n_iqvia": 0, "n_pch": 0}
    if not dci_list:
        return empty
    universe = _universe(tuple(sorted(dci_list)), tuple(sorted(mk)))
    if universe is None or universe.empty:
        return empty
    dosage, forme, lab, statut = _clean_list(dosage), _clean_list(forme), _clean_list(lab), _clean_list(statut)
    # Dosage options: clean dosages from the official Nomenclature only — the IQVIA/PCH
    # "dosage" column is the raw product label and far too messy to pick from.
    uni_dose = universe[universe["source"] == "NOMENCLATURE"]
    if uni_dose.empty:
        uni_dose = universe
    dosage_opts = safe_unique(facet_filter(uni_dose, dosage=[], formes=forme, labs=lab, statuts=statut, markets=mk, ignore={"dosage"})["dosage"], 400)
    # Forme options: keep only recognized canonical forms (drop raw label leftovers).
    canon_forms = set(me.FORM_SYNONYMS.keys())
    forme_raw = safe_unique(facet_filter(universe, dosage=dosage, formes=[], labs=lab, statuts=statut, markets=mk, ignore={"forme"})["forme"], 400)
    forme_opts = [f for f in forme_raw if f in canon_forms]
    lab_opts = safe_unique(facet_filter(universe, dosage=dosage, formes=forme, labs=[], statuts=statut, markets=mk, ignore={"lab"})["lab"], 800)
    statut_opts = [x for x in safe_unique(facet_filter(universe, dosage=dosage, formes=forme, labs=lab, statuts=[], markets=mk, ignore={"statut"})["statut"], 80) if x]
    live = facet_filter(universe, dosage=dosage, formes=forme, labs=lab, statuts=statut, markets=mk)
    return {
        "dosage": dosage_opts,
        "forme": forme_opts,
        "lab": lab_opts,
        "statut": statut_opts,
        "n_candidates": int(len(live)),
        "n_nomenclature": int((live["source"] == "NOMENCLATURE").sum()) if not live.empty else 0,
        "n_iqvia": int((live["source"] == SRC_IQVIA).sum()) if not live.empty else 0,
        "n_pch": int((live["source"] == SRC_PCH).sum()) if not live.empty else 0,
    }


# ------------------------------------------------------------
# Pricing
# ------------------------------------------------------------

@app.get("/api/pricing/suggest")
def pricing_suggest(q: str = Query(..., min_length=1)):
    parsed = parse_smart_query(q, S.data["nom"])
    return {
        "dci_candidates": parsed.get("dci_candidates", []),
        "dosage": parsed.get("dosage", []),
        "forme": parsed.get("forme", []),
    }


def _stats(s):
    if not s:
        return None
    return {k: _clean(s.get(k)) for k in ("n", "avg_dzd", "avg_usd", "median", "min", "max")}


@app.get("/api/pricing")
def pricing(dci: List[str] = Query(default=[]),
            dosage: List[str] = Query(default=[]),
            forme: List[str] = Query(default=[]),
            lab: List[str] = Query(default=[]),
            markets: List[str] = Query(default=[])):
    iqvia, pch, nom = S.data["iqvia"], S.data["pch"], S.data["nom"]
    dci_list = _clean_list(dci)
    if not dci_list:
        raise HTTPException(status_code=400, detail="dci_required")
    mk = _markets(markets)
    res = price_for_dci(iqvia, pch, nom, dci_list,
                        _clean_list(dosage) or None, _clean_list(forme) or None,
                        _clean_list(lab) or None, mk)
    ville_cols = ["BRAND", "PRESENTATION", "LABORATOIRE", "MARKET_VOLUME", "MARKET_VALUE_DZD", "Prix_boite_DZD", "GROWTH_PY"]
    hosp_cols = ["PRODUCT_FULL", "LABORATOIRE", "QTE", "Prix_unitaire_DZD", "MARKET_VALUE_DZD", "DEVISE", "DATESTOCKAGE"]
    return {
        "dci": dci_list,
        "ville": _stats(res.get("ville")),
        "ville_rows": records(res.get("ville_rows"), ville_cols),
        "hospital": _stats(res.get("hospital")),
        "hospital_rows": records(res.get("hospital_rows"), hosp_cols),
    }


# ------------------------------------------------------------
# DCI full market analysis — competitive landscape + chart data
# ------------------------------------------------------------

@app.get("/api/dci/analysis")
def dci_analysis(dci: List[str] = Query(default=[]),
                 markets: List[str] = Query(default=[]),
                 dosage: List[str] = Query(default=[]),
                 forme: List[str] = Query(default=[]),
                 lab: List[str] = Query(default=[]),
                 statut: List[str] = Query(default=[])):
    nom, iqvia, pch = S.data["nom"], S.data["iqvia"], S.data["pch"]
    dci_list = _clean_list(dci)
    if not dci_list:
        raise HTTPException(status_code=400, detail="dci_required")
    mk = _markets(markets)
    dosage_l = _clean_list(dosage) or None
    forme_l = _clean_list(forme) or None
    lab_l = _clean_list(lab) or None
    statut_l = _clean_list(statut) or None

    nom_b, iq_b, pch_b = _matched(tuple(sorted(dci_list)), tuple(sorted(mk)))
    nom_m = me.apply_filters(nom_b, dosage_l, forme_l, lab_l, statut_l, "nom") if nom_b is not None and not nom_b.empty else nom_b
    iq_m = me.apply_filters(iq_b, dosage_l, forme_l, lab_l, None, "iqvia") if iq_b is not None and not iq_b.empty else iq_b
    pch_m = me.apply_filters(pch_b, dosage_l, forme_l, lab_l, None, "pch") if pch_b is not None and not pch_b.empty else pch_b
    main, market_detail, _ = build_opportunity_table(nom_m, iq_m, pch_m)

    if market_detail is None or market_detail.empty:
        return {"empty": True, "dci": dci_list}

    # Competitive landscape: one row per laboratory (city + hospital combined)
    by_lab = market_detail.groupby("LABORATOIRE", dropna=False).agg(
        Value_DZD=("Market_Size_Value_DZD", "sum"),
        Volume=("Market_Size_Volume", "sum"),
    ).reset_index()
    gr = market_detail.groupby("LABORATOIRE", dropna=False).apply(
        lambda d: me.weighted_growth_py(d["Market_Size_Value_DZD"], d.get("Growth_PY", pd.Series(dtype=float)))
    ).rename("Growth_PY").reset_index()
    by_lab = by_lab.merge(gr, on="LABORATOIRE", how="left")
    total = by_lab["Value_DZD"].sum()
    by_lab["Share"] = np.where(total > 0, by_lab["Value_DZD"] / total, np.nan)
    by_lab["Value_USD"] = by_lab["Value_DZD"] / CONFIG["DZD_PER_USD"]
    by_lab = by_lab.sort_values("Value_DZD", ascending=False).reset_index(drop=True)

    origin = nomenclature_origin_for_dci(nom, dci_list)
    hhi = compute_hhi(by_lab["Share"])
    overall_growth = me.weighted_growth_py(market_detail["Market_Size_Value_DZD"],
                                           market_detail.get("Growth_PY", pd.Series(dtype=float)))
    n_players = int(market_detail["LABORATOIRE"].replace("", np.nan).dropna().nunique())

    def _clean_market(df):
        if df is None or df.empty:
            return pd.DataFrame()
        x = df.rename(columns={
            "_QUERY_DCI": "DCI", "PRODUCT_FULL": "Produit", "LABORATOIRE": "Laboratoire",
            "Therapeutic_Class": "Classe", "Market_Size_Volume": "Volume",
            "Market_Size_Value_DZD": "Valeur DZD", "Market_Size_Value_USD": "Valeur USD",
            "Growth_PY": "Croissance",
        })
        cols = [c for c in ["DCI", "Produit", "Laboratoire", "Classe", "Volume", "Valeur DZD", "Valeur USD", "Croissance"] if c in x.columns]
        x = x[cols]
        return x.sort_values("Valeur DZD", ascending=False) if "Valeur DZD" in x.columns else x

    ville = _clean_market(market_detail[market_detail["SOURCE_MARKET"].eq(SRC_IQVIA)])
    hosp = _clean_market(market_detail[market_detail["SOURCE_MARKET"].eq(SRC_PCH)])

    comp_cols = ["LABORATOIRE", "Value_DZD", "Value_USD", "Volume", "Share", "Growth_PY"]
    market_cols = ["DCI", "Produit", "Laboratoire", "Classe", "Volume", "Valeur DZD", "Valeur USD", "Croissance"]
    return {
        "empty": False,
        "dci": dci_list,
        "kpis": {
            "value_dzd": num(main["Valeur DZD"].sum()) if "Valeur DZD" in main else 0,
            "value_usd": num(main["Valeur USD"].sum()) if "Valeur USD" in main else 0,
            "volume": num(main["Volume"].sum()) if "Volume" in main else 0,
            "growth": _clean(overall_growth),
            "n_competitors": n_players,
            "hhi": _clean(hhi),
            "hhi_label": hhi_label(hhi),
        },
        "origin": {
            "local_labs": origin["local_labs"],
            "import_labs": origin["import_labs"],
            "n_local": len(origin["local_labs"]),
            "n_import": len(origin["import_labs"]),
        },
        "competitors": records(by_lab, comp_cols),
        "ville_rows": records(ville, market_cols),
        "hospital_rows": records(hosp, market_cols),
        "n_ville": int(len(ville)),
        "n_hosp": int(len(hosp)),
    }


# ------------------------------------------------------------
# AI Assistant — natural-language → structured filter (Claude Haiku)
# ------------------------------------------------------------

LLM_MODEL = "claude-haiku-4-5"

_SYSTEM = """Tu convertis une question en français sur le marché pharmaceutique algérien en un FILTRE JSON.
Réponds UNIQUEMENT par un objet JSON valide, sans texte autour, avec ces clés (toutes optionnelles) :
- "min_market_usd": nombre (marché minimum en USD)
- "max_market_usd": nombre
- "min_growth": nombre décimal (ex: 0.10 pour +10%)
- "max_growth": nombre décimal
- "max_manufacturers": entier (nombre max de fabricants locaux)
- "min_manufacturers": entier
- "min_importers": entier
- "import_substitution_only": booléen (marchés sans fabricant local mais avec importateurs)
- "eligible_only": booléen
- "sort_by": une valeur parmi "market", "growth", "score"
- "top_n": entier (défaut 25)
N'invente pas de clés. Convertis les pourcentages en décimal."""


class AssistantQuery(BaseModel):
    question: str


def _ask_llm(question: str) -> dict:
    import anthropic
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise HTTPException(status_code=503, detail="no_key")
    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model=LLM_MODEL, max_tokens=400, system=_SYSTEM,
        messages=[{"role": "user", "content": question}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    if "```" in text:
        text = text.split("```")[1].replace("json", "", 1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return {}
    return json.loads(text[start:end + 1])


def _apply_filters(recs: pd.DataFrame, f: dict) -> pd.DataFrame:
    x = recs.copy()
    if x.empty:
        return x
    g = lambda k: f.get(k)
    if g("min_market_usd") is not None:
        x = x[x["Market value USD"] >= float(g("min_market_usd"))]
    if g("max_market_usd") is not None:
        x = x[x["Market value USD"] <= float(g("max_market_usd"))]
    if g("min_growth") is not None:
        x = x[pd.to_numeric(x["Growth_PY"], errors="coerce").fillna(-99) >= float(g("min_growth"))]
    if g("max_growth") is not None:
        x = x[pd.to_numeric(x["Growth_PY"], errors="coerce").fillna(99) <= float(g("max_growth"))]
    if g("max_manufacturers") is not None:
        x = x[x["Manufacturers"] <= int(g("max_manufacturers"))]
    if g("min_manufacturers") is not None:
        x = x[x["Manufacturers"] >= int(g("min_manufacturers"))]
    if g("min_importers") is not None:
        x = x[x["Importers"] >= int(g("min_importers"))]
    if g("import_substitution_only"):
        x = x[(x["Manufacturers"] == 0) & (x["Importers"] > 0)]
    if g("eligible_only") and "Eligible" in x.columns:
        x = x[x["Eligible"].eq(True)]
    sort_map = {"market": "Market value USD", "growth": "Growth_PY", "score": "Opportunity score"}
    sort_col = sort_map.get(str(g("sort_by") or "market"), "Market value USD")
    x = x.sort_values(sort_col, ascending=False)
    top_n = int(g("top_n") or 25)
    return x.head(max(1, min(top_n, 200)))


@app.post("/api/assistant")
def assistant(body: AssistantQuery):
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="empty_question")
    try:
        filt = _ask_llm(body.question.strip())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"llm_error: {e}")
    res = _apply_filters(S.recs, filt)
    cols = ["DCI", "Market value USD", "Growth_PY", "Manufacturers", "Importers",
            "Opportunity score", "Recommendation", "Top market products"]
    return {
        "filter": filt,
        "kpis": {
            "count": int(len(res)),
            "market_sum_usd": num(res["Market value USD"].sum()) if len(res) else 0,
            "white_space": int((res["Manufacturers"] == 0).sum()) if len(res) else 0,
            "growth_median": _clean(pd.to_numeric(res["Growth_PY"], errors="coerce").median()) if len(res) else None,
        },
        "rows": records(res, cols),
    }
