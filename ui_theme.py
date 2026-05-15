import streamlit as st

BUILD_VERSION = "v4.5 premium-mobile-ui"

def apply_theme():
    st.set_page_config(
        page_title="Algeria Pharma Market Intelligence",
        page_icon="💊",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

:root {
    --bg: #07111f;
    --card: rgba(15, 28, 48, 0.82);
    --card2: rgba(20, 45, 75, 0.72);
    --line: rgba(87, 215, 255, 0.22);
    --text: #f4f7fb;
    --muted: #aab7c8;
    --cyan: #25e6d2;
    --blue: #3388ff;
    --green: #69f0ae;
    --red: #ff4d5d;
}

/* GLOBAL */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif !important;
}

.stApp {
    background:
        radial-gradient(circle at 10% 0%, rgba(37,230,210,0.16), transparent 30%),
        radial-gradient(circle at 90% 10%, rgba(51,136,255,0.18), transparent 32%),
        linear-gradient(135deg, #07111f 0%, #0b1424 45%, #08101e 100%);
    color: var(--text);
}

.block-container {
    padding-top: 1.1rem !important;
    padding-left: 2.2rem !important;
    padding-right: 2.2rem !important;
    max-width: 1480px !important;
}

/* SIDEBAR */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, rgba(8,14,27,0.98), rgba(13,24,44,0.98)) !important;
    border-right: 1px solid rgba(87,215,255,0.16);
}

section[data-testid="stSidebar"] > div {
    padding-top: 1rem !important;
}

/* TITLES */
h1 {
    font-size: clamp(2.35rem, 4.8vw, 4.5rem) !important;
    line-height: 1.02 !important;
    font-weight: 900 !important;
    letter-spacing: -0.055em !important;
    color: #ffffff !important;
    margin-bottom: 1rem !important;
}

h2, h3 {
    color: #f8fbff !important;
    letter-spacing: -0.025em !important;
}

p, label, span {
    color: inherit;
}

/* PREMIUM CARDS */
.glass-card, div[data-testid="stExpander"] {
    background: linear-gradient(145deg, rgba(17,33,57,0.88), rgba(10,20,36,0.82)) !important;
    border: 1px solid rgba(95, 218, 255, 0.20) !important;
    box-shadow: 0 20px 60px rgba(0,0,0,0.30);
    border-radius: 28px !important;
}

.glass-card {
    padding: 1.55rem !important;
}

div[data-testid="stMetric"] {
    background: linear-gradient(145deg, rgba(20,45,75,0.85), rgba(9,18,34,0.90));
    border: 1px solid rgba(95,218,255,0.18);
    padding: 1rem 1.1rem;
    border-radius: 22px;
    box-shadow: 0 14px 38px rgba(0,0,0,0.25);
}

div[data-testid="stMetricValue"] {
    color: #ffffff !important;
    font-weight: 900 !important;
    letter-spacing: -0.04em;
}

div[data-testid="stMetricLabel"] {
    color: var(--muted) !important;
    font-weight: 700 !important;
}

/* INPUTS */
input, textarea, [data-baseweb="select"] {
    font-size: 16px !important;
}

.stTextInput input, .stTextArea textarea {
    background: rgba(16, 31, 54, 0.95) !important;
    color: #ffffff !important;
    border: 1px solid rgba(95,218,255,0.18) !important;
    border-radius: 16px !important;
}

[data-baseweb="select"] > div {
    background: rgba(16, 31, 54, 0.95) !important;
    border: 1px solid rgba(95,218,255,0.18) !important;
    border-radius: 16px !important;
}

/* BUTTONS */
.stButton button, .stDownloadButton button {
    width: 100%;
    height: 3.25rem !important;
    border-radius: 18px !important;
    border: 1px solid rgba(255,255,255,0.28) !important;
    background: linear-gradient(135deg, var(--cyan), var(--blue)) !important;
    color: white !important;
    font-weight: 850 !important;
    font-size: 1rem !important;
    box-shadow: 0 14px 35px rgba(35,135,255,0.27);
    transition: transform .16s ease, box-shadow .16s ease;
}

.stButton button:hover, .stDownloadButton button:hover {
    transform: translateY(-1px);
    box-shadow: 0 18px 45px rgba(35,135,255,0.38);
}

/* TABS */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.45rem;
    overflow-x: auto;
    padding-bottom: 0.4rem;
}

.stTabs [data-baseweb="tab"] {
    background: rgba(16, 31, 54, 0.84);
    border: 1px solid rgba(95,218,255,0.16);
    border-radius: 999px;
    padding: 0.6rem 1rem;
    color: #dce8f7;
    font-weight: 800;
}

.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, rgba(37,230,210,0.95), rgba(51,136,255,0.95)) !important;
    color: white !important;
}

/* TABLES */
.stDataFrame {
    border-radius: 18px !important;
    overflow: hidden !important;
    border: 1px solid rgba(95,218,255,0.16);
}

div[data-testid="stDataFrameResizable"] {
    overflow-x: auto !important;
}

/* ALERTS */
div[data-testid="stAlert"] {
    border-radius: 18px !important;
    border: 1px solid rgba(95,218,255,0.16);
}

/* HIDE STREAMLIT NOISE */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {background: transparent !important;}

/* MOBILE PREMIUM */
@media (max-width: 768px) {
    .block-container {
        padding-top: 0.45rem !important;
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
        padding-bottom: 4.5rem !important;
    }

    h1 {
        font-size: 2.05rem !important;
        line-height: 2.18rem !important;
        letter-spacing: -0.045em !important;
        margin-bottom: 0.65rem !important;
    }

    h2 {
        font-size: 1.35rem !important;
    }

    h3 {
        font-size: 1.08rem !important;
    }

    p {
        font-size: 0.96rem !important;
        line-height: 1.6rem !important;
    }

    .glass-card {
        padding: 0.95rem !important;
        border-radius: 20px !important;
        margin-bottom: 0.8rem !important;
    }

    div[data-testid="stHorizontalBlock"] {
        flex-direction: column !important;
        gap: 0.6rem !important;
    }

    div[data-testid="column"] {
        width: 100% !important;
        flex: 1 1 100% !important;
        min-width: 100% !important;
    }

    div[data-testid="stMetric"] {
        padding: 0.8rem 0.9rem !important;
        border-radius: 18px !important;
    }

    div[data-testid="stMetricValue"] {
        font-size: 1.55rem !important;
    }

    .stButton button, .stDownloadButton button {
        height: 3rem !important;
        font-size: 0.95rem !important;
        border-radius: 16px !important;
    }

    .stTabs [data-baseweb="tab"] {
        padding: 0.48rem 0.78rem !important;
        font-size: 0.82rem !important;
        white-space: nowrap !important;
    }

    section[data-testid="stSidebar"] {
        width: 100% !important;
    }

    .stDataFrame {
        overflow-x: scroll !important;
    }

    div[data-testid="stDataFrameResizable"] {
        overflow-x: scroll !important;
    }

    [data-testid="stVerticalBlock"] {
        gap: 0.55rem !important;
    }
}

/* SMALL IPHONE */
@media (max-width: 390px) {
    h1 {
        font-size: 1.82rem !important;
        line-height: 2rem !important;
    }

    .block-container {
        padding-left: 0.55rem !important;
        padding-right: 0.55rem !important;
    }

    .glass-card {
        padding: 0.8rem !important;
    }
}
</style>
        """,
        unsafe_allow_html=True,
    )


def hero(title: str, subtitle: str):
    st.markdown(
        f"""
<div class="glass-card">
    <div style="
        display:inline-block;
        padding:0.45rem 0.8rem;
        border-radius:999px;
        background:rgba(37,230,210,0.10);
        border:1px solid rgba(37,230,210,0.28);
        color:#9ffcf2;
        font-size:0.82rem;
        font-weight:800;
        margin-bottom:1rem;">
        ✨ Internal Market Intelligence Engine · {BUILD_VERSION}
    </div>
    <h1>{title}</h1>
    <p style="color:#b7c4d8;font-size:1.12rem;line-height:1.85rem;max-width:920px;">
        {subtitle}
    </p>
</div>
        """,
        unsafe_allow_html=True,
    )


def section_title(title: str, subtitle: str = ""):
    st.markdown(
        f"""
<div style="margin:1.1rem 0 0.65rem 0;">
    <h2 style="margin-bottom:0.25rem;">{title}</h2>
    <p style="color:#9fb0c6;margin-top:0;">{subtitle}</p>
</div>
        """,
        unsafe_allow_html=True,
    )


def info_card(text: str):
    st.markdown(
        f"""
<div style="
    background:rgba(51,136,255,0.14);
    border:1px solid rgba(51,136,255,0.22);
    border-radius:18px;
    padding:1rem;
    color:#d8e8ff;
    font-weight:600;
    line-height:1.65rem;">
    {text}
</div>
        """,
        unsafe_allow_html=True,
    )

def fmt_money(value, currency="DZD"):
    try:
        if value is None:
            return "-"
        value = float(value)
        if abs(value) >= 1_000_000_000:
            return f"{value/1_000_000_000:,.2f} B {currency}".replace(",", " ")
        if abs(value) >= 1_000_000:
            return f"{value/1_000_000:,.2f} M {currency}".replace(",", " ")
        if abs(value) >= 1_000:
            return f"{value/1_000:,.2f} K {currency}".replace(",", " ")
        return f"{value:,.0f} {currency}".replace(",", " ")
    except Exception:
        return "-"
