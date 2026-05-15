import math
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from strategic_recommendations import render_strategic_recommendations_page

from market_engine import (
    CONFIG,
    build_option_universe,
    build_opportunity_table,
    export_excel_bytes,
    facet_filter,
    filter_iqvia,
    filter_nomenclature,
    filter_options,
    filter_pch,
    load_prepared_data,
    parse_dci_input,
    get_nomenclature_dci_options,
    dci_input_to_list,
    run_market_analysis,
    safe_unique,
)

st.set_page_config(
    page_title="Algeria Pharma Market Intelligence",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
html, body, [class*="css"] {font-family: 'Inter', sans-serif;}
.stApp {
  background:
    radial-gradient(circle at 8% 8%, rgba(20,184,166,0.20), transparent 28%),
    radial-gradient(circle at 88% 0%, rgba(59,130,246,0.18), transparent 30%),
    linear-gradient(135deg, #020617 0%, #0f172a 38%, #111827 100%);
  color: #E5E7EB;
}
[data-testid="stSidebar"] {
  background: rgba(2,6,23,0.82);
  border-right: 1px solid rgba(148,163,184,0.18);
}
[data-testid="stSidebar"] * {color: #E5E7EB;}
.block-container {padding-top: 1.35rem; padding-bottom: 2rem; max-width: 1500px;}
.hero {
  border: 1px solid rgba(45,212,191,0.25);
  background: linear-gradient(135deg, rgba(15,23,42,0.92), rgba(30,41,59,0.70));
  border-radius: 28px;
  padding: 26px 30px;
  box-shadow: 0 24px 80px rgba(0,0,0,.35);
  margin-bottom: 20px;
}
.hero h1 {font-size: clamp(30px, 5vw, 56px); line-height: 1.0; margin: 0; font-weight: 900; letter-spacing: -0.055em;}
.hero p {color: #CBD5E1; font-size: 16px; margin: 12px 0 0 0; max-width: 980px;}
.badge {display: inline-flex; gap: 8px; align-items:center; padding: 7px 11px; border-radius: 999px; background: rgba(20,184,166,.12); border: 1px solid rgba(45,212,191,.25); color:#99F6E4; font-weight:700; font-size: 12px; margin-bottom: 12px;}
.card {
  background: rgba(15,23,42,.72);
  border: 1px solid rgba(148,163,184,.18);
  border-radius: 22px;
  padding: 18px;
  box-shadow: 0 16px 45px rgba(0,0,0,.25);
}
.metric-card {
  background: linear-gradient(180deg, rgba(15,23,42,.92), rgba(15,23,42,.58));
  border: 1px solid rgba(45,212,191,.18);
  border-radius: 22px;
  padding: 18px;
  min-height: 118px;
}
.metric-label {font-size: 12px; color: #94A3B8; text-transform: uppercase; font-weight: 800; letter-spacing: .08em;}
.metric-value {font-size: clamp(22px, 3vw, 34px); color: #F8FAFC; font-weight: 900; margin-top: 8px; letter-spacing: -0.035em;}
.metric-sub {font-size: 12px; color: #A7F3D0; margin-top: 4px;}
.stButton>button, .stDownloadButton>button {
  border: 1px solid rgba(45,212,191,.35);
  background: linear-gradient(135deg, #14B8A6, #2563EB);
  color: white;
  border-radius: 16px;
  padding: .72rem 1rem;
  font-weight: 900;
  box-shadow: 0 12px 35px rgba(20,184,166,.18);
}
.stButton>button:hover, .stDownloadButton>button:hover {border-color: #99F6E4; transform: translateY(-1px);}
[data-testid="stMetricValue"] {color: #F8FAFC;}
div[data-baseweb="select"] > div {background-color: rgba(15,23,42,.78); border-color: rgba(148,163,184,.25); border-radius: 14px;}
input, textarea {background-color: rgba(15,23,42,.86) !important; color: #F8FAFC !important; border-radius: 14px !important;}
.stTabs [data-baseweb="tab-list"] {gap: 8px;}
.stTabs [data-baseweb="tab"] {background: rgba(15,23,42,.60); border-radius: 14px; padding: 10px 16px; border:1px solid rgba(148,163,184,.16);}
.stDataFrame {border-radius: 18px; overflow:hidden;}
.small-muted {color:#94A3B8; font-size: 13px;}
@media (max-width: 900px) {
  .hero {padding:18px; border-radius:22px;}
  .block-container {padding-left: 0.75rem; padding-right: 0.75rem; padding-top: .8rem;}
  .metric-card {min-height: 92px; padding: 14px;}
  .metric-value {font-size: 24px;}
  [data-testid="stSidebar"] {min-width: 92vw !important; max-width: 92vw !important;}
}
@media (max-width: 520px) {
  .hero h1 {font-size: 30px;}
  .hero p {font-size: 13px;}
  .badge {font-size: 10px; padding: 6px 9px;}
  .stButton>button, .stDownloadButton>button {border-radius: 14px; padding: .65rem .8rem;}
}

</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def fmt_money(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    x = float(x)
    if abs(x) >= 1_000_000_000:
        return f"{x/1_000_000_000:,.2f} B"
    if abs(x) >= 1_000_000:
        return f"{x/1_000_000:,.1f} M"
    if abs(x) >= 1_000:
        return f"{x/1_000:,.1f} K"
    return f"{x:,.0f}"


@st.cache_data(show_spinner="Chargement des fichiers IQVIA / PCH / Nomenclature…")
def cached_data():
    return load_prepared_data()


try:
    nom, iqvia, pch = cached_data()
except Exception as e:
    st.error("Impossible de charger les fichiers Excel. Vérifie que le dossier data/ contient les 3 fichiers attendus.")
    st.exception(e)
    st.stop()

with st.sidebar:
    st.markdown("### 🧭 Navigation")
    page = st.radio(
        "Page",
        ["Analyse produit / DCI", "Recommandations stratégiques"],
        index=0,
        label_visibility="collapsed",
    )
    st.markdown("---")

if page == "Recommandations stratégiques":
    render_strategic_recommendations_page(nom, iqvia, pch)
    st.stop()

@media (max-width: 768px) {
  .block-container {
    padding: 0.8rem 0.7rem !important;
  }

  div[data-testid="stHorizontalBlock"] {
    flex-direction: column !important;
  }

  div[data-testid="column"] {
    width: 100% !important;
    flex: 1 1 100% !important;
  }

  .stMetric {
    width: 100% !important;
  }

  h1 {
    font-size: 1.8rem !important;
    line-height: 2.1rem !important;
  }

  h2, h3 {
    font-size: 1.2rem !important;
  }

  .stDataFrame {
    overflow-x: auto !important;
  }

  section[data-testid="stSidebar"] {
    width: 100% !important;
  }

  button {
    width: 100% !important;
  }
}

with st.sidebar:
    st.markdown("### 🔎 Recherche intelligente")
    dci_search = st.text_input(
        "Chercher une DCI dans la Nomenclature",
        placeholder="Ex: dolutegravir, raltegravir, paracetamol",
        help="Tape quelques lettres : la liste proposée vient uniquement de la Nomenclature officielle.",
    )
    dci_options = get_nomenclature_dci_options(nom, dci_search, limit=350)
    previous_dcis = st.session_state.get("selected_dcis", [])
    dci_options = list(dict.fromkeys(list(previous_dcis) + list(dci_options)))
    selected_dcis = st.multiselect(
        "DCI(s) sélectionnée(s)",
        dci_options,
        default=previous_dcis,
        key="selected_dcis",
        placeholder="Choisir une ou plusieurs DCI / associations",
        help="Sélection contrôlée : tu peux choisir la DCI seule ou les associations présentes dans la Nomenclature.",
    )
    dci_text = ", ".join(selected_dcis) if selected_dcis else dci_search
    markets = st.multiselect(
        "Marché analysé",
        ["IQVIA VILLE", "PCH HOSPITALIER"],
        default=["IQVIA VILLE", "PCH HOSPITALIER"],
        help="Si vide, l'app considère les deux marchés.",
    ) or ["IQVIA VILLE", "PCH HOSPITALIER"]

    universe = build_option_universe(dci_text, markets, nom, iqvia, pch)
    st.markdown("---")
    st.markdown("### 🎛️ Filtres dynamiques")
    st.caption("Chaque filtre met à jour tous les autres. Aucun ordre obligatoire.")

    # keep state-safe selections
    current_dosages = st.session_state.get("dosage", [])
    current_formes = st.session_state.get("formes", [])
    current_labs = st.session_state.get("labs", [])
    current_statuts = st.session_state.get("statuts", [])

    base_kwargs = dict(dosage=current_dosages, formes=current_formes, labs=current_labs, statuts=current_statuts, markets=markets)

    dosage_search = st.text_input("Chercher dans les dosages", placeholder="ex: 1, 500 mg, 5 mg/ml")
    dosage_options = [] if universe.empty else filter_options(safe_unique(facet_filter(universe, **base_kwargs, ignore={"dosage"})["dosage"], 1200), dosage_search, 350)
    current_dosages = [x for x in current_dosages if x in dosage_options]
    dosage = st.multiselect("Dosage", dosage_options, default=current_dosages, key="dosage")

    forme_search = st.text_input("Chercher dans les formes", placeholder="ex: injectable, comprimé")
    base_kwargs = dict(dosage=dosage, formes=current_formes, labs=current_labs, statuts=current_statuts, markets=markets)
    forme_options = [] if universe.empty else filter_options(safe_unique(facet_filter(universe, **base_kwargs, ignore={"forme"})["forme"], 600), forme_search, 200)
    current_formes = [x for x in current_formes if x in forme_options]
    formes = st.multiselect("Forme / type", forme_options, default=current_formes, key="formes")

    base_kwargs = dict(dosage=dosage, formes=formes, labs=current_labs, statuts=current_statuts, markets=markets)
    lab_options = [] if universe.empty else safe_unique(facet_filter(universe, **base_kwargs, ignore={"lab"})["lab"], 2000)
    current_labs = [x for x in current_labs if x in lab_options]
    labs = st.multiselect(
        "Laboratoire",
        lab_options,
        default=current_labs,
        key="labs",
        placeholder="Choisir un ou plusieurs laboratoires",
        help="Liste dynamique issue des produits réellement associés aux filtres actuels. Pas de saisie libre."
    )

    base_kwargs = dict(dosage=dosage, formes=formes, labs=labs, statuts=current_statuts, markets=markets)
    statut_options = [] if universe.empty else [x for x in safe_unique(facet_filter(universe, **base_kwargs, ignore={"statut"})["statut"], 80) if x]
    current_statuts = [x for x in current_statuts if x in statut_options]
    statuts = st.multiselect("Statut Nomenclature", statut_options, default=current_statuts, key="statuts")

    live_intersection = pd.DataFrame() if universe.empty else facet_filter(universe, dosage=dosage, formes=formes, labs=labs, statuts=statuts, markets=markets)
    st.markdown("---")
    st.markdown(f"**Candidats actifs :** `{len(live_intersection):,}`")
    if not live_intersection.empty:
        st.caption(
            f"Nomenclature: {(live_intersection['source']=='NOMENCLATURE').sum():,} · "
            f"IQVIA: {(live_intersection['source']=='IQVIA VILLE').sum():,} · "
            f"PCH: {(live_intersection['source']=='PCH HOSPITALIER').sum():,}"
        )

run_col1, run_col2 = st.columns([0.72, 0.28], vertical_alignment="center")
with run_col1:
    st.markdown('<div class="small-muted">Le moteur accepte les approximations : accents, casse, dosage abrégé, formes variables et noms de laboratoires partiels.</div>', unsafe_allow_html=True)
with run_col2:
    run = st.button("🚀 Lancer l’analyse", use_container_width=True, type="primary")

if not dci_text.strip():
    st.info("Tape une DCI puis sélectionne une ou plusieurs propositions issues de la Nomenclature.")
    st.stop()

if universe.empty:
    st.warning("Aucun candidat trouvé pour cette DCI. Essaie une orthographe plus large ou retire certains filtres.")
    st.stop()

# Preview cards
c1, c2, c3, c4 = st.columns(4)
c1.markdown(f'<div class="metric-card"><div class="metric-label">Candidats</div><div class="metric-value">{len(live_intersection):,}</div><div class="metric-sub">intersection actuelle</div></div>', unsafe_allow_html=True)
c2.markdown(f'<div class="metric-card"><div class="metric-label">Laboratoires</div><div class="metric-value">{live_intersection["lab"].replace("", pd.NA).dropna().nunique():,}</div><div class="metric-sub">players potentiels</div></div>', unsafe_allow_html=True)
c3.markdown(f'<div class="metric-card"><div class="metric-label">Formes</div><div class="metric-value">{live_intersection["forme"].replace("", pd.NA).dropna().nunique():,}</div><div class="metric-sub">formes associées</div></div>', unsafe_allow_html=True)
c4.markdown(f'<div class="metric-card"><div class="metric-label">Sources</div><div class="metric-value">{live_intersection["source"].nunique():,}</div><div class="metric-sub">nomenclature / marchés</div></div>', unsafe_allow_html=True)

# Preview tabs built directly from source tables to avoid losing nomenclature lines through the faceted universe.
preview_dcis = dci_input_to_list(selected_dcis, dci_search)
preview_nom = filter_nomenclature(nom, preview_dcis, dosage, formes, labs, statuts) if preview_dcis else pd.DataFrame()
preview_iqvia = filter_iqvia(iqvia, preview_dcis, dosage, formes, labs) if preview_dcis and "IQVIA VILLE" in markets else pd.DataFrame()
preview_pch = filter_pch(pch, preview_dcis, dosage, formes, labs) if preview_dcis and "PCH HOSPITALIER" in markets else pd.DataFrame()

with st.expander("👁️ Aperçu des lignes associées", expanded=False):
    t_nom, t_iqvia, t_pch = st.tabs([
        f"📚 Nomenclature ({len(preview_nom):,})",
        f"🏙️ IQVIA ville ({len(preview_iqvia):,})",
        f"🏥 Ventes hospitalières PCH ({len(preview_pch):,})",
    ])

    with t_nom:
        if preview_nom.empty:
            st.info("Aucune ligne nomenclature associée aux filtres actuels.")
        else:
            st.caption("Source affichée ici : uniquement la Nomenclature. Toutes les lignes liées à la/aux DCI sélectionnée(s) sont affichées.")
            cols = [c for c in ['_QUERY_DCI','DCI','BRAND','FORME','DOSAGE','CONDITIONNEMENT','LABORATOIRE','STATUT','TYPE','P1','P2','LISTE','SOURCE_NOMENCLATURE'] if c in preview_nom.columns]
            st.dataframe(preview_nom[cols].head(1000), use_container_width=True, height=390)

    with t_iqvia:
        if preview_iqvia.empty:
            st.info("Aucune ligne IQVIA ville associée aux filtres actuels.")
        else:
            st.caption("Aperçu des lignes marché ville associées aux filtres actuels.")
            cols = [c for c in ['_QUERY_DCI','MOLECULE','BRAND','PRESENTATION','LABORATOIRE','THERAPEUTIC_CLASS','MARKET_VOLUME','MARKET_VALUE_DZD','MARKET_VALUE_USD'] if c in preview_iqvia.columns]
            st.dataframe(preview_iqvia[cols].head(1000), use_container_width=True, height=390)

    with t_pch:
        if preview_pch.empty:
            st.info("Aucune ligne de réceptions / ventes hospitalières PCH associée aux filtres actuels.")
        else:
            st.caption("Aperçu des lignes hospitalières associées aux filtres actuels.")
            cols = [c for c in ['_QUERY_DCI','PRODUCT_FULL','LABORATOIRE','THERAPEUTIC_CLASS','QTE','UNIT_PRICE','DEVISE','MARKET_VALUE_DZD','MARKET_VALUE_USD','DATESTOCKAGE','TYPE_RECEP'] if c in preview_pch.columns]
            st.dataframe(preview_pch[cols].head(1000), use_container_width=True, height=390)

if run:
    dci_list = dci_input_to_list(selected_dcis, dci_search)
    with st.spinner("Matching intelligent en cours… agrégation des marchés… génération du fichier Excel…"):
        nom_matches = filter_nomenclature(nom, dci_list, dosage, formes, labs, statuts)
        iqvia_matches = filter_iqvia(iqvia, dci_list, dosage, formes, labs) if "IQVIA VILLE" in markets else pd.DataFrame()
        pch_matches = filter_pch(pch, dci_list, dosage, formes, labs) if "PCH HOSPITALIER" in markets else pd.DataFrame()
        main, market_detail, nom_detail = build_opportunity_table(nom_matches, iqvia_matches, pch_matches)
        excel_bytes = export_excel_bytes(main, market_detail, nom_detail)
        st.session_state["result"] = (main, market_detail, nom_detail, excel_bytes)

if "result" not in st.session_state:
    st.stop()

main, market_detail, nom_detail, excel_bytes = st.session_state["result"]

if main.empty:
    st.warning("Analyse terminée, mais aucun marché agrégé exploitable n’a été trouvé avec ces filtres.")
    st.stop()

st.success("Analyse terminée. Résultat prêt à exporter.")

k1, k2, k3, k4 = st.columns(4)
total_dzd = main["Market size in Value DZD"].sum() if "Market size in Value DZD" in main else 0
total_usd = main["Market size in Value USD"].sum() if "Market size in Value USD" in main else 0
total_vol = main["Market size in Volume"].sum() if "Market size in Volume" in main else 0
players = main[[c for c in main.columns if c.startswith("Player ") and "Share" not in c]].stack().replace("", pd.NA).dropna().nunique()
k1.markdown(f'<div class="metric-card"><div class="metric-label">Market value DZD</div><div class="metric-value">{fmt_money(total_dzd)}</div><div class="metric-sub">total sélection</div></div>', unsafe_allow_html=True)
k2.markdown(f'<div class="metric-card"><div class="metric-label">Market value USD</div><div class="metric-value">${fmt_money(total_usd)}</div><div class="metric-sub">conversion indicative</div></div>', unsafe_allow_html=True)
k3.markdown(f'<div class="metric-card"><div class="metric-label">Volume</div><div class="metric-value">{fmt_money(total_vol)}</div><div class="metric-sub">unités / réceptions</div></div>', unsafe_allow_html=True)
k4.markdown(f'<div class="metric-card"><div class="metric-label">Players</div><div class="metric-value">{players}</div><div class="metric-sub">laboratoires détectés</div></div>', unsafe_allow_html=True)

# Clean display tables: keep business columns, hide technical matching columns.
def clean_summary_table(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    drop_cols = {"Dossier availability"}
    return df[[c for c in df.columns if c not in drop_cols]].copy()

def clean_market_detail_table(df: pd.DataFrame, mode: str = "market") -> pd.DataFrame:
    """Business-facing market table: no technical score/match/currency/original-value columns.
    For PCH and IQVIA, always expose Market Value in DZD and USD only.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    x = df.copy()
    rename = {
        '_QUERY_DCI': 'DCI',
        'PRODUCT_FULL': 'Product',
        'LABORATOIRE': 'Laboratory',
        'SOURCE_MARKET': 'Source market',
        'Therapeutic_Class': 'Therapeutic class',
        'Market_Size_Volume': 'Market size in volume',
        'Market_Size_Value_DZD': 'Market value DZD',
        'Market_Size_Value_USD': 'Market value USD',
    }
    x = x.rename(columns={k:v for k,v in rename.items() if k in x.columns})
    preferred = [
        'DCI', 'Product', 'Laboratory', 'Source market', 'Therapeutic class',
        'Market size in volume', 'Market value DZD', 'Market value USD'
    ]
    # Optional clean business columns only if they are already user-facing.
    extras_allowed = []
    cols = [c for c in preferred + extras_allowed if c in x.columns]
    return x[cols].copy()

def clean_nomenclature_table(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    hidden_keywords = ["match", "score"]
    cols = [c for c in df.columns if not any(k in str(c).lower() for k in hidden_keywords)]
    return df[cols].copy()

def draw_market_charts(df: pd.DataFrame, title_suffix: str = ""):
    if df is None or df.empty:
        st.info("Aucune donnée marché disponible pour ce graphique.")
        return
    by_lab = df.groupby(["SOURCE_MARKET", "LABORATOIRE"], dropna=False).agg(
        Value_DZD=("Market_Size_Value_DZD", "sum"),
        Volume=("Market_Size_Volume", "sum"),
    ).reset_index().sort_values("Value_DZD", ascending=False).head(25)
    fig = px.bar(
        by_lab,
        x="LABORATOIRE",
        y="Value_DZD",
        color="SOURCE_MARKET",
        title=f"Top players par valeur marché {title_suffix}",
    )
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis_title="Laboratoire", yaxis_title="Valeur DZD")
    st.plotly_chart(fig, use_container_width=True)

    c_left, c_right = st.columns(2)
    with c_left:
        by_source = df.groupby("SOURCE_MARKET", dropna=False).agg(Value_DZD=("Market_Size_Value_DZD", "sum")).reset_index()
        fig2 = px.pie(by_source, names="SOURCE_MARKET", values="Value_DZD", title=f"Split par source {title_suffix}")
        fig2.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig2, use_container_width=True)
    with c_right:
        by_product = df.groupby("PRODUCT_FULL", dropna=False).agg(Value_DZD=("Market_Size_Value_DZD", "sum")).reset_index().sort_values("Value_DZD", ascending=False).head(12)
        fig3 = px.bar(by_product, x="Value_DZD", y="PRODUCT_FULL", orientation="h", title=f"Top produits {title_suffix}")
        fig3.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis_title="Valeur DZD", yaxis_title="Produit")
        st.plotly_chart(fig3, use_container_width=True)

summary_display = clean_summary_table(main)
market_display = clean_market_detail_table(market_detail)
hospital_detail = market_detail[market_detail["SOURCE_MARKET"].eq("PCH HOSPITALIER")].copy() if "SOURCE_MARKET" in market_detail.columns else pd.DataFrame()
ville_detail = market_detail[market_detail["SOURCE_MARKET"].eq("IQVIA VILLE")].copy() if "SOURCE_MARKET" in market_detail.columns else pd.DataFrame()
hospital_display = clean_market_detail_table(hospital_detail, mode="hospital")
ville_display = clean_market_detail_table(ville_detail, mode="ville")
nom_display = clean_nomenclature_table(nom_detail)

# Export the same business-clean version visible in the app.
excel_bytes_clean = export_excel_bytes(summary_display, market_display, nom_display)
st.download_button(
    "⬇️ Télécharger l’analyse Excel",
    data=excel_bytes_clean,
    file_name=f"pharma_market_opportunity_{datetime.now():%Y%m%d_%H%M}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)

tab_market, tab_hosp, tab_ville, tab_graph_all, tab_graph_hosp, tab_graph_ville, tab_nom = st.tabs([
    "📌 Analyse marché",
    "🏥 Ventes hospitalières",
    "🏙️ Marché de ville",
    "📊 Graphiques généraux",
    "🏥 Graphiques hospitalier",
    "🏙️ Graphiques ville",
    "📚 Nomenclature",
])

with tab_market:
    st.caption("Synthèse business consolidée. La colonne Dossier availability a été retirée pour garder une lecture claire.")
    st.dataframe(summary_display, use_container_width=True, height=430)

with tab_hosp:
    st.caption("Détail des ventes / réceptions hospitalières PCH uniquement. Colonnes techniques de matching masquées.")
    if hospital_display.empty:
        st.info("Aucune donnée hospitalière PCH trouvée pour ces filtres.")
    else:
        st.dataframe(hospital_display, use_container_width=True, height=520)

with tab_ville:
    st.caption("Détail du marché ville IQVIA uniquement. Colonnes techniques de matching masquées.")
    if ville_display.empty:
        st.info("Aucune donnée IQVIA ville trouvée pour ces filtres.")
    else:
        st.dataframe(ville_display, use_container_width=True, height=520)

with tab_graph_all:
    draw_market_charts(market_detail, "— global")

with tab_graph_hosp:
    draw_market_charts(hospital_detail, "— hospitalier PCH")

with tab_graph_ville:
    draw_market_charts(ville_detail, "— marché ville IQVIA")

with tab_nom:
    if nom_display is not None and not nom_display.empty:
        st.dataframe(nom_display, use_container_width=True, height=520)
    else:
        st.info("Aucun match nomenclature avec les filtres actuels.")
