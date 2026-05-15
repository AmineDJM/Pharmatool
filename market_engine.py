# ============================================================
# ALGERIA PHARMA MARKET OPPORTUNITY TOOL - COLAB VERSION
# Author: ChatGPT for Amine
# Files expected in Colab session:
#   - Algeria IQVIA Data March 25.xlsx
#   - Reception2025_copy.xlsx
#   - NOMENCLATURE.VERSION.AVRIL_.2026-.xlsx
# ============================================================

# ---------- 0) IMPORTS ----------
import os, re, math, unicodedata, warnings
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

warnings.filterwarnings('ignore')
pd.set_option('display.max_columns', 200)
pd.set_option('display.width', 180)

# ---------- 1) CONFIG ----------
BASE_DIR = Path(__file__).resolve().parent if '__file__' in globals() else Path.cwd()
CONFIG = {
    'IQVIA_FILE': str(BASE_DIR / 'data' / 'Algeria IQVIA Data March 25.xlsx'),
    'PCH_FILE': str(BASE_DIR / 'data' / 'Reception2025_copy.xlsx'),
    'NOM_FILE': str(BASE_DIR / 'data' / 'NOMENCLATURE.VERSION.AVRIL_.2026-.xlsx'),
    'OUTPUT_FILE': str(BASE_DIR / 'market_opportunity_output.xlsx'),

    # Exchange rates: EDIT when needed
    'FX_TO_DZD': {
        'DA': 1.0, 'DZD': 1.0, 'DZ': 1.0,
        'USD': 135.0,
        'EUR': 145.0,
        'CHF': 155.0,
        'GBP': 170.0,
    },
    'DZD_PER_USD': 135.0,

    # Matching thresholds
    'FUZZY_DCI_THRESHOLD': 82,
    'FUZZY_TEXT_THRESHOLD': 76,
    'FUZZY_STRONG_THRESHOLD': 90,

    # Default market metric for IQVIA: MAT is most useful for annual market sizing
    'IQVIA_PERIOD': 'MAT',  # options: 'Mar', 'YTD', 'MAT'
}

# ---------- 2) LOW-LEVEL NORMALIZATION ----------
STOPWORDS = set('''
ACIDE ACID BASE BASIQUE SODIUM POTASSIUM CALCIUM MAGNESIUM HYDROCHLORIDE CHLORHYDRATE DICHLORHYDRATE
MONOHYDRATE DIHYDRATE TRIHYDRATE ANHYDRE MALEATE MESILATE PHOSPHATE SULFATE SULPHATE NITRATE LA LE LES DE DU DES ET OU AVEC SANS
COMPRIME COMP GELULE GLES SIROP SOLUTION INJECTABLE INJ SOL SUSPENSION BUVABLE FLACON AMP AMPOULE BTE BOITE B
'''.split())

FORM_SYNONYMS = {
    'COMPRIME': ['COMP', 'CP', 'TAB', 'TABLET', 'COMPRIME', 'COMPRIMES'],
    'GELULE': ['GEL', 'GELS', 'GLES', 'CAPS', 'CAPSULE', 'GELULE'],
    'SIROP': ['SIROP', 'SYRUP'],
    'SOLUTION INJECTABLE': ['SOL INJ', 'SOL.INJ', 'INJ', 'INJECTABLE', 'AMP', 'AMPOULE', 'VIAL', 'FLACON INJ'],
    'SOLUTION BUVABLE': ['SOL BUV', 'BUVABLE', 'ORAL SOLUTION'],
    'SUSPENSION': ['SUSP', 'SUSPENSION'],
    'CREME': ['CREME', 'CREAM'],
    'POMMADE': ['POMMADE', 'OINTMENT'],
    'COLLYRE': ['COLLYRE', 'EYE DROPS'],
    'LYOPHILISAT': ['LYO', 'LYOPH', 'LYOPHILISAT', 'POUDRE POUR SOLUTION INJECTABLE'],
}

def strip_accents(s):
    if pd.isna(s): return ''
    s = str(s)
    s = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in s if not unicodedata.combining(c))

def norm_text(s):
    s = strip_accents(s).upper()
    s = s.replace('µ', 'U').replace('μ', 'U')
    s = re.sub(r'[/\\|,;:+()\[\]{}]', ' ', s)
    s = re.sub(r'[^A-Z0-9.%\s-]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def compact(s):
    return re.sub(r'\s+', '', norm_text(s))

def tokens(s):
    return [t for t in norm_text(s).split() if t and t not in STOPWORDS]

def safe_num(x):
    if pd.isna(x): return 0.0
    if isinstance(x, str):
        x = x.replace('\xa0',' ').replace(' ', '').replace(',', '.')
    try: return float(x)
    except Exception: return 0.0

# ---------- 3) DOSAGE PARSING ----------
# Converts common dosage strings to normalized comparable values.
# Example: 1G -> 1000 mg ; 0.5G -> 500 mg ; 5MG/ML stays as mg_per_ml.

def parse_dosage_units(text):
    text0 = norm_text(text).replace(',', '.')
    if not text0: return []
    out = []
    # normalize IU/UI
    text0 = text0.replace(' UI', ' IU')
    patterns = [
        (r'(\d+(?:\.\d+)?)\s*(MG|G|MCG|UG|µG|IU|UI|ML|%)\s*/\s*(\d+(?:\.\d+)?)?\s*(ML|L|DOSE|PUFF|SACHET|COMP|CP)?', 'ratio'),
        (r'(\d+(?:\.\d+)?)\s*(MG|G|MCG|UG|µG|IU|UI|ML|%)', 'single'),
    ]
    for pat, kind in patterns:
        for m in re.finditer(pat, text0):
            val = float(m.group(1)); unit = m.group(2).replace('UI','IU').replace('UG','MCG').replace('µG','MCG')
            denom_val = None; denom_unit = None
            if kind == 'ratio':
                denom_val = m.group(3)
                denom_unit = m.group(4)
                denom_val = float(denom_val) if denom_val else 1.0
                denom_unit = denom_unit or ''
            # convert mass to mg basis when possible
            val_mg = None
            if unit == 'G': val_mg = val * 1000
            elif unit == 'MG': val_mg = val
            elif unit == 'MCG': val_mg = val / 1000
            out.append({
                'raw': m.group(0), 'value': val, 'unit': unit,
                'value_mg': val_mg,
                'denom_value': denom_val, 'denom_unit': denom_unit,
                'kind': kind
            })
    # unique by raw
    unique = []
    seen = set()
    for d in out:
        k = (round(d.get('value_mg') or d['value'],6), d['unit'], d.get('denom_value'), d.get('denom_unit'))
        if k not in seen:
            seen.add(k); unique.append(d)
    return unique

def dosage_query_variants(q):
    qn = norm_text(q).replace(',', '.')
    if not qn: return []
    # If user types only "1", include 1g and 1000mg logic.
    vals = parse_dosage_units(qn)
    if not vals and re.fullmatch(r'\d+(?:\.\d+)?', qn):
        v = float(qn)
        vals = [
            {'raw': qn, 'value': v, 'unit': 'G', 'value_mg': v*1000, 'kind':'single'},
            {'raw': qn, 'value': v, 'unit': 'MG', 'value_mg': v, 'kind':'single'},
        ]
    return vals

def dosage_match_score(query, candidate_text):
    """0-100. If query empty: 100. Strong if same mg basis or direct string."""
    if not str(query).strip(): return 100
    qvars = dosage_query_variants(query)
    cvars = parse_dosage_units(candidate_text)
    cand_norm = norm_text(candidate_text)
    qnorm = norm_text(query)
    if qnorm and qnorm in cand_norm: return 96
    if not qvars or not cvars: return fuzz.partial_ratio(qnorm, cand_norm)
    best = 0
    for q in qvars:
        for c in cvars:
            # Compare mg basis if possible
            if q.get('value_mg') is not None and c.get('value_mg') is not None:
                if abs(q['value_mg'] - c['value_mg']) < 1e-6:
                    best = max(best, 100)
                else:
                    rel = abs(q['value_mg'] - c['value_mg']) / max(q['value_mg'], c['value_mg'], 1e-9)
                    best = max(best, max(0, 100 - rel*200))
            # Compare same unit values
            if q.get('unit') == c.get('unit') and abs(q.get('value',0)-c.get('value',-999)) < 1e-6:
                best = max(best, 95)
            # Denominator if query included ratio
            if q.get('denom_unit') and c.get('denom_unit'):
                if q.get('denom_unit') == c.get('denom_unit'):
                    best += 3
    return min(100, best)

# ---------- 4) FORM NORMALIZATION ----------
def canonical_form(s):
    ns = norm_text(s)
    if not ns: return ''
    for canon, arr in FORM_SYNONYMS.items():
        for a in arr:
            if norm_text(a) in ns:
                return canon
    return ns

# ---------- 5) LOAD DATA ----------
def resolve_file(path, fallback_name):
    p = Path(path)
    if p.exists(): return str(p)
    # search in /content and /mnt/data
    for base in [str(BASE_DIR / 'data'), str(BASE_DIR), '/content', '/mnt/data', '.']:
        matches = list(Path(base).glob(fallback_name))
        if matches: return str(matches[0])
    raise FileNotFoundError(f'File not found: {path} / {fallback_name}. Upload it to Colab or edit CONFIG paths.')

def load_data():
    iqvia_file = resolve_file(CONFIG['IQVIA_FILE'], 'Algeria IQVIA Data March 25.xlsx')
    pch_file = resolve_file(CONFIG['PCH_FILE'], 'Reception2025_copy.xlsx')
    nom_file = resolve_file(CONFIG['NOM_FILE'], 'NOMENCLATURE.VERSION.AVRIL_.2026-.xlsx')

    iqvia = pd.read_excel(iqvia_file, sheet_name=0)
    pch = pd.read_excel(pch_file, sheet_name=0)
    nom_active = pd.read_excel(nom_file, sheet_name='Nomenclature Avril 2026')
    try: nom_non = pd.read_excel(nom_file, sheet_name='Non Renouvelés ')
    except Exception: nom_non = pd.DataFrame()
    try: nom_ret = pd.read_excel(nom_file, sheet_name='Retraits')
    except Exception: nom_ret = pd.DataFrame()

    return iqvia, pch, nom_active, nom_non, nom_ret

# ---------- 6) STANDARDIZE TABLES ----------
def prep_nomenclature(nom_active, nom_non=None, nom_ret=None):
    frames = []
    for df, src in [(nom_active, 'ACTIVE'), (nom_non, 'NON_RENOUVELE'), (nom_ret, 'RETRAIT')]:
        if df is None or df.empty: continue
        x = df.copy()
        x['SOURCE_NOMENCLATURE'] = src
        frames.append(x)
    nom = pd.concat(frames, ignore_index=True, sort=False)
    col = lambda c: c if c in nom.columns else None
    rename = {
        'DENOMINATION COMMUNE INTERNATIONALE':'DCI',
        'NOM DE MARQUE':'BRAND',
        'FORME':'FORME',
        'DOSAGE':'DOSAGE',
        'CONDITIONNEMENT':'CONDITIONNEMENT',
        "LABORATOIRES DETENTEUR DE LA DECISION D'ENREGISTREMENT":'LABORATOIRE',
        'STATUT':'STATUT',
        'TYPE':'TYPE',
        'P1':'P1', 'P2':'P2', 'LISTE':'LISTE', 'CODE':'CODE'
    }
    nom = nom.rename(columns={k:v for k,v in rename.items() if k in nom.columns})
    for c in ['DCI','BRAND','FORME','DOSAGE','CONDITIONNEMENT','LABORATOIRE','STATUT','TYPE','P1','P2','LISTE','CODE']:
        if c not in nom.columns: nom[c] = ''
    nom['DCI_NORM'] = nom['DCI'].map(norm_text)
    nom['BRAND_NORM'] = nom['BRAND'].map(norm_text)
    nom['FORME_NORM'] = nom['FORME'].map(canonical_form)
    nom['DOSAGE_NORM_TEXT'] = nom['DOSAGE'].map(norm_text)
    nom['LAB_NORM'] = nom['LABORATOIRE'].map(norm_text)
    nom['STATUS_NORM'] = nom['STATUT'].map(norm_text)
    nom['PRODUCT_FULL'] = (nom['BRAND'].fillna('').astype(str)+' '+nom['FORME'].fillna('').astype(str)+' '+nom['DOSAGE'].fillna('').astype(str)+' '+nom['CONDITIONNEMENT'].fillna('').astype(str)).str.strip()
    return nom

def prep_iqvia(iqvia):
    x = iqvia.copy()
    x = x.rename(columns={
        'ATC4':'THERAPEUTIC_CLASS', 'PRODUIT':'BRAND', 'PRESENTATION':'PRESENTATION',
        'MOLECULE':'MOLECULE', 'LABORATOIRE':'LABORATOIRE'
    })
    for c in ['THERAPEUTIC_CLASS','BRAND','PRESENTATION','MOLECULE','LABORATOIRE']:
        if c not in x.columns: x[c]=''
    x['MOLECULE_NORM'] = x['MOLECULE'].map(norm_text)
    x['BRAND_NORM'] = x['BRAND'].map(norm_text)
    x['PRES_NORM'] = x['PRESENTATION'].map(norm_text)
    x['FORME_NORM'] = x['PRESENTATION'].map(canonical_form)
    x['LAB_NORM'] = x['LABORATOIRE'].map(norm_text)
    x['PRODUCT_FULL'] = (x['BRAND'].fillna('').astype(str)+' '+x['PRESENTATION'].fillna('').astype(str)).str.strip()
    # choose columns
    period = CONFIG['IQVIA_PERIOD'].upper()
    if period == 'MAT':
        x['MARKET_VOLUME'] = x.get('MAT Mar 2025\nUNITES', 0).map(safe_num) if hasattr(x.get('MAT Mar 2025\nUNITES', 0),'map') else 0
        x['MARKET_VALUE_DZD'] = x.get('MAT Mar 2025\nVALEURS', 0).map(safe_num) if hasattr(x.get('MAT Mar 2025\nVALEURS', 0),'map') else 0
    elif period == 'YTD':
        x['MARKET_VOLUME'] = x.get('YTD Mar 2025\nUNITES', 0).map(safe_num)
        x['MARKET_VALUE_DZD'] = x.get('YTD Mar 2025\nVALEURS', 0).map(safe_num)
    else:
        x['MARKET_VOLUME'] = x.get('Mar 2025\nUNITES', 0).map(safe_num)
        x['MARKET_VALUE_DZD'] = x.get('Mar 2025\nVALEURS', 0).map(safe_num)
    x['SOURCE_MARKET'] = 'IQVIA VILLE'
    x['DEVISING'] = 'DZD'
    x['MARKET_VALUE_USD'] = x['MARKET_VALUE_DZD'] / CONFIG['DZD_PER_USD']
    return x

def prep_pch(pch):
    x = pch.copy()
    x = x.rename(columns={
        'GAMME':'GAMME', 'DESI_CLASSE':'THERAPEUTIC_CLASS', 'NOM_FOUR':'LABORATOIRE',
        'DESI_PRO':'PRODUCT_FULL', 'CODE_COND':'CONDITIONNEMENT', 'QTE':'QTE',
        'ROUND(P.COUT_UNIT_ACHAT,2)':'UNIT_PRICE', 'CODE_MON':'DEVISE', 'DATESTOCKAGE':'DATESTOCKAGE', 'TYPE_RECEP':'TYPE_RECEP'
    })
    for c in ['GAMME','THERAPEUTIC_CLASS','LABORATOIRE','PRODUCT_FULL','CONDITIONNEMENT','QTE','UNIT_PRICE','DEVISE']:
        if c not in x.columns: x[c]=''
    x['TEXT_NORM'] = x['PRODUCT_FULL'].map(norm_text)
    x['FORME_NORM'] = x['PRODUCT_FULL'].map(canonical_form)
    x['LAB_NORM'] = x['LABORATOIRE'].map(norm_text)
    x['QTE'] = x['QTE'].map(safe_num)
    x['UNIT_PRICE'] = x['UNIT_PRICE'].map(safe_num)
    x['MARKET_VALUE_ORIG'] = x['QTE'] * x['UNIT_PRICE']
    x['DEVISE_NORM'] = x['DEVISE'].fillna('DA').astype(str).str.upper().str.strip()
    x['FX_TO_DZD'] = x['DEVISE_NORM'].map(CONFIG['FX_TO_DZD']).fillna(np.nan)
    x['MARKET_VALUE_DZD'] = x['MARKET_VALUE_ORIG'] * x['FX_TO_DZD']
    x['MARKET_VALUE_USD'] = x['MARKET_VALUE_DZD'] / CONFIG['DZD_PER_USD']
    x['MARKET_VOLUME'] = x['QTE']
    x['SOURCE_MARKET'] = 'PCH HOSPITALIER'
    return x

# ---------- 7) SMART MATCHING ----------
# V4 pharma-safe matching philosophy:
# 1) DCI matching is STRICT and molecule-aware.
# 2) Product-label fuzzy matching is only used as fallback, never as the first decision layer.
# 3) Similar suffixes such as -tegravir must NOT create false positives.
#    Example: raltegravir must not return dolutegravir / bictegravir.

MOLECULE_CONFUSION_BLACKLIST = {
    'RALTEGRAVIR': {'DOLUTEGRAVIR', 'BICTEGRAVIR', 'ELVITEGRAVIR'},
    'DOLUTEGRAVIR': {'RALTEGRAVIR', 'BICTEGRAVIR', 'ELVITEGRAVIR'},
    'BICTEGRAVIR': {'RALTEGRAVIR', 'DOLUTEGRAVIR', 'ELVITEGRAVIR'},
    'ELVITEGRAVIR': {'RALTEGRAVIR', 'DOLUTEGRAVIR', 'BICTEGRAVIR'},
}

MOLECULE_SUFFIXES_REQUIRING_EXACT_TOKEN = (
    'TEGRAVIR', 'VIR', 'MAB', 'TINIB', 'STATIN', 'PRIL', 'SARTAN', 'OLOL', 'CAINE', 'AZOLE', 'CYCLINE'
)

def query_molecule_tokens(query_dci):
    q = norm_text(query_dci)
    return [t for t in tokens(q) if len(t) >= 3]


def _regex_word_token(tok):
    tok = re.escape(norm_text(tok))
    return rf'(?<![A-Z0-9]){tok}(?![A-Z0-9])'


def _contains_all_query_tokens_series(series_norm, query_dci):
    qtokens = query_molecule_tokens(query_dci)
    if not qtokens:
        return pd.Series(False, index=series_norm.index)
    mask = pd.Series(True, index=series_norm.index)
    for tok in qtokens:
        mask &= series_norm.fillna('').astype(str).str.contains(_regex_word_token(tok), regex=True, na=False)
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
    # Single molecule-like queries are dangerous for partial fuzzy matching.
    # Raltegravir vs dolutegravir is the exact bug this prevents.
    if len(qts) == 1 and any(qts[0].endswith(suf) for suf in MOLECULE_SUFFIXES_REQUIRING_EXACT_TOKEN):
        return True
    return False


def dci_match_score(query_dci, candidate):
    """Strict DCI-vs-DCI score. Returns 0-100.
    Exact/token containment is privileged. Fuzzy is only fallback for typos.
    """
    q = norm_text(query_dci); c = norm_text(candidate)
    if not q or not c:
        return 0
    if q == c:
        return 100
    qt, ct = set(query_molecule_tokens(q)), _candidate_tokens(c)
    if qt and qt.issubset(ct):
        return 99
    if _is_blacklisted_molecule_pair(q, c):
        return 0
    # If user typed a precise antiviral / mab / etc, do not allow suffix-based partial matches.
    if _requires_exact_token(q):
        # Allow only very high whole-token typo correction against each token, not partial substring.
        best_token = max([fuzz.WRatio(t, q) for t in ct] or [0])
        return best_token if best_token >= 94 else 0
    score = max(fuzz.WRatio(q, c), fuzz.token_sort_ratio(q, c), fuzz.token_set_ratio(q, c))
    return score if score >= 90 else 0


def text_product_match_score(query_dci, product_text):
    """Strict DCI-vs-product-label score for PCH labels.
    The DCI must appear as a real token first. Fuzzy fallback only corrects typos.
    """
    q = norm_text(query_dci); t = norm_text(product_text)
    if not q or not t:
        return 0
    qt, tt = set(query_molecule_tokens(q)), _candidate_tokens(t)
    if qt and qt.issubset(tt):
        return 99
    if _is_blacklisted_molecule_pair(q, t):
        return 0
    if _requires_exact_token(q):
        best_token = max([fuzz.WRatio(qtok, ttok) for qtok in qt for ttok in tt] or [0])
        return best_token if best_token >= 95 else 0
    # Multi-word or less risky fallback: token-level, not partial full-string.
    best_token = max([fuzz.WRatio(qtok, ttok) for qtok in qt for ttok in tt] or [0])
    return best_token if best_token >= 92 else 0


def apply_filters(df, dosage=None, formes=None, labs=None, statuts=None, source='nom'):
    x = df.copy()
    if dosage:
        coltxt = 'DOSAGE' if source == 'nom' else ('PRESENTATION' if source == 'iqvia' else 'PRODUCT_FULL')
        if isinstance(dosage, (list, tuple, set)):
            dosage_list = [str(d).strip() for d in dosage if str(d).strip()]
        else:
            dosage_list = [str(dosage).strip()] if str(dosage).strip() else []
        if dosage_list:
            x['_DOSAGE_SCORE'] = x[coltxt].fillna('').astype(str).map(lambda s: max([dosage_match_score(d, s) for d in dosage_list] or [0]))
            x = x[x['_DOSAGE_SCORE'] >= 82]
        else:
            x['_DOSAGE_SCORE'] = 100
    else:
        x['_DOSAGE_SCORE'] = 100
    if formes:
        forms_norm = set(canonical_form(f) for f in formes if str(f).strip())
        if forms_norm:
            x = x[x['FORME_NORM'].isin(forms_norm)]
    if labs:
        labs_norm = [norm_text(l) for l in labs if str(l).strip()]
        if labs_norm:
            # The lab field comes from a controlled dropdown, so exact normalized match first.
            lab_set = set(labs_norm)
            x = x[x['LAB_NORM'].isin(lab_set)]
    if statuts and source == 'nom':
        st = set(norm_text(s) for s in statuts if str(s).strip())
        if st:
            x = x[x['STATUS_NORM'].isin(st)]
    return x


def _strict_filter_by_dci_column(df, dci_list, col_norm):
    frames=[]
    for dci in dci_list:
        tmp = df.copy()
        tmp['_QUERY_DCI'] = dci
        exact_mask = _contains_all_query_tokens_series(tmp[col_norm], dci)
        if exact_mask.any():
            tmp = tmp[exact_mask].copy()
            tmp['_DCI_SCORE'] = tmp[col_norm].map(lambda s: dci_match_score(dci, s))
            tmp['_DCI_SCORE'] = tmp['_DCI_SCORE'].replace(0, 99)
        else:
            tmp['_DCI_SCORE'] = tmp[col_norm].map(lambda s: dci_match_score(dci, s))
            tmp = tmp[tmp['_DCI_SCORE'] >= max(CONFIG['FUZZY_DCI_THRESHOLD'], 90)]
        frames.append(tmp)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates()


def filter_nomenclature(nom, dci_list, dosage=None, formes=None, labs=None, statuts=None):
    tmp = _strict_filter_by_dci_column(nom, dci_list, 'DCI_NORM')
    if tmp.empty:
        return tmp
    return apply_filters(tmp, dosage, formes, labs, statuts, source='nom')


def filter_iqvia(iqvia, dci_list, dosage=None, formes=None, labs=None):
    tmp = _strict_filter_by_dci_column(iqvia, dci_list, 'MOLECULE_NORM')
    if tmp.empty:
        return tmp
    return apply_filters(tmp, dosage, formes, labs, None, source='iqvia')


def filter_pch(pch, dci_list, dosage=None, formes=None, labs=None):
    frames=[]
    for dci in dci_list:
        tmp = pch.copy()
        tmp['_QUERY_DCI'] = dci
        exact_mask = _contains_all_query_tokens_series(tmp['TEXT_NORM'], dci)
        if exact_mask.any():
            tmp = tmp[exact_mask].copy()
            tmp['_DCI_SCORE'] = tmp['TEXT_NORM'].map(lambda s: text_product_match_score(dci, s))
            tmp['_DCI_SCORE'] = tmp['_DCI_SCORE'].replace(0, 99)
        else:
            tmp['_DCI_SCORE'] = tmp['TEXT_NORM'].map(lambda s: text_product_match_score(dci, s))
            tmp = tmp[tmp['_DCI_SCORE'] >= 92]
        tmp = apply_filters(tmp, dosage, formes, labs, None, source='pch')
        frames.append(tmp)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates()

# ---------- 8) AGGREGATION / MARKET SHARE ----------
def summarize_market(market_df, source_name):
    if market_df is None or market_df.empty:
        return pd.DataFrame()
    x = market_df.copy()
    group_cols = ['_QUERY_DCI','PRODUCT_FULL','LABORATOIRE','SOURCE_MARKET']
    if source_name == 'IQVIA VILLE':
        # include class/presentation exact
        agg = x.groupby(group_cols, dropna=False).agg(
            Therapeutic_Class=('THERAPEUTIC_CLASS','first'),
            Market_Size_Volume=('MARKET_VOLUME','sum'),
            Market_Size_Value_DZD=('MARKET_VALUE_DZD','sum'),
            Market_Size_Value_USD=('MARKET_VALUE_USD','sum'),
            Avg_Match_Score=('_DCI_SCORE','mean'),
            Dosage_Match_Score=('_DOSAGE_SCORE','mean')
        ).reset_index()
        agg['Currency'] = 'DZD'
    else:
        agg = x.groupby(group_cols, dropna=False).agg(
            Therapeutic_Class=('THERAPEUTIC_CLASS','first'),
            Market_Size_Volume=('MARKET_VOLUME','sum'),
            Market_Size_Value_Orig=('MARKET_VALUE_ORIG','sum'),
            Market_Size_Value_DZD=('MARKET_VALUE_DZD','sum'),
            Market_Size_Value_USD=('MARKET_VALUE_USD','sum'),
            Currency=('DEVISE_NORM', lambda s: ', '.join(sorted(set(map(str, s.dropna()))))[:60]),
            Avg_Match_Score=('_DCI_SCORE','mean'),
            Dosage_Match_Score=('_DOSAGE_SCORE','mean')
        ).reset_index()
    agg['Average_Price_Per_Box_DZD'] = np.where(agg['Market_Size_Volume']>0, agg['Market_Size_Value_DZD']/agg['Market_Size_Volume'], np.nan)
    return agg

def build_opportunity_table(nom_matches, iqvia_matches, pch_matches):
    iq = summarize_market(iqvia_matches, 'IQVIA VILLE')
    ph = summarize_market(pch_matches, 'PCH HOSPITALIER')
    market = pd.concat([iq, ph], ignore_index=True, sort=False)
    if market.empty:
        return pd.DataFrame(), market, pd.DataFrame()

    # Main aggregation by query DCI and source; player table by lab
    main_rows = []
    for (qdci, source), g in market.groupby(['_QUERY_DCI','SOURCE_MARKET'], dropna=False):
        lab = g.groupby('LABORATOIRE', dropna=False).agg(
            Value_DZD=('Market_Size_Value_DZD','sum'),
            Volume=('Market_Size_Volume','sum')
        ).reset_index().sort_values('Value_DZD', ascending=False)
        total_value = lab['Value_DZD'].sum()
        total_vol = lab['Volume'].sum()
        lab['Market_Share'] = np.where(total_value>0, lab['Value_DZD']/total_value, np.nan)
        top = lab.head(5).reset_index(drop=True)
        product_examples = '; '.join(g.sort_values('Market_Size_Value_DZD', ascending=False)['PRODUCT_FULL'].dropna().astype(str).head(5).tolist())
        nom_sub = nom_matches[nom_matches['_QUERY_DCI'].map(norm_text)==norm_text(qdci)] if nom_matches is not None and not nom_matches.empty else pd.DataFrame()
        dossier = 'Available' if not nom_sub.empty else 'Not found in nomenclature'
        statuts = ', '.join(sorted(set(nom_sub['STATUT'].dropna().astype(str)))) if not nom_sub.empty and 'STATUT' in nom_sub else ''
        types = ', '.join(sorted(set(nom_sub['TYPE'].dropna().astype(str)))) if not nom_sub.empty and 'TYPE' in nom_sub else ''
        row = {
            'DCI searched': qdci,
            'Product': product_examples,
            'Dossier availability': dossier,
            'Nomenclature status': statuts,
            'Nomenclature type': types,
            'Market source': source,
            'Market size in Volume': total_vol,
            'Market size in Value DZD': total_value,
            'Market size in Value USD': total_value / CONFIG['DZD_PER_USD'],
            'Average Price Per Box DZD': total_value/total_vol if total_vol else np.nan,
            'Average Price Per Box USD': (total_value/CONFIG['DZD_PER_USD'])/total_vol if total_vol else np.nan,
            'Number of Players': int(lab['LABORATOIRE'].nunique()),
        }
        for i in range(5):
            row[f'Player {i+1}'] = top.loc[i,'LABORATOIRE'] if i < len(top) else ''
            row[f'Player {i+1} Market Share'] = top.loc[i,'Market_Share'] if i < len(top) else np.nan
        main_rows.append(row)
    main = pd.DataFrame(main_rows).sort_values(['DCI searched','Market source'])
    return main, market, nom_matches

# ---------- 9) EXCEL EXPORT ----------
def export_excel(main, market_detail, nom_detail, output_file=None):
    output_file = output_file or CONFIG['OUTPUT_FILE']
    with pd.ExcelWriter(output_file, engine='xlsxwriter') as writer:
        main.to_excel(writer, sheet_name='Opportunity Summary', index=False)
        market_detail.to_excel(writer, sheet_name='Market Detail', index=False)
        if nom_detail is not None and not nom_detail.empty:
            cols = [c for c in ['_QUERY_DCI','DCI','BRAND','FORME','DOSAGE','CONDITIONNEMENT','LABORATOIRE','STATUT','TYPE','P1','P2','LISTE','SOURCE_NOMENCLATURE','_DCI_SCORE','_DOSAGE_SCORE'] if c in nom_detail.columns]
            nom_detail[cols].to_excel(writer, sheet_name='Nomenclature Matches', index=False)
        else:
            pd.DataFrame().to_excel(writer, sheet_name='Nomenclature Matches', index=False)
        wb = writer.book
        header_fmt = wb.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#0F766E', 'border':1, 'align':'center', 'valign':'vcenter'})
        orange_fmt = wb.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#F97316', 'border':1, 'align':'center', 'valign':'vcenter'})
        money_fmt = wb.add_format({'num_format': '#,##0'})
        pct_fmt = wb.add_format({'num_format': '0.0%'})
        num_fmt = wb.add_format({'num_format': '#,##0'})
        for sheet_name, df in [('Opportunity Summary',main), ('Market Detail',market_detail), ('Nomenclature Matches',nom_detail if nom_detail is not None else pd.DataFrame())]:
            ws = writer.sheets[sheet_name]
            ws.freeze_panes(1,0)
            ws.autofilter(0,0,max(len(df),1),max(len(df.columns)-1,0))
            for col_idx, col in enumerate(df.columns):
                width = min(max(12, int(max([len(str(col))] + [len(str(x)) for x in df[col].head(200).fillna('').astype(str)])*1.05)), 45)
                ws.set_column(col_idx, col_idx, width)
                fmt = orange_fmt if 'Market Share' in str(col) or 'Average Price' in str(col) else header_fmt
                ws.write(0, col_idx, col, fmt)
                if 'Value' in str(col) or 'Price' in str(col) or 'Volume' in str(col):
                    ws.set_column(col_idx, col_idx, width, money_fmt)
                if 'Share' in str(col):
                    ws.set_column(col_idx, col_idx, width, pct_fmt)
        # conditional formatting for scores
        for sheet_name in ['Market Detail','Nomenclature Matches']:
            ws = writer.sheets[sheet_name]
            df = market_detail if sheet_name=='Market Detail' else (nom_detail if nom_detail is not None else pd.DataFrame())
            for col in ['Avg_Match_Score','_DCI_SCORE','Dosage_Match_Score','_DOSAGE_SCORE']:
                if col in df.columns:
                    cidx = list(df.columns).index(col)
                    ws.conditional_format(1,cidx,max(len(df),1),cidx, {'type':'3_color_scale'})
    return output_file

# ---------- 10) MASTER ANALYSIS FUNCTION ----------
def run_market_analysis(
    dci_input,
    dosage=None,
    formes=None,
    labs=None,
    statuts=None,
    markets=None,
    output_file=None,
    verbose=True
):
    """
    dci_input: string comma-separated or list, e.g. 'paracetamol, amoxicilline'
    dosage: optional string, e.g. '1', '500 mg', '1 g', '5 mg/ml'
    formes: optional list, e.g. ['COMPRIME', 'SOLUTION INJECTABLE']
    labs: optional list
    statuts: optional list ['F','I']
    markets: optional list ['IQVIA VILLE','PCH HOSPITALIER']; None = both
    """
    if isinstance(dci_input, str):
        dci_list = [x.strip() for x in re.split(r'[,;\n]+', dci_input) if x.strip()]
    else:
        dci_list = [str(x).strip() for x in dci_input if str(x).strip()]
    if not dci_list: raise ValueError('Give at least one DCI.')
    formes = formes or []
    labs = labs or []
    statuts = statuts or []
    markets = markets or ['IQVIA VILLE','PCH HOSPITALIER']

    iqvia_raw, pch_raw, nom_active, nom_non, nom_ret = load_data()
    nom = prep_nomenclature(nom_active, nom_non, nom_ret)
    iqvia = prep_iqvia(iqvia_raw)
    pch = prep_pch(pch_raw)

    nom_matches = filter_nomenclature(nom, dci_list, dosage, formes, labs, statuts)
    iqvia_matches = filter_iqvia(iqvia, dci_list, dosage, formes, labs) if 'IQVIA VILLE' in markets else pd.DataFrame()
    pch_matches = filter_pch(pch, dci_list, dosage, formes, labs) if 'PCH HOSPITALIER' in markets else pd.DataFrame()

    main, market_detail, nom_detail = build_opportunity_table(nom_matches, iqvia_matches, pch_matches)
    output = export_excel(main, market_detail, nom_detail, output_file or CONFIG['OUTPUT_FILE'])

    if verbose:
        print('✅ Analysis complete')
        print(f'Input DCI: {dci_list}')
        print(f'Nomenclature matches: {len(nom_matches):,}')
        print(f'IQVIA matches: {len(iqvia_matches):,}')
        print(f'PCH matches: {len(pch_matches):,}')
        print(f'Excel exported: {output}')
        print(main.head())
    return main, market_detail, nom_detail, output



# ---------- 11) STREAMLIT FACET HELPERS ----------
def parse_dci_input(dci_input):
    if isinstance(dci_input, str):
        return [x.strip() for x in re.split(r'[,;\n]+', dci_input) if x.strip()]
    return [str(x).strip() for x in (dci_input or []) if str(x).strip()]


def load_prepared_data():
    iqvia_raw, pch_raw, nom_active, nom_non, nom_ret = load_data()
    return prep_nomenclature(nom_active, nom_non, nom_ret), prep_iqvia(iqvia_raw), prep_pch(pch_raw)


def safe_unique(values, limit=1000):
    """Robust unique extractor for Series/DataFrame/list/array/scalars."""
    if values is None:
        return []
    if isinstance(values, pd.DataFrame):
        raw = values.to_numpy().ravel().tolist()
    elif isinstance(values, pd.Series):
        raw = values.to_numpy().ravel().tolist()
    elif isinstance(values, (list, tuple, set, np.ndarray)):
        raw = np.array(list(values), dtype=object).ravel().tolist()
    else:
        raw = [values]
    vals = []
    seen = set()
    for v in raw:
        if isinstance(v, (list, tuple, set, np.ndarray)):
            iterable = np.array(list(v), dtype=object).ravel().tolist()
        else:
            iterable = [v]
        for item in iterable:
            if pd.isna(item):
                continue
            sv = str(item).strip()
            if not sv or sv.lower() in {'nan','none','nat'}:
                continue
            if sv not in seen:
                seen.add(sv)
                vals.append(sv)
    return sorted(vals)[:limit]


def build_option_universe(dci_text, selected_markets, nom, iqvia, pch):
    dci_list = parse_dci_input(dci_text)
    selected_markets = selected_markets or ['IQVIA VILLE', 'PCH HOSPITALIER']
    frames = []
    if not dci_list:
        return pd.DataFrame(columns=['source','dci','dosage','forme','lab','statut','market','label'])
    nm = filter_nomenclature(nom, dci_list)
    if nm is not None and not nm.empty:
        frames.append(pd.DataFrame({
            'source': 'NOMENCLATURE', 'dci': nm['_QUERY_DCI'].astype(str),
            'dosage': nm['DOSAGE'].fillna('').astype(str), 'forme': nm['FORME_NORM'].fillna('').astype(str),
            'lab': nm['LABORATOIRE'].fillna('').astype(str), 'statut': nm['STATUT'].fillna('').astype(str),
            'market': 'NOMENCLATURE', 'label': nm['PRODUCT_FULL'].fillna('').astype(str)}))
    if 'IQVIA VILLE' in selected_markets:
        iq = filter_iqvia(iqvia, dci_list)
        if iq is not None and not iq.empty:
            frames.append(pd.DataFrame({
                'source': 'IQVIA VILLE', 'dci': iq['_QUERY_DCI'].astype(str),
                'dosage': iq['PRESENTATION'].fillna('').astype(str), 'forme': iq['FORME_NORM'].fillna('').astype(str),
                'lab': iq['LABORATOIRE'].fillna('').astype(str), 'statut': '',
                'market': 'IQVIA VILLE', 'label': iq['PRODUCT_FULL'].fillna('').astype(str)}))
    if 'PCH HOSPITALIER' in selected_markets:
        ph = filter_pch(pch, dci_list)
        if ph is not None and not ph.empty:
            frames.append(pd.DataFrame({
                'source': 'PCH HOSPITALIER', 'dci': ph['_QUERY_DCI'].astype(str),
                'dosage': ph['PRODUCT_FULL'].fillna('').astype(str), 'forme': ph['FORME_NORM'].fillna('').astype(str),
                'lab': ph['LABORATOIRE'].fillna('').astype(str), 'statut': '',
                'market': 'PCH HOSPITALIER', 'label': ph['PRODUCT_FULL'].fillna('').astype(str)}))
    if not frames:
        return pd.DataFrame(columns=['source','dci','dosage','forme','lab','statut','market','label'])
    u = pd.concat(frames, ignore_index=True, sort=False).fillna('')
    for c in ['dosage','forme','lab','statut','market']:
        u[c+'_NORM'] = u[c].map(norm_text)
    return u.drop_duplicates()


def facet_filter(universe, dosage=None, formes=None, labs=None, statuts=None, markets=None, ignore=None):
    ignore = ignore or set()
    x = universe.copy()
    dosage = list(dosage or []); formes = list(formes or []); labs = list(labs or []); statuts = list(statuts or []); markets = list(markets or [])
    if dosage and 'dosage' not in ignore:
        x = x[x['dosage'].astype(str).map(lambda s: max([dosage_match_score(d, s) for d in dosage] or [0]) >= 82)]
    if formes and 'forme' not in ignore:
        forms_norm = set(canonical_form(f) for f in formes)
        x = x[x['forme'].map(canonical_form).isin(forms_norm)]
    if labs and 'lab' not in ignore:
        labs_norm = [norm_text(l) for l in labs]
        x = x[x['lab_NORM'].map(lambda s: max([fuzz.WRatio(str(s), l) for l in labs_norm] or [0]) >= 86)]
    if statuts and 'statut' not in ignore:
        st = set(norm_text(s) for s in statuts)
        x = x[(x['statut_NORM'].isin(st)) | (x['statut_NORM'].eq(''))]
    if markets and 'market' not in ignore:
        m = set(markets)
        x = x[x['market'].isin(m) | x['market'].eq('NOMENCLATURE')]
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


def export_excel_bytes(main, market_detail, nom_detail):
    from io import BytesIO
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine='xlsxwriter') as writer:
        main.to_excel(writer, sheet_name='Opportunity Summary', index=False)
        market_detail.to_excel(writer, sheet_name='Market Detail', index=False)
        if nom_detail is not None and not nom_detail.empty:
            cols = [c for c in ['_QUERY_DCI','DCI','BRAND','FORME','DOSAGE','CONDITIONNEMENT','LABORATOIRE','STATUT','TYPE','P1','P2','LISTE','SOURCE_NOMENCLATURE','_DCI_SCORE','_DOSAGE_SCORE'] if c in nom_detail.columns]
            nom_detail[cols].to_excel(writer, sheet_name='Nomenclature Matches', index=False)
        wb = writer.book
        header = wb.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#0F172A', 'border': 1, 'align': 'center'})
        accent = wb.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#14B8A6', 'border': 1, 'align': 'center'})
        money = wb.add_format({'num_format': '#,##0'})
        pct = wb.add_format({'num_format': '0.0%'})
        for sheet, df in [('Opportunity Summary', main), ('Market Detail', market_detail), ('Nomenclature Matches', nom_detail if nom_detail is not None else pd.DataFrame())]:
            ws = writer.sheets[sheet]
            ws.freeze_panes(1, 0)
            if len(df.columns):
                ws.autofilter(0, 0, max(len(df), 1), len(df.columns)-1)
            for i, col in enumerate(df.columns):
                width = min(max(12, len(str(col)) + 4), 42)
                ws.write(0, i, col, accent if 'Share' in col or 'Average' in col else header)
                if any(k in str(col) for k in ['Value', 'Price', 'Volume']): ws.set_column(i, i, width, money)
                elif 'Share' in str(col): ws.set_column(i, i, width, pct)
                else: ws.set_column(i, i, width)
    bio.seek(0)
    return bio.getvalue()
