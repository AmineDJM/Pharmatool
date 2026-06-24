import streamlit as st

import market_engine as me
from ui_theme import BUILD_VERSION, apply_theme, configure_page
from auth import require_password
from market_overview_page import render_market_overview_page
from market_analysis_page import render_market_analysis_page
from competition_page import render_competition_page
from strategic_recommendations import render_strategic_recommendations_page

configure_page()
apply_theme()

# Server-side gate: nothing below (data load, pages) runs until authenticated.
require_password()


@st.cache_data(show_spinner="Chargement IQVIA / PCH / Nomenclature…")
def cached_data(dzd_per_usd: float):
    me.CONFIG["DZD_PER_USD"] = dzd_per_usd
    return me.load_prepared_data()


PAGES = {
    "🏠 Vue d'ensemble": render_market_overview_page,
    "🔬 Analyse produit / DCI": render_market_analysis_page,
    "🏟️ Analyse concurrentielle": render_competition_page,
    "🧠 Opportunités stratégiques": render_strategic_recommendations_page,
}

with st.sidebar:
    st.markdown("## 💊 Pharma Intelligence")
    st.caption("Algérie · IQVIA · PCH · Nomenclature")
    page = st.radio("Navigation", list(PAGES.keys()), index=0, label_visibility="collapsed")
    st.markdown("---")
    with st.expander("⚙️ Réglages", expanded=False):
        dzd_per_usd = st.number_input("Taux de change (DZD / USD)", min_value=50.0, max_value=400.0,
                                      value=float(me.CONFIG["DZD_PER_USD"]), step=1.0,
                                      help="Sert uniquement à la conversion USD indicative.")

try:
    data = cached_data(dzd_per_usd)
except Exception as e:
    st.error("Impossible de charger les fichiers Excel. Vérifie que le dossier data/ contient les fichiers IQVIA / PCH / Nomenclature.")
    st.exception(e)
    st.stop()

# keep FX in sync even when data is served from cache
me.CONFIG["DZD_PER_USD"] = dzd_per_usd

with st.sidebar:
    meta = data.get("meta", {})
    st.markdown("---")
    st.markdown("**Sources chargées**")
    st.caption(
        f"📈 {meta.get('iqvia_file', '—')}\n\n"
        f"🏥 {meta.get('pch_file', '—')}\n\n"
        f"📚 {meta.get('nom_file', '—')}"
    )
    st.caption(f"Build : {BUILD_VERSION}")
    if st.button("🔒 Se déconnecter", use_container_width=True):
        for k in ("auth_ok", "auth_attempts", "auth_locked_until"):
            st.session_state.pop(k, None)
        st.rerun()

PAGES[page](data)
