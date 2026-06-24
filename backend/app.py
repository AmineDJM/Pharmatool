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
    iqvia_class_breakdown,
    iqvia_total_market,
    compute_hhi,
    hhi_label,
    load_prepared_data,
    nomenclature_dci_dates,
    parse_smart_query,
    price_for_dci,
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


def _boot():
    t0 = time.time()
    S.data = load_prepared_data()
    nom, iqvia, pch = S.data["nom"], S.data["iqvia"], S.data["pch"]
    S.recs, _ = analytics.build_recommendations(nom, iqvia, pch, [SRC_IQVIA, SRC_PCH], active_only=True)
    S.dci_dates = nomenclature_dci_dates(nom, active_only=True)
    S.ready = True
    print(f"[pharmatool-api] data + recommendations ready in {time.time()-t0:.1f}s "
          f"({len(S.recs)} DCI scored)")


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

@app.get("/api/overview")
def overview():
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


@app.get("/api/pricing")
def pricing(dci: str = Query(..., min_length=1),
            dosage: Optional[str] = None,
            forme: Optional[str] = None):
    iqvia, pch, nom = S.data["iqvia"], S.data["pch"], S.data["nom"]
    dosage_list = [d for d in (dosage.split(",") if dosage else []) if d.strip()] or None
    forme_list = [f for f in (forme.split(",") if forme else []) if f.strip()] or None
    res = price_for_dci(iqvia, pch, nom, [dci], dosage_list, forme_list, None, [SRC_IQVIA, SRC_PCH])

    ville_cols = ["BRAND", "PRESENTATION", "LABORATOIRE", "MARKET_VOLUME", "MARKET_VALUE_DZD", "Prix_boite_DZD", "GROWTH_PY"]
    hosp_cols = ["PRODUCT_FULL", "LABORATOIRE", "QTE", "Prix_unitaire_DZD", "MARKET_VALUE_DZD", "DEVISE", "DATESTOCKAGE"]
    return {
        "dci": dci,
        "ville": _stats(res.get("ville")),
        "ville_rows": records(res.get("ville_rows"), ville_cols),
        "hospital": _stats(res.get("hospital")),
        "hospital_rows": records(res.get("hospital_rows"), hosp_cols),
    }


def _stats(s):
    if not s:
        return None
    return {k: _clean(s.get(k)) for k in ("n", "avg_dzd", "avg_usd", "median", "min", "max")}


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
