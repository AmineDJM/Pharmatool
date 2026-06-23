"""Design system: page config, CSS theme, number formatting and reusable
HTML components (KPI cards, growth pills, section headers, chips).
Edit visuals here only — pages import these helpers."""

import math
import streamlit as st

BUILD_VERSION = "v5.0 · IQVIA 2026 · competition-suite"

# Brand palette
ACCENT = "#14B8A6"
ACCENT_2 = "#2563EB"
GOOD = "#34D399"
BAD = "#F87171"
WARN = "#FBBF24"


def configure_page() -> None:
    st.set_page_config(
        page_title="Algeria Pharma Intelligence",
        page_icon="💊",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={"about": "Algeria Pharma Market Intelligence — IQVIA / PCH / Nomenclature."},
    )


# ------------------------------------------------------------
# Number formatting
# ------------------------------------------------------------
def _sp(v, d=0):
    return f"{v:,.{d}f}".replace(",", " ")


def fmt_money(x, currency=""):
    """Compact human-readable money: 12.5 M, 3.9 B, 1 234."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    try:
        x = float(x)
    except Exception:
        return "—"
    pre = f"{currency} " if currency and not currency.startswith("$") else (currency or "")
    if abs(x) >= 1_000_000_000:
        body = f"{_sp(x/1_000_000_000, 2)} B"
    elif abs(x) >= 1_000_000:
        body = f"{_sp(x/1_000_000, 1)} M"
    else:
        body = _sp(x, 0)
    return f"{pre}{body}".strip()


def fmt_int(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    try:
        return _sp(float(x), 0)
    except Exception:
        return "—"


def fmt_pct(x, decimals=1):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    try:
        x = float(x)
    except Exception:
        return "—"
    if abs(x) <= 1.5:  # fractional
        x *= 100
    return f"{x:.{decimals}f}%".replace(".", ",")


def fmt_growth(x, decimals=1):
    """Signed YoY growth, e.g. +12,4% / -3,1%."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    try:
        x = float(x)
    except Exception:
        return "—"
    if abs(x) <= 1.5:
        x *= 100
    sign = "+" if x >= 0 else ""
    return f"{sign}{x:.{decimals}f}%".replace(".", ",")


def growth_tone(x):
    try:
        x = float(x)
    except Exception:
        return "muted"
    if math.isnan(x):
        return "muted"
    return "good" if x >= 0 else "bad"


def format_number_spaces(x, decimals=0):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return ""
    try:
        x = float(x)
    except Exception:
        return x
    return f"{x:,.{decimals}f}".replace(",", " ")


def format_dataframe_for_display(df):
    """Display-only copy with readable numbers. Source data untouched for charts/exports."""
    import pandas as pd
    if df is None or getattr(df, "empty", True):
        return df
    x = df.copy()
    for col in x.columns:
        name = str(col).lower()
        numeric = pd.to_numeric(x[col], errors="coerce")
        if numeric.notna().sum() == 0:
            continue
        if any(k in name for k in ["growth", "croissance", "evolution", "évolution"]):
            vals = numeric.where(numeric.abs() > 1.5, numeric * 100)
            x[col] = vals.map(lambda v: "" if pd.isna(v) else f"{'+' if v >= 0 else ''}{v:,.1f}%".replace(",", " "))
        elif any(k in name for k in ["share", "part", "percentage", "concentration %"]):
            vals = numeric.where(numeric.abs() > 1.5, numeric * 100)
            x[col] = vals.map(lambda v: "" if pd.isna(v) else f"{v:,.1f}%".replace(",", " "))
        elif "hhi" in name:
            x[col] = numeric.map(lambda v: "" if pd.isna(v) else f"{v:,.0f}".replace(",", " "))
        elif any(k in name for k in ["value", "valeur", "market", "price", "prix", "volume", "qte", "qty", "unit", "cout", "coût", "usd", "dzd"]):
            decimals = 2 if ("prix" in name or "price" in name) and "volume" not in name else 0
            x[col] = numeric.map(lambda v: "" if pd.isna(v) else format_number_spaces(v, decimals))
    # Coerce any remaining mixed-type object columns to clean strings so Streamlit's
    # Arrow serialization stays silent (avoids "Expected bytes, got float" warnings).
    for col in x.columns:
        if x[col].dtype == object:
            x[col] = x[col].map(lambda v: "" if (v is None or (isinstance(v, float) and pd.isna(v))) else str(v))
    return x


# ------------------------------------------------------------
# Reusable HTML components
# ------------------------------------------------------------
def hero(title_html, subtitle, badge=None):
    badge_html = f'<div class="badge">{badge}</div>' if badge else ""
    st.markdown(
        f"""
        <div class="hero">
          {badge_html}
          <h1>{title_html}</h1>
          <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_card(label, value, sub="", tone="default"):
    tone_cls = {"good": "kpi-good", "bad": "kpi-bad", "warn": "kpi-warn"}.get(tone, "")
    sub_html = f'<div class="metric-sub {tone_cls}">{sub}</div>' if sub else ""
    return f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div>{sub_html}</div>'


def kpi_row(cards):
    """cards: list of (label, value, sub, tone) tuples. Renders responsive columns."""
    cols = st.columns(len(cards))
    for col, c in zip(cols, cards):
        label, value = c[0], c[1]
        sub = c[2] if len(c) > 2 else ""
        tone = c[3] if len(c) > 3 else "default"
        col.markdown(kpi_card(label, value, sub, tone), unsafe_allow_html=True)


def section_title(title, subtitle=""):
    sub = f'<div class="section-sub">{subtitle}</div>' if subtitle else ""
    st.markdown(f'<div class="section-head"><h3>{title}</h3>{sub}</div>', unsafe_allow_html=True)


def chip(text, tone="default"):
    return f'<span class="chip chip-{tone}">{text}</span>'


def chips_row(items):
    st.markdown('<div class="chips">' + "".join(items) + "</div>", unsafe_allow_html=True)


def plotly_layout(fig, height=None):
    """Apply consistent dark transparent styling to a Plotly figure."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#E2E8F0"),
        margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    if height:
        fig.update_layout(height=height)
    return fig


def apply_theme() -> None:
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

:root {
  --bg-0:#020617; --bg-1:#0f172a;
  --panel:rgba(15,23,42,.74); --panel-strong:rgba(15,23,42,.94);
  --border:rgba(148,163,184,.16); --border-accent:rgba(45,212,191,.30);
  --text:#F8FAFC; --muted:#94A3B8; --soft:#CBD5E1;
  --accent:#14B8A6; --accent-2:#2563EB; --good:#34D399; --bad:#F87171; --warn:#FBBF24;
}
html, body, [class*="css"] {font-family:'Inter',sans-serif;}
.stApp {
  background:
    radial-gradient(circle at 8% 6%, rgba(20,184,166,.18), transparent 30%),
    radial-gradient(circle at 92% 0%, rgba(37,99,235,.16), transparent 32%),
    linear-gradient(135deg, var(--bg-0) 0%, var(--bg-1) 45%, #0b1220 100%);
  color:var(--text);
}
.block-container {padding-top:1.1rem; padding-bottom:2.5rem; max-width:1580px;}
[data-testid="stSidebar"] {background:rgba(2,6,23,.90); border-right:1px solid var(--border);}
[data-testid="stSidebar"] * {color:#E5E7EB;}
#MainMenu, footer {visibility:hidden;}

/* Hero */
.hero {
  border:1px solid var(--border-accent);
  background:linear-gradient(135deg, rgba(15,23,42,.96), rgba(30,41,59,.66));
  border-radius:26px; padding:26px 30px; margin-bottom:18px;
  box-shadow:0 24px 80px rgba(0,0,0,.40);
}
.hero h1 {font-size:clamp(28px,4.6vw,52px); line-height:1.02; margin:0; font-weight:900; letter-spacing:-0.05em;}
.hero p {color:var(--soft); font-size:15.5px; margin:12px 0 0 0; max-width:1040px; line-height:1.5;}
.badge {
  display:inline-flex; gap:8px; align-items:center; padding:7px 12px; border-radius:999px;
  background:rgba(20,184,166,.12); border:1px solid rgba(45,212,191,.28);
  color:#99F6E4; font-weight:800; font-size:11.5px; margin-bottom:12px; letter-spacing:.02em;
}
.small-muted {color:var(--muted); font-size:13px;}

/* Section header */
.section-head {margin:18px 0 8px 0;}
.section-head h3 {margin:0; font-weight:800; letter-spacing:-0.02em; font-size:1.25rem;}
.section-sub {color:var(--muted); font-size:13px; margin-top:2px;}

/* Cards / KPIs */
.card {background:linear-gradient(180deg, rgba(15,23,42,.92), rgba(15,23,42,.56)); border:1px solid var(--border); border-radius:20px; box-shadow:0 16px 45px rgba(0,0,0,.22); padding:18px;}
.metric-card {
  background:linear-gradient(180deg, rgba(15,23,42,.94), rgba(15,23,42,.58));
  border:1px solid rgba(45,212,191,.16); border-radius:20px; padding:16px 18px;
  min-height:112px; box-shadow:0 16px 45px rgba(0,0,0,.22);
  transition:transform .15s ease, border-color .15s ease;
}
.metric-card:hover {transform:translateY(-2px); border-color:rgba(45,212,191,.45);}
.metric-label {font-size:11.5px; color:var(--muted); text-transform:uppercase; font-weight:900; letter-spacing:.09em;}
.metric-value {font-size:clamp(20px,2.6vw,32px); color:var(--text); font-weight:900; margin-top:6px; letter-spacing:-0.03em; line-height:1.1;}
.metric-sub {font-size:12px; color:#A7F3D0; margin-top:5px; font-weight:600;}
.metric-sub.kpi-good {color:var(--good);}
.metric-sub.kpi-bad {color:var(--bad);}
.metric-sub.kpi-warn {color:var(--warn);}

/* Chips / pills */
.chips {display:flex; flex-wrap:wrap; gap:8px; margin:6px 0 12px 0;}
.chip {display:inline-flex; align-items:center; gap:6px; padding:5px 11px; border-radius:999px; font-size:12px; font-weight:700; border:1px solid var(--border);}
.chip-default {background:rgba(148,163,184,.10); color:var(--soft);}
.chip-good {background:rgba(52,211,153,.14); color:var(--good); border-color:rgba(52,211,153,.30);}
.chip-bad {background:rgba(248,113,113,.14); color:var(--bad); border-color:rgba(248,113,113,.30);}
.chip-warn {background:rgba(251,191,36,.14); color:var(--warn); border-color:rgba(251,191,36,.30);}
.chip-accent {background:rgba(20,184,166,.16); color:#99F6E4; border-color:rgba(45,212,191,.30);}

/* Buttons */
.stButton>button, .stDownloadButton>button {
  border:1px solid rgba(45,212,191,.35);
  background:linear-gradient(135deg, var(--accent), var(--accent-2));
  color:white; border-radius:14px; padding:.70rem 1rem; font-weight:800;
  box-shadow:0 12px 32px rgba(20,184,166,.16); min-height:44px; transition:transform .12s ease;
}
.stButton>button:hover, .stDownloadButton>button:hover {border-color:#99F6E4; transform:translateY(-1px);}
[data-testid="stMetricValue"] {color:var(--text);}

/* Inputs */
div[data-baseweb="select"] > div {background-color:rgba(15,23,42,.82); border-color:rgba(148,163,184,.25); border-radius:12px;}
input, textarea {background-color:rgba(15,23,42,.90) !important; color:var(--text) !important; border-radius:12px !important;}
.stTextInput input {min-height:42px;}
.stMultiSelect [data-baseweb="tag"] {background:rgba(20,184,166,.18); border:1px solid rgba(45,212,191,.25);}
[data-testid="stMetric"] {background:rgba(15,23,42,.55); border:1px solid var(--border); border-radius:16px; padding:12px 14px;}

/* Tabs + dataframes */
.stTabs [data-baseweb="tab-list"] {gap:8px; overflow-x:auto; flex-wrap:nowrap; padding-bottom:2px;}
.stTabs [data-baseweb="tab"] {background:rgba(15,23,42,.60); border-radius:12px; padding:9px 15px; border:1px solid rgba(148,163,184,.16); white-space:nowrap;}
.stTabs [aria-selected="true"] {background:linear-gradient(135deg, rgba(20,184,166,.30), rgba(37,99,235,.24)); border-color:rgba(45,212,191,.45);}
.stDataFrame {border-radius:14px; overflow:hidden;}
div[data-testid="stDataFrame"] {overflow-x:auto;}

/* Radio nav in sidebar -> segmented look */
[data-testid="stSidebar"] .stRadio > div {gap:4px;}
[data-testid="stSidebar"] .stRadio label {border-radius:10px; padding:4px 6px;}

/* Mobile */
@media (max-width:900px) {
  .block-container {padding-left:.8rem !important; padding-right:.8rem !important; padding-top:.7rem !important;}
  .hero {padding:18px; border-radius:22px;}
  .hero h1 {font-size:30px !important; line-height:1.04 !important;}
  .hero p {font-size:13.5px;}
  .metric-card {min-height:90px; padding:13px; margin-bottom:8px;}
  .metric-value {font-size:23px;}
  div[data-testid="stHorizontalBlock"] {flex-direction:column !important; gap:.55rem !important;}
  div[data-testid="column"] {width:100% !important; flex:1 1 100% !important; min-width:100% !important;}
  .stButton>button, .stDownloadButton>button {width:100% !important;}
  [data-testid="stSidebar"] {min-width:90vw !important; max-width:90vw !important;}
  .stTabs [data-baseweb="tab"] {padding:8px 11px; font-size:12.5px;}
}
@media (max-width:520px) {
  .hero {padding:15px; border-radius:18px; margin-bottom:12px;}
  .hero h1 {font-size:25px !important; letter-spacing:-0.035em;}
  .hero p {font-size:12.5px;}
  .badge {font-size:10px; padding:6px 9px;}
  .metric-label {font-size:10px;}
  .metric-value {font-size:21px;}
  .section-head h3 {font-size:1.08rem;}
}
</style>
""",
        unsafe_allow_html=True,
    )
