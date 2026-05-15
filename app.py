import streamlit as st

from ui_theme import apply_theme, hero, section_title, info_card, BUILD_VERSION
from market_engine import load_prepared_data
from market_analysis_page import render_market_analysis_page
from strategic_recommendations import render_strategic_recommendations_page

configure_page()
apply_theme()


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
    st.caption(f"Build: {BUILD_VERSION}")
    st.markdown("---")

if page == "Recommandations stratégiques":
    render_strategic_recommendations_page(nom, iqvia, pch)
else:
    render_market_analysis_page(nom, iqvia, pch)
