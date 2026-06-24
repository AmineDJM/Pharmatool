# ============================================================
# ALGERIA PHARMA MARKET INTELLIGENCE — DATA & ANALYTICS ENGINE
# ------------------------------------------------------------
# Responsibilities:
#   * Auto-discover and load the latest IQVIA / PCH / Nomenclature files
#   * Dynamic IQVIA period detection (MAT / YTD / Month, any year)
#   * Pharma-safe DCI matching (molecule-aware, no false suffix matches)
#   * Correct market sizing (de-duplicated, reconciled to IQVIA totals)
#   * Competitive analytics: market share, growth vs PY, concentration (HHI),
#     local manufacturing vs import (from the official Nomenclature)
# ============================================================

import re
import math
import unicodedata
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from rapidfuzz import fuzz

warnings.filterwarnings("ignore")
pd.set_option("display.max_columns", 200)

# ------------------------------------------------------------
# 1) CONFIG
# ------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"

CONFIG = {
    "DATA_DIR": str(DATA_DIR),
    # Currency conversion (editable from the UI)
    "DZD_PER_USD": 135.0,
    "DZD_PER_EUR": 145.0,
    # Matching thresholds
    "FUZZY_DCI_THRESHOLD": 82,
    "FUZZY_STRONG_THRESHOLD": 90,
    # Default IQVIA window used for sizing. MAT = Moving Annual Total (best annual proxy).
    "IQVIA_PERIOD": "MAT",  # MAT | YTD | MONTH
    "IQVIA_MOLECULE_SHEET": "ATC Prod Mol Lab",
    "IQVIA_LAB_SHEET": "Total Lab",
    "IQVIA_CLASS_PRODUCT_SHEET": "ATC4 Produit",
}

# Source labels reused across the app
SRC_IQVIA = "IQVIA VILLE"
SRC_PCH = "PCH HOSPITALIER"

# ------------------------------------------------------------
# 2) TEXT NORMALIZATION (pharma-safe)
# ------------------------------------------------------------
STOPWORDS = set(
    """
ACIDE ACID BASE BASIQUE SODIUM POTASSIUM CALCIUM MAGNESIUM HYDROCHLORIDE CHLORHYDRATE DICHLORHYDRATE
MONOHYDRATE DIHYDRATE TRIHYDRATE ANHYDRE MALEATE MESILATE PHOSPHATE SULFATE SULPHATE NITRATE LA LE LES DE DU DES ET OU AVEC SANS
COMPRIME COMP GELULE GLES SIROP SOLUTION INJECTABLE INJ SOL SUSPENSION BUVABLE FLACON AMP AMPOULE BTE BOITE B
""".split()
)

FORM_SYNONYMS = {
    "COMPRIME": ["COMP", "CP", "TAB", "TABLET", "COMPRIME", "COMPRIMES"],
    "GELULE": ["GEL", "GELS", "GLES", "CAPS", "CAPSULE", "GELULE"],
    "SIROP": ["SIROP", "SYRUP"],
    "SOLUTION INJECTABLE": ["SOL INJ", "SOL.INJ", "INJ", "INJECTABLE", "AMP", "AMPOULE", "VIAL", "FLACON INJ"],
    "SOLUTION BUVABLE": ["SOL BUV", "BUVABLE", "ORAL SOLUTION"],
    "SUSPENSION": ["SUSP", "SUSPENSION"],
    "CREME": ["CREME", "CREAM"],
    "POMMADE": ["POMMADE", "OINTMENT"],
    "COLLYRE": ["COLLYRE", "EYE DROPS"],
    "LYOPHILISAT": ["LYO", "LYOPH", "LYOPHILISAT", "POUDRE POUR SOLUTION INJECTABLE"],
}


def strip_accents(s):
    if pd.isna(s):
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c))


def norm_text(s):
    s = strip_accents(s).upper()
    s = s.replace("µ", "U").replace("μ", "U")
    s = re.sub(r"[/\\|,;:+()\[\]{}]", " ", s)
    s = re.sub(r"[^A-Z0-9.%\s-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def compact(s):
    return re.sub(r"\s+", "", norm_text(s))


def tokens(s):
    return [t for t in norm_text(s).split() if t and t not in STOPWORDS]


def safe_num(x):
    if pd.isna(x):
        return 0.0
    if isinstance(x, str):
        x = x.replace("\xa0", " ").replace(" ", "").replace(",", ".")
    try:
        return float(x)
    except Exception:
        return 0.0


# ------------------------------------------------------------
# 3) DOSAGE PARSING
# ------------------------------------------------------------
def parse_dosage_units(text):
    text0 = norm_text(text).replace(",", ".")
    if not text0:
        return []
    out = []
    text0 = text0.replace(" UI", " IU")
    patterns = [
        (r"(\d+(?:\.\d+)?)\s*(MG|G|MCG|UG|µG|IU|UI|ML|%)\s*/\s*(\d+(?:\.\d+)?)?\s*(ML|L|DOSE|PUFF|SACHET|COMP|CP)?", "ratio"),
        (r"(\d+(?:\.\d+)?)\s*(MG|G|MCG|UG|µG|IU|UI|ML|%)", "single"),
    ]
    for pat, kind in patterns:
        for m in re.finditer(pat, text0):
            val = float(m.group(1))
            unit = m.group(2).replace("UI", "IU").replace("UG", "MCG").replace("µG", "MCG")
            denom_val = denom_unit = None
            if kind == "ratio":
                denom_val = float(m.group(3)) if m.group(3) else 1.0
                denom_unit = m.group(4) or ""
            val_mg = None
            if unit == "G":
                val_mg = val * 1000
            elif unit == "MG":
                val_mg = val
            elif unit == "MCG":
                val_mg = val / 1000
            out.append({"raw": m.group(0), "value": val, "unit": unit, "value_mg": val_mg,
                        "denom_value": denom_val, "denom_unit": denom_unit, "kind": kind})
    unique, seen = [], set()
    for d in out:
        k = (round(d.get("value_mg") or d["value"], 6), d["unit"], d.get("denom_value"), d.get("denom_unit"))
        if k not in seen:
            seen.add(k)
            unique.append(d)
    return unique


def dosage_query_variants(q):
    qn = norm_text(q).replace(",", ".")
    if not qn:
        return []
    vals = parse_dosage_units(qn)
    if not vals and re.fullmatch(r"\d+(?:\.\d+)?", qn):
        v = float(qn)
        vals = [
            {"raw": qn, "value": v, "unit": "G", "value_mg": v * 1000, "kind": "single"},
            {"raw": qn, "value": v, "unit": "MG", "value_mg": v, "kind": "single"},
        ]
    return vals


def dosage_match_score(query, candidate_text):
    if not str(query).strip():
        return 100
    qvars = dosage_query_variants(query)
    cvars = parse_dosage_units(candidate_text)
    cand_norm = norm_text(candidate_text)
    qnorm = norm_text(query)
    if qnorm and qnorm in cand_norm:
        return 96
    if not qvars or not cvars:
        return fuzz.partial_ratio(qnorm, cand_norm)
    best = 0
    for q in qvars:
        for c in cvars:
            if q.get("value_mg") is not None and c.get("value_mg") is not None:
                if abs(q["value_mg"] - c["value_mg"]) < 1e-6:
                    best = max(best, 100)
                else:
                    rel = abs(q["value_mg"] - c["value_mg"]) / max(q["value_mg"], c["value_mg"], 1e-9)
                    best = max(best, max(0, 100 - rel * 200))
            if q.get("unit") == c.get("unit") and abs(q.get("value", 0) - c.get("value", -999)) < 1e-6:
                best = max(best, 95)
            if q.get("denom_unit") and c.get("denom_unit") and q["denom_unit"] == c["denom_unit"]:
                best += 3
    return min(100, best)


def canonical_form(s):
    ns = norm_text(s)
    if not ns:
        return ""
    for canon, arr in FORM_SYNONYMS.items():
        for a in arr:
            if norm_text(a) in ns:
                return canon
    return ns


# ------------------------------------------------------------
# 4) FILE DISCOVERY + DYNAMIC IQVIA COLUMN DETECTION
# ------------------------------------------------------------
def _latest_year_in_name(stem):
    yr = 0
    for m in re.finditer(r"(20\d{2})", stem):
        yr = max(yr, int(m.group(1)))
    if yr == 0:
        for m in re.finditer(r"\b(\d{2})\b", stem):
            yr = max(yr, 2000 + int(m.group(1)))
    return yr


def find_file(patterns, year_aware=False):
    """Return the most relevant data file matching any of the glob patterns.
    When year_aware, prefer the file whose name carries the most recent year."""
    cands = []
    for pat in patterns:
        cands += list(DATA_DIR.glob(pat))
    cands = list(dict.fromkeys(cands))
    if not cands:
        return None
    if year_aware:
        cands.sort(key=lambda p: (_latest_year_in_name(p.stem), p.stat().st_mtime), reverse=True)
    else:
        cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0]


def _source_overrides():
    import json
    p = DATA_DIR / "_cache" / "sources.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def set_source_override(kind, path):
    """Pin a specific file for a source kind ('iqvia' | 'pch' | 'nom'),
    e.g. after an in-app upload. Used in priority by the finders."""
    import json
    (DATA_DIR / "_cache").mkdir(parents=True, exist_ok=True)
    ov = _source_overrides()
    ov[kind] = str(path)
    (DATA_DIR / "_cache" / "sources.json").write_text(json.dumps(ov))


def _override(kind):
    p = _source_overrides().get(kind)
    if p and Path(p).exists():
        return Path(p)
    return None


def find_iqvia_file():
    return _override("iqvia") or find_file(["Algeria IQVIA*.xls*", "*IQVIA*.xls*"], year_aware=True)


def find_pch_file():
    return _override("pch") or find_file(["Reception*.xls*", "*PCH*.xls*", "*eception*.xls*"])


def find_nomenclature_file():
    return _override("nom") or find_file(["NOMENCLATURE*.xls*", "*omenclature*.xls*", "*NOMENC*.xls*"])


def detect_period_columns(columns):
    """Classify IQVIA metric columns into (column, period, year, metric)."""
    out = []
    for c in columns:
        u = str(c).upper().replace("\n", " ")
        if "MAT" in u:
            period = "MAT"
        elif "YTD" in u:
            period = "YTD"
        else:
            period = "MONTH"
        ym = re.search(r"(20\d{2})", u)
        if ym:
            year = int(ym.group(1))
        else:
            ym2 = re.search(r"[-\s.](\d{2})\b", u)
            year = 2000 + int(ym2.group(1)) if ym2 else None
        if "MS%" in u and "CHG" in u:
            metric = "MS_CHG_PY"
        elif "GROWTH" in u:
            metric = "GROWTH_PY"
        elif "MARKET SHARE" in u or "MS %" in u or re.search(r"\bMS\b", u):
            metric = "MARKET_SHARE"
        elif "RANK" in u:
            metric = "RANK"
        elif "UNITES" in u or "UNITS" in u:
            metric = "UNITS"
        elif "VALEUR" in u or "VALUE" in u:
            metric = "VALUE"
        else:
            metric = None
        if metric and year:
            out.append((c, period, year, metric))
    return out


def pick_metric_column(detected, metric, period, period_fallback=("MAT", "YTD", "MONTH")):
    order = [period] + [p for p in period_fallback if p != period]
    for per in order:
        for c, p, y, m in detected:
            if p == per and m == metric:
                return c
    return None


def iqvia_reference_year():
    f = find_iqvia_file()
    return _latest_year_in_name(f.stem) if f else None


# ------------------------------------------------------------
# 5) LOADERS
# ------------------------------------------------------------
def _read_sheet(path, sheet, **kw):
    try:
        return pd.read_excel(path, sheet_name=sheet, **kw)
    except Exception:
        return pd.DataFrame()


def load_raw():
    iqvia_file = find_iqvia_file()
    pch_file = find_pch_file()
    nom_file = find_nomenclature_file()
    if iqvia_file is None or nom_file is None:
        missing = []
        if iqvia_file is None:
            missing.append("IQVIA")
        if nom_file is None:
            missing.append("Nomenclature")
        raise FileNotFoundError(
            "Fichiers introuvables dans data/: " + ", ".join(missing) +
            ". Place les fichiers Excel sources dans le dossier data/."
        )

    iqvia_xls = pd.ExcelFile(iqvia_file)
    iqvia_mol = _read_sheet(iqvia_file, CONFIG["IQVIA_MOLECULE_SHEET"])
    if iqvia_mol.empty:
        # fall back to the first sheet that looks granular
        iqvia_mol = _read_sheet(iqvia_file, iqvia_xls.sheet_names[-1])
    iqvia_lab = _read_sheet(iqvia_file, CONFIG["IQVIA_LAB_SHEET"]) if CONFIG["IQVIA_LAB_SHEET"] in iqvia_xls.sheet_names else pd.DataFrame()
    iqvia_classprod = _read_sheet(iqvia_file, CONFIG["IQVIA_CLASS_PRODUCT_SHEET"]) if CONFIG["IQVIA_CLASS_PRODUCT_SHEET"] in iqvia_xls.sheet_names else pd.DataFrame()

    pch = _read_sheet(pch_file, 0) if pch_file is not None else pd.DataFrame()

    nom_active = _read_sheet(nom_file, "Nomenclature Avril 2026")
    if nom_active.empty:
        nom_active = _read_sheet(nom_file, 0)
    nom_non = _read_sheet(nom_file, "Non Renouvelés ")
    nom_ret = _read_sheet(nom_file, "Retraits")

    meta = {
        "iqvia_file": iqvia_file.name if iqvia_file else None,
        "iqvia_year": _latest_year_in_name(iqvia_file.stem) if iqvia_file else None,
        "pch_file": pch_file.name if pch_file else None,
        "nom_file": nom_file.name if nom_file else None,
    }
    return iqvia_mol, iqvia_lab, iqvia_classprod, pch, nom_active, nom_non, nom_ret, meta


# ------------------------------------------------------------
# 6) STANDARDIZE TABLES
# ------------------------------------------------------------
def prep_nomenclature(nom_active, nom_non=None, nom_ret=None):
    frames = []
    for df, src in [(nom_active, "ACTIVE"), (nom_non, "NON_RENOUVELE"), (nom_ret, "RETRAIT")]:
        if df is None or df.empty:
            continue
        x = df.copy()
        x["SOURCE_NOMENCLATURE"] = src
        frames.append(x)
    if not frames:
        return pd.DataFrame()
    nom = pd.concat(frames, ignore_index=True, sort=False)
    rename = {
        "DENOMINATION COMMUNE INTERNATIONALE": "DCI",
        "NOM DE MARQUE": "BRAND",
        "FORME": "FORME",
        "DOSAGE": "DOSAGE",
        "CONDITIONNEMENT": "CONDITIONNEMENT",
        "LABORATOIRES DETENTEUR DE LA DECISION D'ENREGISTREMENT": "LABORATOIRE",
        "PAYS DU LABORATOIRE DETENTEUR DE LA DECISION D'ENREGISTREMENT": "PAYS",
        "STATUT": "STATUT",
        "TYPE": "TYPE",
        "P1": "P1", "P2": "P2", "LISTE": "LISTE", "CODE": "CODE",
    }
    nom = nom.rename(columns={k: v for k, v in rename.items() if k in nom.columns})
    for c in ["DCI", "BRAND", "FORME", "DOSAGE", "CONDITIONNEMENT", "LABORATOIRE", "PAYS", "STATUT", "TYPE", "P1", "P2", "LISTE", "CODE"]:
        if c not in nom.columns:
            nom[c] = ""
    nom["DCI_NORM"] = nom["DCI"].map(norm_text)
    nom["BRAND_NORM"] = nom["BRAND"].map(norm_text)
    nom["FORME_NORM"] = nom["FORME"].map(canonical_form)
    nom["DOSAGE_NORM_TEXT"] = nom["DOSAGE"].map(norm_text)
    nom["LAB_NORM"] = nom["LABORATOIRE"].map(norm_text)
    nom["STATUS_NORM"] = nom["STATUT"].map(norm_text)
    nom["ORIGIN"] = nom["STATUT"].map(status_origin)  # LOCAL / IMPORT / OTHER
    # Registration dates (column names carry irregular spacing in the source file)
    init_col = next((c for c in nom.columns if "ENREGISTREMENT" in str(c).upper() and "INITIAL" in str(c).upper()), None)
    final_col = next((c for c in nom.columns if "ENREGISTREMENT" in str(c).upper() and "FINAL" in str(c).upper()), None)
    nom["DATE_ENR_INITIAL"] = pd.to_datetime(nom[init_col], errors="coerce") if init_col else pd.NaT
    nom["DATE_ENR_FINAL"] = pd.to_datetime(nom[final_col], errors="coerce") if final_col else pd.NaT
    nom["PRODUCT_FULL"] = (
        nom["BRAND"].fillna("").astype(str) + " " + nom["FORME"].fillna("").astype(str) + " "
        + nom["DOSAGE"].fillna("").astype(str) + " " + nom["CONDITIONNEMENT"].fillna("").astype(str)
    ).str.strip()
    return nom


def status_origin(status):
    """Map Nomenclature STATUT to LOCAL (fabriqué) / IMPORT / OTHER."""
    s = norm_text(status)
    if not s:
        return "OTHER"
    parts = set(s.replace("/", " ").replace("-", " ").split())
    if s == "F" or "F" in parts or s.startswith("FAB") or "FABRI" in s or "PROD" in s:
        return "LOCAL"
    if s == "I" or "I" in parts or s.startswith("IMP") or "IMPORT" in s:
        return "IMPORT"
    return "OTHER"


def prep_iqvia(iqvia_mol, period=None):
    """Granular IQVIA molecule table with dynamic period columns.
    Drops embedded total rows; keeps per-molecule granularity for DCI search.
    Market sizing must de-duplicate on (BRAND, PRESENTATION, LABORATOIRE)."""
    period = (period or CONFIG["IQVIA_PERIOD"]).upper()
    x = iqvia_mol.copy()
    x = x.rename(columns={
        "ATC4": "THERAPEUTIC_CLASS", "PRODUIT": "BRAND", "PRESENTATION": "PRESENTATION",
        "MOLECULE": "MOLECULE", "LABORATOIRE": "LABORATOIRE",
    })
    for c in ["THERAPEUTIC_CLASS", "BRAND", "PRESENTATION", "MOLECULE", "LABORATOIRE"]:
        if c not in x.columns:
            x[c] = ""
    # Drop the embedded "Grand Total" / blank rows that would double the market.
    x = x[x["BRAND"].notna() & x["BRAND"].astype(str).str.strip().ne("")]
    x = x[~x["THERAPEUTIC_CLASS"].astype(str).str.strip().str.lower().eq("grand total")]

    detected = detect_period_columns(iqvia_mol.columns)
    val_c = pick_metric_column(detected, "VALUE", period)
    unit_c = pick_metric_column(detected, "UNITS", period)
    share_c = pick_metric_column(detected, "MARKET_SHARE", period)
    growth_c = pick_metric_column(detected, "GROWTH_PY", period)

    x["MARKET_VALUE_DZD"] = x[val_c].map(safe_num) if val_c else 0.0
    x["MARKET_VOLUME"] = x[unit_c].map(safe_num) if unit_c else 0.0
    x["MARKET_SHARE_RAW"] = x[share_c].map(safe_num) if share_c else np.nan
    x["GROWTH_PY"] = x[growth_c].map(safe_num) if growth_c else np.nan
    x["MARKET_VALUE_USD"] = x["MARKET_VALUE_DZD"] / CONFIG["DZD_PER_USD"]

    x["MOLECULE_NORM"] = x["MOLECULE"].map(norm_text)
    x["BRAND_NORM"] = x["BRAND"].map(norm_text)
    x["PRES_NORM"] = x["PRESENTATION"].map(norm_text)
    x["FORME_NORM"] = x["PRESENTATION"].map(canonical_form)
    x["LAB_NORM"] = x["LABORATOIRE"].map(norm_text)
    x["PRODUCT_FULL"] = (x["BRAND"].fillna("").astype(str) + " " + x["PRESENTATION"].fillna("").astype(str)).str.strip()
    x["PROD_KEY"] = x["BRAND_NORM"] + "|" + x["PRES_NORM"] + "|" + x["LAB_NORM"]
    x["SOURCE_MARKET"] = SRC_IQVIA
    x.attrs["period"] = period
    return x


def iqvia_products(iqvia):
    """One row per distinct product-presentation-lab (de-duplicated, reconciled to IQVIA totals)."""
    if iqvia is None or iqvia.empty:
        return pd.DataFrame()
    cols = ["PROD_KEY", "THERAPEUTIC_CLASS", "BRAND", "PRESENTATION", "PRODUCT_FULL", "LABORATOIRE",
            "LAB_NORM", "FORME_NORM", "MARKET_VALUE_DZD", "MARKET_VOLUME", "MARKET_SHARE_RAW", "GROWTH_PY"]
    cols = [c for c in cols if c in iqvia.columns]
    return iqvia[cols].drop_duplicates(subset=["PROD_KEY"]).copy()


def prep_pch(pch):
    x = pch.copy()
    x = x.rename(columns={
        "GAMME": "GAMME", "DESI_CLASSE": "THERAPEUTIC_CLASS", "NOM_FOUR": "LABORATOIRE",
        "DESI_PRO": "PRODUCT_FULL", "CODE_COND": "CONDITIONNEMENT", "QTE": "QTE",
        "ROUND(P.COUT_UNIT_ACHAT,2)": "UNIT_PRICE", "CODE_MON": "DEVISE",
        "DATESTOCKAGE": "DATESTOCKAGE", "TYPE_RECEP": "TYPE_RECEP",
    })
    for c in ["GAMME", "THERAPEUTIC_CLASS", "LABORATOIRE", "PRODUCT_FULL", "CONDITIONNEMENT", "QTE", "UNIT_PRICE", "DEVISE"]:
        if c not in x.columns:
            x[c] = ""
    x["TEXT_NORM"] = x["PRODUCT_FULL"].map(norm_text)
    x["FORME_NORM"] = x["PRODUCT_FULL"].map(canonical_form)
    x["LAB_NORM"] = x["LABORATOIRE"].map(norm_text)
    x["QTE"] = x["QTE"].map(safe_num)
    x["UNIT_PRICE"] = x["UNIT_PRICE"].map(safe_num)
    # PCH business rule: UNIT_PRICE is ALWAYS already in DZD even if DEVISE shows USD/EUR.
    x["MARKET_VALUE_DZD"] = x["QTE"] * x["UNIT_PRICE"]
    x["MARKET_VALUE_USD"] = x["MARKET_VALUE_DZD"] / CONFIG["DZD_PER_USD"]
    x["MARKET_VOLUME"] = x["QTE"]
    x["DEVISE_NORM"] = x["DEVISE"].fillna("DA").astype(str).str.upper().str.strip()
    x["SOURCE_MARKET"] = SRC_PCH
    return x


# ------------------------------------------------------------
# 7) IQVIA AGGREGATE SHEETS (official, pre-reconciled)
# ------------------------------------------------------------
def prep_lab_landscape(iqvia_lab, period=None):
    """Laboratory-level competitive table from the official 'Total Lab' sheet."""
    if iqvia_lab is None or iqvia_lab.empty:
        return pd.DataFrame()
    period = (period or CONFIG["IQVIA_PERIOD"]).upper()
    detected = detect_period_columns(iqvia_lab.columns)
    val_c = pick_metric_column(detected, "VALUE", period)
    unit_c = pick_metric_column(detected, "UNITS", period)
    share_c = pick_metric_column(detected, "MARKET_SHARE", period)
    growth_c = pick_metric_column(detected, "GROWTH_PY", period)
    rank_c = pick_metric_column(detected, "RANK", period)
    lab_col = iqvia_lab.columns[0]
    out = pd.DataFrame({
        "LABORATOIRE": iqvia_lab[lab_col].astype(str).str.strip(),
        "Value_DZD": iqvia_lab[val_c].map(safe_num) if val_c else 0.0,
        "Volume": iqvia_lab[unit_c].map(safe_num) if unit_c else 0.0,
        "Market_Share": iqvia_lab[share_c].map(safe_num) if share_c else np.nan,
        "Growth_PY": iqvia_lab[growth_c].map(safe_num) if growth_c else np.nan,
        "Rank": iqvia_lab[rank_c].map(safe_num) if rank_c else np.nan,
    })
    out = out[~out["LABORATOIRE"].str.lower().isin(["grand total", "total", "nan", ""])]
    out["Value_USD"] = out["Value_DZD"] / CONFIG["DZD_PER_USD"]
    return out.sort_values("Value_DZD", ascending=False).reset_index(drop=True)


def iqvia_total_market(iqvia_lab, iqvia):
    """Return dict with total market value/volume/growth. Prefer official lab sheet."""
    land = prep_lab_landscape(iqvia_lab)
    if not land.empty:
        total_val = float(land["Value_DZD"].sum())
        total_vol = float(land["Volume"].sum())
        growth = weighted_growth_py(land["Value_DZD"], land["Growth_PY"])
        n_labs = int((land["Value_DZD"] > 0).sum())
    else:
        prod = iqvia_products(iqvia)
        total_val = float(prod["MARKET_VALUE_DZD"].sum()) if not prod.empty else 0.0
        total_vol = float(prod["MARKET_VOLUME"].sum()) if not prod.empty else 0.0
        growth = weighted_growth_py(prod["MARKET_VALUE_DZD"], prod["GROWTH_PY"]) if not prod.empty else np.nan
        n_labs = int(prod["LABORATOIRE"].nunique()) if not prod.empty else 0
    return {
        "value_dzd": total_val,
        "value_usd": total_val / CONFIG["DZD_PER_USD"],
        "volume": total_vol,
        "growth_py": growth,
        "n_labs": n_labs,
    }


def iqvia_class_breakdown(iqvia, top=None):
    """Therapeutic-class breakdown (ATC4) with value, volume, value-weighted growth, #players."""
    prod = iqvia_products(iqvia)
    if prod.empty:
        return pd.DataFrame()
    g = prod.groupby("THERAPEUTIC_CLASS", dropna=False)
    out = g.agg(
        Value_DZD=("MARKET_VALUE_DZD", "sum"),
        Volume=("MARKET_VOLUME", "sum"),
        Players=("LABORATOIRE", "nunique"),
        Products=("BRAND", "nunique"),
    ).reset_index()
    # YoY growth per class (prior-reconstruction, outlier-robust)
    gr = prod.groupby("THERAPEUTIC_CLASS").apply(
        lambda d: weighted_growth_py(d["MARKET_VALUE_DZD"], d["GROWTH_PY"])
    ).rename("Growth_PY").reset_index()
    out = out.merge(gr, on="THERAPEUTIC_CLASS", how="left")
    out["Value_USD"] = out["Value_DZD"] / CONFIG["DZD_PER_USD"]
    total = out["Value_DZD"].sum()
    out["Share"] = np.where(total > 0, out["Value_DZD"] / total, np.nan)
    out = out.sort_values("Value_DZD", ascending=False).reset_index(drop=True)
    return out.head(top) if top else out


def weighted_growth_py(values, growths):
    """Aggregate per-line YoY growth correctly and robustly.
    Reconstructs the prior-year value of each line (value / (1+growth)) and returns
    Σvalue / Σprior - 1. Outlier lines (huge % on tiny value) barely move the result,
    unlike a naive value-weighted mean of percentages."""
    v = pd.to_numeric(pd.Series(values).reset_index(drop=True), errors="coerce")
    g = pd.to_numeric(pd.Series(growths).reset_index(drop=True), errors="coerce")
    mask = v.notna() & g.notna() & (g > -1) & (v > 0)
    if mask.sum() == 0:
        return np.nan
    cur = v[mask]
    prior = cur / (1 + g[mask])
    tot_prior = prior.sum()
    return float(cur.sum() / tot_prior - 1) if tot_prior > 0 else np.nan


def compute_hhi(shares):
    """Herfindahl-Hirschman Index on a list/array of fractional market shares (0-1)."""
    s = pd.to_numeric(pd.Series(shares), errors="coerce").fillna(0)
    total = s.sum()
    if total <= 0:
        return np.nan
    frac = s / total
    return float((frac ** 2).sum() * 10000)  # 0-10000 scale


def hhi_label(hhi):
    if hhi is None or (isinstance(hhi, float) and math.isnan(hhi)):
        return "—"
    if hhi < 1500:
        return "Concurrentiel"
    if hhi < 2500:
        return "Modérément concentré"
    return "Très concentré"


def class_list(iqvia):
    prod = iqvia_products(iqvia)
    if prod.empty:
        return []
    return safe_unique(prod["THERAPEUTIC_CLASS"], 5000)


def lab_list_iqvia(iqvia):
    prod = iqvia_products(iqvia)
    if prod.empty:
        return []
    return safe_unique(prod["LABORATOIRE"], 5000)


def class_competition(iqvia, class_name):
    """Competitive landscape inside one therapeutic class (ATC4).
    Returns (labs_df, products_df, summary_dict)."""
    prod = iqvia_products(iqvia)
    if prod.empty or not class_name:
        return pd.DataFrame(), pd.DataFrame(), {}
    sub = prod[prod["THERAPEUTIC_CLASS"].astype(str) == str(class_name)].copy()
    if sub.empty:
        return pd.DataFrame(), pd.DataFrame(), {}
    total = sub["MARKET_VALUE_DZD"].sum()

    labs = sub.groupby("LABORATOIRE", dropna=False).apply(
        lambda d: pd.Series({
            "Value_DZD": d["MARKET_VALUE_DZD"].sum(),
            "Volume": d["MARKET_VOLUME"].sum(),
            "Products": d["BRAND"].nunique(),
            "Growth_PY": weighted_growth_py(d["MARKET_VALUE_DZD"], d["GROWTH_PY"]),
        })
    ).reset_index()
    labs["Share"] = np.where(total > 0, labs["Value_DZD"] / total, np.nan)
    labs["Value_USD"] = labs["Value_DZD"] / CONFIG["DZD_PER_USD"]
    labs = labs.sort_values("Value_DZD", ascending=False).reset_index(drop=True)

    products = sub.groupby(["BRAND", "LABORATOIRE"], dropna=False).apply(
        lambda d: pd.Series({
            "Value_DZD": d["MARKET_VALUE_DZD"].sum(),
            "Volume": d["MARKET_VOLUME"].sum(),
            "Growth_PY": weighted_growth_py(d["MARKET_VALUE_DZD"], d["GROWTH_PY"]),
        })
    ).reset_index()
    products["Share"] = np.where(total > 0, products["Value_DZD"] / total, np.nan)
    products["Value_USD"] = products["Value_DZD"] / CONFIG["DZD_PER_USD"]
    products = products.sort_values("Value_DZD", ascending=False).reset_index(drop=True)

    summary = {
        "class": class_name,
        "value_dzd": float(total),
        "value_usd": float(total) / CONFIG["DZD_PER_USD"],
        "volume": float(sub["MARKET_VOLUME"].sum()),
        "growth_py": weighted_growth_py(sub["MARKET_VALUE_DZD"], sub["GROWTH_PY"]),
        "n_labs": int(labs["LABORATOIRE"].nunique()),
        "n_products": int(sub["BRAND"].nunique()),
        "hhi": compute_hhi(labs["Share"]),
        "leader": labs.iloc[0]["LABORATOIRE"] if len(labs) else "—",
        "leader_share": float(labs.iloc[0]["Share"]) if len(labs) else np.nan,
    }
    return labs, products, summary


def lab_portfolio(iqvia, lab_name):
    """Portfolio of one laboratory: per-class and per-product breakdown."""
    prod = iqvia_products(iqvia)
    if prod.empty or not lab_name:
        return pd.DataFrame(), pd.DataFrame(), {}
    sub = prod[prod["LABORATOIRE"].astype(str) == str(lab_name)].copy()
    if sub.empty:
        return pd.DataFrame(), pd.DataFrame(), {}
    by_class = sub.groupby("THERAPEUTIC_CLASS", dropna=False).apply(
        lambda d: pd.Series({
            "Value_DZD": d["MARKET_VALUE_DZD"].sum(),
            "Volume": d["MARKET_VOLUME"].sum(),
            "Products": d["BRAND"].nunique(),
            "Growth_PY": weighted_growth_py(d["MARKET_VALUE_DZD"], d["GROWTH_PY"]),
        })
    ).reset_index().sort_values("Value_DZD", ascending=False)
    by_class["Value_USD"] = by_class["Value_DZD"] / CONFIG["DZD_PER_USD"]
    products = sub[["BRAND", "PRESENTATION", "THERAPEUTIC_CLASS", "MARKET_VALUE_DZD", "MARKET_VOLUME", "GROWTH_PY"]].copy()
    products = products.sort_values("MARKET_VALUE_DZD", ascending=False).reset_index(drop=True)
    summary = {
        "lab": lab_name,
        "value_dzd": float(sub["MARKET_VALUE_DZD"].sum()),
        "value_usd": float(sub["MARKET_VALUE_DZD"].sum()) / CONFIG["DZD_PER_USD"],
        "growth_py": weighted_growth_py(sub["MARKET_VALUE_DZD"], sub["GROWTH_PY"]),
        "n_classes": int(sub["THERAPEUTIC_CLASS"].nunique()),
        "n_products": int(sub["BRAND"].nunique()),
    }
    return by_class, products, summary


def nomenclature_origin_for_dci(nom, dci_list):
    """Local (fabriqué) vs import manufacturer counts for the given DCI(s), from the active Nomenclature."""
    if nom is None or nom.empty:
        return {"local_labs": [], "import_labs": [], "other_labs": []}
    sub = _strict_filter_by_dci_column(nom, dci_list, "DCI_NORM")
    if sub.empty:
        return {"local_labs": [], "import_labs": [], "other_labs": []}
    if "SOURCE_NOMENCLATURE" in sub.columns:
        sub = sub[sub["SOURCE_NOMENCLATURE"].astype(str).str.upper().eq("ACTIVE")]
    local = sorted(set(sub.loc[sub["ORIGIN"].eq("LOCAL"), "LABORATOIRE"].replace("", pd.NA).dropna().astype(str)))
    imp = sorted(set(sub.loc[sub["ORIGIN"].eq("IMPORT"), "LABORATOIRE"].replace("", pd.NA).dropna().astype(str)))
    other = sorted(set(sub.loc[sub["ORIGIN"].eq("OTHER"), "LABORATOIRE"].replace("", pd.NA).dropna().astype(str)))
    return {"local_labs": local, "import_labs": imp, "other_labs": other}


def parse_smart_query(text, nom):
    """Parse a free-text query like 'amoxicilline 500 mg comprime' into
    {dci_candidates, dosage, forme}. Powers the intelligent pricing search."""
    raw = str(text or "").strip()
    if not raw:
        return {"dci_candidates": [], "dosage": [], "forme": []}
    # dosage tokens
    dos = parse_dosage_units(raw)
    dosage = sorted({d["raw"].strip() for d in dos if d.get("raw")})
    # forme detection
    formes = []
    for canon, arr in FORM_SYNONYMS.items():
        if any(norm_text(a) in norm_text(raw) for a in arr):
            formes.append(canon)
    # DCI: strip dosage/forme noise, rank remaining text against nomenclature DCIs
    cleaned = norm_text(raw)
    for d in dos:
        cleaned = cleaned.replace(norm_text(d.get("raw", "")), " ")
    for canon, arr in FORM_SYNONYMS.items():
        for a in arr:
            cleaned = re.sub(_regex_word_token(a), " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    dci_candidates = get_nomenclature_dci_options(nom, cleaned or raw, limit=10)
    return {"dci_candidates": dci_candidates, "dosage": dosage, "forme": list(dict.fromkeys(formes))}


def price_for_dci(iqvia, pch, nom, dci_list, dosage=None, formes=None, labs=None, markets=None):
    """Price intelligence for a DCI: average / range price per box (IQVIA ville)
    and per unit (PCH hospitalier), plus per-product detail."""
    markets = markets or [SRC_IQVIA, SRC_PCH]
    out = {"ville": None, "hospital": None, "ville_rows": pd.DataFrame(), "hospital_rows": pd.DataFrame()}

    def _stats(prices, avg):
        prices = pd.to_numeric(pd.Series(prices), errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        return {
            "avg_dzd": avg,
            "avg_usd": (avg / CONFIG["DZD_PER_USD"]) if avg == avg else np.nan,
            "min": float(prices.min()) if len(prices) else np.nan,
            "median": float(prices.median()) if len(prices) else np.nan,
            "max": float(prices.max()) if len(prices) else np.nan,
            "n": int(len(prices)),
        }

    if SRC_IQVIA in markets:
        iq = filter_iqvia(iqvia, dci_list, dosage, formes, labs)
        if iq is not None and not iq.empty:
            if "PROD_KEY" in iq.columns:
                iq = iq.sort_values("MARKET_VALUE_DZD", ascending=False).drop_duplicates(subset=["_QUERY_DCI", "PROD_KEY"])
            iq = iq.copy()
            iq["Prix_boite_DZD"] = np.where(iq["MARKET_VOLUME"] > 0, iq["MARKET_VALUE_DZD"] / iq["MARKET_VOLUME"], np.nan)
            tv, tvol = iq["MARKET_VALUE_DZD"].sum(), iq["MARKET_VOLUME"].sum()
            out["ville"] = _stats(iq["Prix_boite_DZD"], tv / tvol if tvol > 0 else np.nan)
            out["ville_rows"] = iq[[c for c in ["BRAND", "PRESENTATION", "LABORATOIRE", "MARKET_VOLUME", "MARKET_VALUE_DZD", "Prix_boite_DZD", "GROWTH_PY"] if c in iq.columns]].sort_values("MARKET_VALUE_DZD", ascending=False)

    if SRC_PCH in markets:
        ph = filter_pch(pch, dci_list, dosage, formes, labs)
        if ph is not None and not ph.empty:
            ph = ph.copy()
            ph["Prix_unitaire_DZD"] = pd.to_numeric(ph["UNIT_PRICE"], errors="coerce")
            tv, tvol = (ph["Prix_unitaire_DZD"] * ph["QTE"]).sum(), ph["QTE"].sum()
            out["hospital"] = _stats(ph["Prix_unitaire_DZD"], tv / tvol if tvol > 0 else np.nan)
            out["hospital_rows"] = ph[[c for c in ["PRODUCT_FULL", "LABORATOIRE", "QTE", "Prix_unitaire_DZD", "MARKET_VALUE_DZD", "DEVISE", "DATESTOCKAGE"] if c in ph.columns]].sort_values("MARKET_VALUE_DZD", ascending=False)
    return out


def nomenclature_dci_dates(nom, active_only=True):
    """Per-DCI registration timeline: latest initial registration and nearest expiry."""
    if nom is None or nom.empty or "DCI" not in nom.columns:
        return pd.DataFrame(columns=["DCI", "DCI_NORM_KEY", "Last_registration", "Next_expiry", "Registrations"])
    x = nom.copy()
    if active_only and "SOURCE_NOMENCLATURE" in x.columns:
        x = x[x["SOURCE_NOMENCLATURE"].astype(str).str.upper().eq("ACTIVE")]
    x = x[x["DCI"].notna() & x["DCI"].astype(str).str.strip().ne("")]
    if x.empty:
        return pd.DataFrame(columns=["DCI", "DCI_NORM_KEY", "Last_registration", "Next_expiry", "Registrations"])
    x["DCI_NORM_KEY"] = x["DCI"].map(norm_text)
    rows = []
    for key, g in x.groupby("DCI_NORM_KEY", dropna=False):
        rows.append({
            "DCI": safe_unique(g["DCI"], 5)[0] if len(g) else key,
            "DCI_NORM_KEY": key,
            "Last_registration": pd.to_datetime(g["DATE_ENR_INITIAL"], errors="coerce").max(),
            "Next_expiry": pd.to_datetime(g["DATE_ENR_FINAL"], errors="coerce").max(),
            "Registrations": int(len(g)),
        })
    return pd.DataFrame(rows)


# ------------------------------------------------------------
# 8) PHARMA-SAFE DCI MATCHING
# ------------------------------------------------------------
MOLECULE_CONFUSION_BLACKLIST = {
    "RALTEGRAVIR": {"DOLUTEGRAVIR", "BICTEGRAVIR", "ELVITEGRAVIR"},
    "DOLUTEGRAVIR": {"RALTEGRAVIR", "BICTEGRAVIR", "ELVITEGRAVIR"},
    "BICTEGRAVIR": {"RALTEGRAVIR", "DOLUTEGRAVIR", "ELVITEGRAVIR"},
    "ELVITEGRAVIR": {"RALTEGRAVIR", "DOLUTEGRAVIR", "BICTEGRAVIR"},
}
MOLECULE_SUFFIXES_REQUIRING_EXACT_TOKEN = (
    "TEGRAVIR", "VIR", "MAB", "TINIB", "STATIN", "PRIL", "SARTAN", "OLOL", "CAINE", "AZOLE", "CYCLINE",
)


def query_molecule_tokens(query_dci):
    return [t for t in tokens(norm_text(query_dci)) if len(t) >= 3]


def _regex_word_token(tok):
    tok = re.escape(norm_text(tok))
    return rf"(?<![A-Z0-9]){tok}(?![A-Z0-9])"


def _contains_all_query_tokens_series(series_norm, query_dci):
    qtokens = query_molecule_tokens(query_dci)
    if not qtokens:
        return pd.Series(False, index=series_norm.index)
    mask = pd.Series(True, index=series_norm.index)
    for tok in qtokens:
        mask &= series_norm.fillna("").astype(str).str.contains(_regex_word_token(tok), regex=True, na=False)
    return mask


def _candidate_tokens(candidate):
    return set(t for t in tokens(candidate) if len(t) >= 3)


def _is_blacklisted_molecule_pair(query_dci, candidate_text):
    qt = set(query_molecule_tokens(query_dci))
    ct = _candidate_tokens(candidate_text)
    for q in qt:
        if q in MOLECULE_CONFUSION_BLACKLIST and (ct & MOLECULE_CONFUSION_BLACKLIST[q]):
            return True
    return False


def _requires_exact_token(query_dci):
    qts = query_molecule_tokens(query_dci)
    if not qts:
        return True
    if len(qts) == 1 and any(qts[0].endswith(suf) for suf in MOLECULE_SUFFIXES_REQUIRING_EXACT_TOKEN):
        return True
    return False


def dci_match_score(query_dci, candidate):
    q = norm_text(query_dci)
    c = norm_text(candidate)
    if not q or not c:
        return 0
    if q == c:
        return 100
    qt, ct = set(query_molecule_tokens(q)), _candidate_tokens(c)
    if qt and qt.issubset(ct):
        return 99
    if _is_blacklisted_molecule_pair(q, c):
        return 0
    if _requires_exact_token(q):
        best_token = max([fuzz.WRatio(t, q) for t in ct] or [0])
        return best_token if best_token >= 94 else 0
    score = max(fuzz.WRatio(q, c), fuzz.token_sort_ratio(q, c), fuzz.token_set_ratio(q, c))
    return score if score >= 90 else 0


def text_product_match_score(query_dci, product_text):
    q = norm_text(query_dci)
    t = norm_text(product_text)
    if not q or not t:
        return 0
    qt, tt = set(query_molecule_tokens(q)), _candidate_tokens(t)
    if qt and qt.issubset(tt):
        return 99
    if _is_blacklisted_molecule_pair(q, t):
        return 0
    best_token = max([fuzz.WRatio(qtok, ttok) for qtok in qt for ttok in tt] or [0])
    threshold = 95 if _requires_exact_token(q) else 92
    return best_token if best_token >= threshold else 0


# ------------------------------------------------------------
# 9) FILTERS
# ------------------------------------------------------------
def apply_filters(df, dosage=None, formes=None, labs=None, statuts=None, source="nom"):
    x = df.copy()
    if dosage:
        coltxt = "DOSAGE" if source == "nom" else ("PRESENTATION" if source == "iqvia" else "PRODUCT_FULL")
        dosage_list = [str(d).strip() for d in (dosage if isinstance(dosage, (list, tuple, set)) else [dosage]) if str(d).strip()]
        if dosage_list:
            x["_DOSAGE_SCORE"] = x[coltxt].fillna("").astype(str).map(lambda s: max([dosage_match_score(d, s) for d in dosage_list] or [0]))
            x = x[x["_DOSAGE_SCORE"] >= 82]
        else:
            x["_DOSAGE_SCORE"] = 100
    else:
        x["_DOSAGE_SCORE"] = 100
    if formes:
        forms_norm = set(canonical_form(f) for f in formes if str(f).strip())
        if forms_norm:
            x = x[x["FORME_NORM"].isin(forms_norm)]
    if labs:
        labs_norm = set(norm_text(l) for l in labs if str(l).strip())
        if labs_norm:
            x = x[x["LAB_NORM"].isin(labs_norm)]
    if statuts and source == "nom":
        sts = set(norm_text(s) for s in statuts if str(s).strip())
        if sts:
            x = x[x["STATUS_NORM"].isin(sts)]
    return x


def _strict_filter_by_dci_column(df, dci_list, col_norm):
    frames = []
    for dci in dci_list:
        tmp = df.copy()
        tmp["_QUERY_DCI"] = dci
        exact_mask = _contains_all_query_tokens_series(tmp[col_norm], dci)
        if exact_mask.any():
            tmp = tmp[exact_mask].copy()
            tmp["_DCI_SCORE"] = tmp[col_norm].map(lambda s: dci_match_score(dci, s)).replace(0, 99)
        else:
            tmp["_DCI_SCORE"] = tmp[col_norm].map(lambda s: dci_match_score(dci, s))
            tmp = tmp[tmp["_DCI_SCORE"] >= max(CONFIG["FUZZY_DCI_THRESHOLD"], 90)]
        frames.append(tmp)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates()


def filter_nomenclature(nom, dci_list, dosage=None, formes=None, labs=None, statuts=None):
    tmp = _strict_filter_by_dci_column(nom, dci_list, "DCI_NORM")
    if tmp.empty:
        return tmp
    return apply_filters(tmp, dosage, formes, labs, statuts, source="nom")


def filter_iqvia(iqvia, dci_list, dosage=None, formes=None, labs=None):
    tmp = _strict_filter_by_dci_column(iqvia, dci_list, "MOLECULE_NORM")
    if tmp.empty:
        return tmp
    return apply_filters(tmp, dosage, formes, labs, None, source="iqvia")


def filter_pch(pch, dci_list, dosage=None, formes=None, labs=None):
    frames = []
    for dci in dci_list:
        tmp = pch.copy()
        tmp["_QUERY_DCI"] = dci
        exact_mask = _contains_all_query_tokens_series(tmp["TEXT_NORM"], dci)
        if exact_mask.any():
            tmp = tmp[exact_mask].copy()
            tmp["_DCI_SCORE"] = tmp["TEXT_NORM"].map(lambda s: text_product_match_score(dci, s)).replace(0, 99)
        else:
            tmp["_DCI_SCORE"] = tmp["TEXT_NORM"].map(lambda s: text_product_match_score(dci, s))
            tmp = tmp[tmp["_DCI_SCORE"] >= 92]
        tmp = apply_filters(tmp, dosage, formes, labs, None, source="pch")
        frames.append(tmp)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates()


# ------------------------------------------------------------
# 10) DCI-LEVEL MARKET + COMPETITION
# ------------------------------------------------------------
def _dedup_iqvia_matches(iqvia_matches):
    """Avoid molecule multi-count: keep one row per (query DCI, product, presentation, lab)."""
    if iqvia_matches is None or iqvia_matches.empty:
        return iqvia_matches
    keys = [c for c in ["_QUERY_DCI", "PROD_KEY"] if c in iqvia_matches.columns]
    if not keys:
        return iqvia_matches
    return iqvia_matches.sort_values("MARKET_VALUE_DZD", ascending=False).drop_duplicates(subset=keys)


def summarize_market(market_df, source_name):
    if market_df is None or market_df.empty:
        return pd.DataFrame()
    x = market_df.copy()
    if source_name == SRC_IQVIA:
        x = _dedup_iqvia_matches(x)
    group_cols = ["_QUERY_DCI", "PRODUCT_FULL", "LABORATOIRE", "SOURCE_MARKET"]
    agg = x.groupby(group_cols, dropna=False).agg(
        Therapeutic_Class=("THERAPEUTIC_CLASS", "first"),
        Market_Size_Volume=("MARKET_VOLUME", "sum"),
        Market_Size_Value_DZD=("MARKET_VALUE_DZD", "sum"),
        Market_Size_Value_USD=("MARKET_VALUE_USD", "sum"),
        Growth_PY=("GROWTH_PY", "mean") if "GROWTH_PY" in x.columns else ("MARKET_VALUE_DZD", "size"),
        Avg_Match_Score=("_DCI_SCORE", "mean"),
        Dosage_Match_Score=("_DOSAGE_SCORE", "mean"),
    ).reset_index()
    agg["Average_Price_Per_Box_DZD"] = np.where(agg["Market_Size_Volume"] > 0, agg["Market_Size_Value_DZD"] / agg["Market_Size_Volume"], np.nan)
    return agg


def build_opportunity_table(nom_matches, iqvia_matches, pch_matches):
    iq = summarize_market(iqvia_matches, SRC_IQVIA)
    ph = summarize_market(pch_matches, SRC_PCH)
    market = pd.concat([iq, ph], ignore_index=True, sort=False)
    if market.empty:
        return pd.DataFrame(), market, (nom_matches if nom_matches is not None else pd.DataFrame())

    main_rows = []
    for (qdci, source), g in market.groupby(["_QUERY_DCI", "SOURCE_MARKET"], dropna=False):
        lab = g.groupby("LABORATOIRE", dropna=False).agg(
            Value_DZD=("Market_Size_Value_DZD", "sum"),
            Volume=("Market_Size_Volume", "sum"),
        ).reset_index().sort_values("Value_DZD", ascending=False)
        total_value = lab["Value_DZD"].sum()
        total_vol = lab["Volume"].sum()
        lab["Market_Share"] = np.where(total_value > 0, lab["Value_DZD"] / total_value, np.nan)
        top = lab.head(5).reset_index(drop=True)
        product_examples = "; ".join(g.sort_values("Market_Size_Value_DZD", ascending=False)["PRODUCT_FULL"].dropna().astype(str).head(5).tolist())
        nom_sub = nom_matches[nom_matches["_QUERY_DCI"].map(norm_text) == norm_text(qdci)] if nom_matches is not None and not nom_matches.empty else pd.DataFrame()
        dossier = "Disponible" if not nom_sub.empty else "Absent de la nomenclature"
        statuts = ", ".join(sorted(set(nom_sub["STATUT"].dropna().astype(str)))) if not nom_sub.empty and "STATUT" in nom_sub else ""
        hhi = compute_hhi(lab["Market_Share"])
        row = {
            "DCI": qdci,
            "Produits": product_examples,
            "Dossier nomenclature": dossier,
            "Statut nomenclature": statuts,
            "Marché": source,
            "Volume": total_vol,
            "Valeur DZD": total_value,
            "Valeur USD": total_value / CONFIG["DZD_PER_USD"],
            "Prix moyen boîte DZD": total_value / total_vol if total_vol else np.nan,
            "Nb concurrents": int(lab["LABORATOIRE"].nunique()),
            "HHI": round(hhi, 0) if hhi == hhi else np.nan,
            "Concentration": hhi_label(hhi),
        }
        for i in range(5):
            row[f"Concurrent {i+1}"] = top.loc[i, "LABORATOIRE"] if i < len(top) else ""
            row[f"Part {i+1}"] = top.loc[i, "Market_Share"] if i < len(top) else np.nan
        main_rows.append(row)
    main = pd.DataFrame(main_rows).sort_values(["DCI", "Marché"])
    return main, market, (nom_matches if nom_matches is not None else pd.DataFrame())


# ------------------------------------------------------------
# 11) STREAMLIT FACET HELPERS
# ------------------------------------------------------------
def parse_dci_input(dci_input):
    if isinstance(dci_input, str):
        return [x.strip() for x in re.split(r"[,;\n]+", dci_input) if x.strip()]
    return [str(x).strip() for x in (dci_input or []) if str(x).strip()]


def dci_input_to_list(selected_dcis=None, free_text=""):
    selected = [str(x).strip() for x in (selected_dcis or []) if str(x).strip()]
    return selected if selected else parse_dci_input(free_text)


def get_nomenclature_dci_options(nom, query="", limit=300):
    if nom is None or nom.empty or "DCI" not in nom.columns:
        return []
    vals = safe_unique(nom["DCI"].dropna().astype(str), 20000)
    q = norm_text(query)
    if not q:
        return vals[:limit]
    ranked = []
    for v in vals:
        vn = norm_text(v)
        if not vn:
            continue
        if vn == q:
            score = 120
        elif q in vn:
            score = 110
        else:
            score = fuzz.WRatio(q, vn)
            if len(q) >= 5 and score < 88:
                score = 0
        if score >= 78:
            ranked.append((score, len(vn), v))
    ranked.sort(key=lambda x: (-x[0], x[1], x[2]))
    return [v for _, __, v in ranked[:limit]]


def safe_unique(values, limit=1000):
    if values is None:
        return []
    if isinstance(values, (pd.DataFrame, pd.Series)):
        raw = values.to_numpy().ravel().tolist()
    elif isinstance(values, (list, tuple, set, np.ndarray)):
        raw = np.array(list(values), dtype=object).ravel().tolist()
    else:
        raw = [values]
    vals, seen = [], set()
    for v in raw:
        iterable = np.array(list(v), dtype=object).ravel().tolist() if isinstance(v, (list, tuple, set, np.ndarray)) else [v]
        for item in iterable:
            if pd.isna(item):
                continue
            sv = str(item).strip()
            if not sv or sv.lower() in {"nan", "none", "nat"}:
                continue
            if sv not in seen:
                seen.add(sv)
                vals.append(sv)
    return sorted(vals)[:limit]


def build_option_universe(dci_text, selected_markets, nom, iqvia, pch):
    dci_list = parse_dci_input(dci_text)
    selected_markets = selected_markets or [SRC_IQVIA, SRC_PCH]
    if not dci_list:
        return pd.DataFrame(columns=["source", "dci", "dosage", "forme", "lab", "statut", "market", "label"])
    frames = []
    nm = filter_nomenclature(nom, dci_list)
    if nm is not None and not nm.empty:
        frames.append(pd.DataFrame({
            "source": "NOMENCLATURE", "dci": nm["_QUERY_DCI"].astype(str),
            "dosage": nm["DOSAGE"].fillna("").astype(str), "forme": nm["FORME_NORM"].fillna("").astype(str),
            "lab": nm["LABORATOIRE"].fillna("").astype(str), "statut": nm["STATUT"].fillna("").astype(str),
            "market": "NOMENCLATURE", "label": nm["PRODUCT_FULL"].fillna("").astype(str)}))
    if SRC_IQVIA in selected_markets:
        iq = filter_iqvia(iqvia, dci_list)
        if iq is not None and not iq.empty:
            frames.append(pd.DataFrame({
                "source": SRC_IQVIA, "dci": iq["_QUERY_DCI"].astype(str),
                "dosage": iq["PRESENTATION"].fillna("").astype(str), "forme": iq["FORME_NORM"].fillna("").astype(str),
                "lab": iq["LABORATOIRE"].fillna("").astype(str), "statut": "",
                "market": SRC_IQVIA, "label": iq["PRODUCT_FULL"].fillna("").astype(str)}))
    if SRC_PCH in selected_markets:
        ph = filter_pch(pch, dci_list)
        if ph is not None and not ph.empty:
            frames.append(pd.DataFrame({
                "source": SRC_PCH, "dci": ph["_QUERY_DCI"].astype(str),
                "dosage": ph["PRODUCT_FULL"].fillna("").astype(str), "forme": ph["FORME_NORM"].fillna("").astype(str),
                "lab": ph["LABORATOIRE"].fillna("").astype(str), "statut": "",
                "market": SRC_PCH, "label": ph["PRODUCT_FULL"].fillna("").astype(str)}))
    if not frames:
        return pd.DataFrame(columns=["source", "dci", "dosage", "forme", "lab", "statut", "market", "label"])
    u = pd.concat(frames, ignore_index=True, sort=False).fillna("")
    for c in ["dosage", "forme", "lab", "statut", "market"]:
        u[c + "_NORM"] = u[c].map(norm_text)
    return u.drop_duplicates()


def facet_filter(universe, dosage=None, formes=None, labs=None, statuts=None, markets=None, ignore=None):
    ignore = ignore or set()
    x = universe.copy()
    dosage, formes, labs, statuts, markets = list(dosage or []), list(formes or []), list(labs or []), list(statuts or []), list(markets or [])
    if dosage and "dosage" not in ignore:
        x = x[x["dosage"].astype(str).map(lambda s: max([dosage_match_score(d, s) for d in dosage] or [0]) >= 82)]
    if formes and "forme" not in ignore:
        forms_norm = set(canonical_form(f) for f in formes)
        x = x[x["forme"].map(canonical_form).isin(forms_norm)]
    if labs and "lab" not in ignore:
        labs_norm = [norm_text(l) for l in labs]
        x = x[x["lab_NORM"].map(lambda s: max([fuzz.WRatio(str(s), l) for l in labs_norm] or [0]) >= 86)]
    if statuts and "statut" not in ignore:
        sts = set(norm_text(s) for s in statuts)
        x = x[(x["statut_NORM"].isin(sts)) | (x["statut_NORM"].eq(""))]
    if markets and "market" not in ignore:
        m = set(markets)
        x = x[x["market"].isin(m) | x["market"].eq("NOMENCLATURE")]
    return x


def filter_options(options, query, limit=500):
    q = norm_text(query)
    if not q:
        return list(options)[:limit]
    ranked = []
    for o in options:
        on = norm_text(o)
        if q in on:
            ranked.append((100, o))
        else:
            score = fuzz.partial_ratio(q, on)
            if score >= 70:
                ranked.append((score, o))
    return [o for _, o in sorted(ranked, reverse=True)[:limit]]


# ------------------------------------------------------------
# 12) MASTER LOADER  (+ Parquet cache for fast cold starts)
# ------------------------------------------------------------
CACHE_VERSION = "v5.1"
CACHE_DIR = DATA_DIR / "_cache"
_CACHE_TABLES = ["nom", "iqvia", "pch", "lab_landscape", "iqvia_lab_raw"]


def _source_signature(period):
    """Identity of the inputs so a stale cache is detected automatically."""
    import json
    sig = {"cache_version": CACHE_VERSION, "period": (period or CONFIG["IQVIA_PERIOD"]).upper(), "files": {}}
    for finder, key in [(find_iqvia_file, "iqvia"), (find_pch_file, "pch"), (find_nomenclature_file, "nom")]:
        f = finder()
        if f is not None:
            st = f.stat()
            sig["files"][key] = {"name": f.name, "size": st.st_size}
    return json.dumps(sig, sort_keys=True)


def _parquet_safe(df):
    """Return a copy whose object columns are clean strings so pyarrow never chokes
    on mixed str/float cells (the same issue Streamlit hits on display)."""
    if df is None:
        return pd.DataFrame()
    x = df.copy()
    for c in x.columns:
        if x[c].dtype == object:
            x[c] = x[c].map(lambda v: None if (v is None or (isinstance(v, float) and pd.isna(v))) else str(v))
    return x


def _read_cache(period):
    """Return the prepared-data dict from the Parquet cache, or None if missing/stale."""
    sig_path = CACHE_DIR / "signature.json"
    if not sig_path.exists():
        return None
    try:
        if sig_path.read_text() != _source_signature(period):
            return None
        out = {}
        for t in _CACHE_TABLES:
            p = CACHE_DIR / f"{t}.parquet"
            out[t] = pd.read_parquet(p) if p.exists() else pd.DataFrame()
        out["meta"] = _build_meta()
        return out
    except Exception:
        return None


def _write_cache(data, period):
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        for t in _CACHE_TABLES:
            _parquet_safe(data.get(t)).to_parquet(CACHE_DIR / f"{t}.parquet", index=False)
        (CACHE_DIR / "signature.json").write_text(_source_signature(period))
    except Exception:
        pass  # read-only FS or missing pyarrow: degrade gracefully to live loading


def _build_meta():
    iqvia_file, pch_file, nom_file = find_iqvia_file(), find_pch_file(), find_nomenclature_file()
    return {
        "iqvia_file": iqvia_file.name if iqvia_file else None,
        "iqvia_year": _latest_year_in_name(iqvia_file.stem) if iqvia_file else None,
        "pch_file": pch_file.name if pch_file else None,
        "nom_file": nom_file.name if nom_file else None,
    }


def _compute_prepared(period=None):
    iqvia_mol, iqvia_lab, iqvia_classprod, pch, nom_active, nom_non, nom_ret, meta = load_raw()
    nom = prep_nomenclature(nom_active, nom_non, nom_ret)
    iqvia = prep_iqvia(iqvia_mol, period)
    pch_p = prep_pch(pch) if pch is not None and not pch.empty else pd.DataFrame()
    lab_land = prep_lab_landscape(iqvia_lab, period)
    return {
        "nom": nom,
        "iqvia": iqvia,
        "pch": pch_p,
        "lab_landscape": lab_land,
        "iqvia_lab_raw": iqvia_lab,
        "meta": meta,
    }


def load_prepared_data(period=None, use_cache=True):
    """Prepared tables for the whole app. Reads a Parquet cache when valid
    (cold start ~1s); otherwise parses the Excel sources and refreshes the cache."""
    if use_cache:
        cached = _read_cache(period)
        if cached is not None:
            return cached
    data = _compute_prepared(period)
    if use_cache:
        _write_cache(data, period)
    return data


def build_cache(period=None):
    """Force a rebuild of the Parquet cache from the Excel sources."""
    data = _compute_prepared(period)
    _write_cache(data, period)
    return _build_meta()


# ------------------------------------------------------------
# 13) EXCEL EXPORT
# ------------------------------------------------------------
def export_excel_bytes(*sheets):
    """sheets: iterable of (sheet_name, dataframe)."""
    from io import BytesIO
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="xlsxwriter") as writer:
        wrote = False
        for name, df in sheets:
            if df is None:
                df = pd.DataFrame()
            df.to_excel(writer, sheet_name=name[:31], index=False)
            wrote = True
        if not wrote:
            pd.DataFrame().to_excel(writer, sheet_name="Sheet1", index=False)
        wb = writer.book
        header = wb.add_format({"bold": True, "font_color": "white", "bg_color": "#0F766E", "border": 1, "align": "center", "valign": "vcenter"})
        accent = wb.add_format({"bold": True, "font_color": "white", "bg_color": "#F97316", "border": 1, "align": "center"})
        money = wb.add_format({"num_format": "# ##0"})
        pct = wb.add_format({"num_format": "0.0%"})
        for name, df in sheets:
            if df is None or df.empty:
                continue
            ws = writer.sheets[name[:31]]
            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, max(len(df), 1), max(len(df.columns) - 1, 0))
            for i, col in enumerate(df.columns):
                width = min(max(12, int(max([len(str(col))] + [len(str(v)) for v in df[col].head(150).fillna("").astype(str)]) * 1.05)), 48)
                cl = str(col).lower()
                is_share = "part" in cl or "share" in cl
                ws.write(0, i, col, accent if (is_share or "prix" in cl) else header)
                if any(k in cl for k in ["valeur", "value", "prix", "price", "volume", "dzd", "usd"]):
                    ws.set_column(i, i, width, money)
                elif is_share:
                    ws.set_column(i, i, width, pct)
                else:
                    ws.set_column(i, i, width)
    bio.seek(0)
    return bio.getvalue()


# ------------------------------------------------------------
# CLI: regenerate the Parquet cache  ->  python market_engine.py
# ------------------------------------------------------------
if __name__ == "__main__":
    import time
    t0 = time.time()
    meta = build_cache()
    print(f"✅ Cache Parquet généré en {time.time()-t0:.1f}s  ->  {CACHE_DIR}")
    print(f"   Sources: {meta}")
