import math
import streamlit as st

BUILD_VERSION = "v4.6 pch-dzd-number-format"


def configure_page() -> None:
    st.set_page_config(
        page_title="Algeria Pharma Market Intelligence",
        page_icon="💊",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def fmt_money(x, decimals=0):
    """Human-readable number with spaces as thousand separators.
    Example: 1234567 -> 1 234 567 ; 12_500_000 -> 12.5 M
    """
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    try:
        x = float(x)
    except Exception:
        return "—"

    def sp(v, d=0):
        return f"{v:,.{d}f}".replace(",", " ")

    if abs(x) >= 1_000_000_000:
        return f"{sp(x/1_000_000_000, 2)} B"
    if abs(x) >= 1_000_000:
        return f"{sp(x/1_000_000, 1)} M"
    if abs(x) >= 1_000:
        return sp(x, decimals)
    return sp(x, decimals)


def format_number_spaces(x, decimals=0):
    """Strict table formatter: no K/M/B abbreviation, just separated thousands."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return ""
    try:
        x = float(x)
    except Exception:
        return x
    return f"{x:,.{decimals}f}".replace(",", " ")


def format_dataframe_for_display(df):
    """Return a display-only copy with readable numbers: 1 234 567.
    Keeps source data untouched for charts and Excel exports.
    """
    import pandas as pd
    if df is None or getattr(df, 'empty', True):
        return df
    x = df.copy()
    for col in x.columns:
        name = str(col).lower()
        numeric = pd.to_numeric(x[col], errors='coerce')
        if numeric.notna().sum() == 0:
            continue
        if 'share' in name or 'part' in name or 'percentage' in name:
            vals = numeric.where(numeric.abs() > 1, numeric * 100)
            x[col] = vals.map(lambda v: "" if pd.isna(v) else f"{v:,.1f}%".replace(",", " "))
        elif any(k in name for k in ['value', 'valeur', 'market', 'price', 'prix', 'volume', 'qte', 'qty', 'unit', 'cout', 'coût', 'usd', 'dzd']):
            decimals = 2 if ('avg' in name or 'average' in name or 'prix' in name or 'price' in name) and 'volume' not in name else 0
            x[col] = numeric.map(lambda v: "" if pd.isna(v) else format_number_spaces(v, decimals))
    return x


def apply_theme() -> None:
    st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

:root {{
  --bg-0: #020617;
  --bg-1: #0f172a;
  --panel: rgba(15,23,42,.74);
  --panel-strong: rgba(15,23,42,.94);
  --border: rgba(148,163,184,.18);
  --border-accent: rgba(45,212,191,.32);
  --text: #F8FAFC;
  --muted: #94A3B8;
  --soft: #CBD5E1;
  --accent: #14B8A6;
  --accent-2: #2563EB;
}}

html, body, [class*="css"] {{font-family: 'Inter', sans-serif;}}
.stApp {{
  background:
    radial-gradient(circle at 8% 8%, rgba(20,184,166,0.20), transparent 28%),
    radial-gradient(circle at 88% 0%, rgba(59,130,246,0.18), transparent 30%),
    linear-gradient(135deg, var(--bg-0) 0%, var(--bg-1) 42%, #111827 100%);
  color: var(--text);
}}
.block-container {{
  padding-top: 1.25rem;
  padding-bottom: 2rem;
  max-width: 1540px;
}}
[data-testid="stSidebar"] {{
  background: rgba(2,6,23,0.86);
  border-right: 1px solid var(--border);
}}
[data-testid="stSidebar"] * {{color: #E5E7EB;}}

.hero {{
  border: 1px solid var(--border-accent);
  background: linear-gradient(135deg, rgba(15,23,42,0.94), rgba(30,41,59,0.70));
  border-radius: 30px;
  padding: 28px 32px;
  box-shadow: 0 24px 90px rgba(0,0,0,.35);
  margin-bottom: 20px;
}}
.hero h1 {{
  font-size: clamp(32px, 5vw, 58px);
  line-height: 1.0;
  margin: 0;
  font-weight: 900;
  letter-spacing: -0.055em;
}}
.hero p {{color: var(--soft); font-size: 16px; margin: 12px 0 0 0; max-width: 1000px;}}
.badge {{
  display: inline-flex;
  gap: 8px;
  align-items:center;
  padding: 7px 11px;
  border-radius: 999px;
  background: rgba(20,184,166,.12);
  border: 1px solid rgba(45,212,191,.25);
  color:#99F6E4;
  font-weight:800;
  font-size: 12px;
  margin-bottom: 12px;
}}
.small-muted {{color:var(--muted); font-size: 13px;}}

.card, .metric-card {{
  background: linear-gradient(180deg, rgba(15,23,42,.92), rgba(15,23,42,.58));
  border: 1px solid var(--border);
  border-radius: 22px;
  box-shadow: 0 16px 45px rgba(0,0,0,.25);
}}
.card {{padding: 18px;}}
.metric-card {{padding: 18px; min-height: 118px; border-color: rgba(45,212,191,.18);}}
.metric-label {{font-size: 12px; color: var(--muted); text-transform: uppercase; font-weight: 900; letter-spacing: .08em;}}
.metric-value {{font-size: clamp(22px, 3vw, 34px); color: var(--text); font-weight: 900; margin-top: 8px; letter-spacing: -0.035em;}}
.metric-sub {{font-size: 12px; color: #A7F3D0; margin-top: 4px;}}

.stButton>button, .stDownloadButton>button {{
  border: 1px solid rgba(45,212,191,.35);
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  color: white;
  border-radius: 16px;
  padding: .72rem 1rem;
  font-weight: 900;
  box-shadow: 0 12px 35px rgba(20,184,166,.18);
  min-height: 44px;
}}
.stButton>button:hover, .stDownloadButton>button:hover {{border-color: #99F6E4; transform: translateY(-1px);}}
[data-testid="stMetricValue"] {{color: var(--text);}}

/* Inputs */
div[data-baseweb="select"] > div {{background-color: rgba(15,23,42,.80); border-color: rgba(148,163,184,.25); border-radius: 14px;}}
input, textarea {{background-color: rgba(15,23,42,.88) !important; color: var(--text) !important; border-radius: 14px !important;}}
.stTextInput input {{min-height: 42px;}}
.stMultiSelect [data-baseweb="tag"] {{background: rgba(20,184,166,.18); border: 1px solid rgba(45,212,191,.25);}}

/* Tabs and dataframes */
.stTabs [data-baseweb="tab-list"] {{gap: 8px; overflow-x: auto; flex-wrap: nowrap;}}
.stTabs [data-baseweb="tab"] {{background: rgba(15,23,42,.60); border-radius: 14px; padding: 10px 16px; border:1px solid rgba(148,163,184,.16); white-space: nowrap;}}
.stDataFrame {{border-radius: 18px; overflow:hidden;}}
div[data-testid="stDataFrame"] {{overflow-x: auto;}}

/* Better mobile behaviour: Streamlit columns stack, tables scroll, buttons full width */
@media (max-width: 900px) {{
  .block-container {{padding-left: .85rem !important; padding-right: .85rem !important; padding-top: .85rem !important;}}
  .hero {{padding:20px; border-radius:24px;}}
  .hero h1 {{font-size: 34px !important; line-height: 1.02 !important;}}
  .hero p {{font-size: 14px;}}
  .metric-card {{min-height: 92px; padding: 14px; margin-bottom: 10px;}}
  .metric-value {{font-size: 24px;}}
  div[data-testid="stHorizontalBlock"] {{flex-direction: column !important; gap: .65rem !important;}}
  div[data-testid="column"] {{width: 100% !important; flex: 1 1 100% !important; min-width: 100% !important;}}
  .stButton>button, .stDownloadButton>button {{width: 100% !important;}}
  [data-testid="stSidebar"] {{min-width: 92vw !important; max-width: 92vw !important;}}
  .stTabs [data-baseweb="tab"] {{padding: 9px 12px; font-size: 13px;}}
}}

@media (max-width: 520px) {{
  .block-container {{padding-left: .6rem !important; padding-right: .6rem !important;}}
  .hero {{padding: 16px; border-radius: 20px; margin-bottom: 14px;}}
  .hero h1 {{font-size: 28px !important; letter-spacing: -0.04em;}}
  .hero p {{font-size: 12.5px;}}
  .badge {{font-size: 10px; padding: 6px 9px;}}
  h1 {{font-size: 1.65rem !important;}}
  h2, h3 {{font-size: 1.15rem !important;}}
  .metric-label {{font-size: 10.5px;}}
  .metric-value {{font-size: 22px;}}
  .stButton>button, .stDownloadButton>button {{border-radius: 14px; padding: .65rem .8rem; min-height: 42px;}}
}}
</style>
""", unsafe_allow_html=True)
