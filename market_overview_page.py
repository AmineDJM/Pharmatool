"""Market Overview — the landing dashboard.
Gives an instant read of the Algerian retail (IQVIA) market: size, growth,
leading therapeutic classes and laboratories, concentration and momentum."""

import numpy as np
import plotly.express as px
import streamlit as st

import market_engine as me
from ui_theme import (
    hero, kpi_row, section_title, fmt_money, fmt_int, fmt_growth,
    growth_tone, format_dataframe_for_display, plotly_layout, chip, chips_row,
)


@st.cache_data(show_spinner=False)
def _overview(_iqvia, _iqvia_lab_raw, year, fx):
    total = me.iqvia_total_market(_iqvia_lab_raw, _iqvia)
    classes = me.iqvia_class_breakdown(_iqvia)
    labs = me.prep_lab_landscape(_iqvia_lab_raw)
    return total, classes, labs


def render_market_overview_page(data: dict) -> None:
    iqvia = data["iqvia"]
    iqvia_lab_raw = data["iqvia_lab_raw"]
    meta = data.get("meta", {})
    year = meta.get("iqvia_year", "")

    hero(
        f"Marché pharmaceutique<br/>algérien · {year}",
        "Vue d'ensemble du marché de ville IQVIA : taille, dynamique de croissance, classes "
        "thérapeutiques porteuses, laboratoires leaders et intensité concurrentielle. "
        "Toutes les valeurs sont réconciliées avec les totaux officiels IQVIA.",
        badge=f"📈 Market Overview · {meta.get('iqvia_file', 'IQVIA')}",
    )

    total, classes, labs = _overview(iqvia, iqvia_lab_raw, year, me.CONFIG["DZD_PER_USD"])

    if classes.empty:
        st.warning("Aucune donnée IQVIA exploitable. Vérifie le fichier dans data/.")
        return

    market_hhi = me.compute_hhi(labs["Market_Share"]) if not labs.empty else np.nan

    kpi_row([
        ("Marché total (DZD)", fmt_money(total["value_dzd"]), f"≈ {fmt_money(total['value_usd'], '$')} USD"),
        ("Croissance vs N-1", fmt_growth(total["growth_py"]), "valeur, MAT", growth_tone(total["growth_py"])),
        ("Volume (unités)", fmt_money(total["volume"]), "boîtes / an"),
        ("Laboratoires actifs", fmt_int(total["n_labs"]), f"{me.hhi_label(market_hhi)} · HHI {fmt_int(market_hhi)}"),
    ])

    # ---- Tabs ----
    t_classes, t_labs, t_momentum = st.tabs([
        "🧬 Classes thérapeutiques", "🏭 Laboratoires", "🚀 Dynamique du marché",
    ])

    with t_classes:
        section_title("Top classes thérapeutiques (ATC4)", "Par valeur de marché, avec part et croissance annuelle.")
        top_n = st.slider("Nombre de classes affichées", 5, 40, 15, key="ov_classes_n")
        top = classes.head(top_n).copy()
        fig = px.bar(
            top.sort_values("Value_DZD"), x="Value_DZD", y="THERAPEUTIC_CLASS",
            orientation="h", color="Growth_PY", color_continuous_scale="RdYlGn",
            color_continuous_midpoint=0, title="Valeur de marché par classe (couleur = croissance)",
        )
        fig.update_layout(coloraxis_colorbar_title="Croiss.", yaxis_title="", xaxis_title="Valeur DZD")
        st.plotly_chart(plotly_layout(fig, height=max(380, 26 * len(top))), width='stretch')

        disp = top.rename(columns={
            "THERAPEUTIC_CLASS": "Classe thérapeutique", "Value_DZD": "Valeur DZD",
            "Value_USD": "Valeur USD", "Share": "Part de marché", "Growth_PY": "Croissance",
            "Players": "Concurrents", "Products": "Produits", "Volume": "Volume",
        })[["Classe thérapeutique", "Valeur DZD", "Valeur USD", "Part de marché", "Croissance", "Concurrents", "Produits"]]
        st.dataframe(format_dataframe_for_display(disp), width='stretch', height=420)

    with t_labs:
        section_title("Laboratoires leaders", "Classement officiel IQVIA par valeur, part de marché et croissance.")
        if labs.empty:
            st.info("Feuille 'Total Lab' absente du fichier IQVIA.")
        else:
            top_n = st.slider("Nombre de laboratoires affichés", 5, 40, 15, key="ov_labs_n")
            top = labs.head(top_n).copy()
            fig = px.bar(
                top.sort_values("Value_DZD"), x="Value_DZD", y="LABORATOIRE",
                orientation="h", color="Growth_PY", color_continuous_scale="RdYlGn",
                color_continuous_midpoint=0, title="Valeur de marché par laboratoire (couleur = croissance)",
            )
            fig.update_layout(coloraxis_colorbar_title="Croiss.", yaxis_title="", xaxis_title="Valeur DZD")
            st.plotly_chart(plotly_layout(fig, height=max(380, 26 * len(top))), width='stretch')

            disp = top.rename(columns={
                "LABORATOIRE": "Laboratoire", "Value_DZD": "Valeur DZD", "Value_USD": "Valeur USD",
                "Market_Share": "Part de marché", "Growth_PY": "Croissance", "Rank": "Rang",
            })[["Rang", "Laboratoire", "Valeur DZD", "Valeur USD", "Part de marché", "Croissance"]]
            st.dataframe(format_dataframe_for_display(disp), width='stretch', height=420)

    with t_momentum:
        section_title("Classes en plus forte croissance / déclin", "Filtre sur les classes matérielles (≥ 0,3% du marché) pour éviter le bruit.")
        material = classes[classes["Share"] >= 0.003].copy()
        material = material[material["Growth_PY"].notna()]
        growers = material.sort_values("Growth_PY", ascending=False).head(12)
        decliners = material.sort_values("Growth_PY", ascending=True).head(12)
        c1, c2 = st.columns(2)
        with c1:
            chips_row([chip("🟢 Momentum positif", "good")])
            fig = px.bar(growers.sort_values("Growth_PY"), x="Growth_PY", y="THERAPEUTIC_CLASS",
                         orientation="h", color_discrete_sequence=["#34D399"], title="Top croissance")
            fig.update_layout(yaxis_title="", xaxis_title="Croissance vs N-1", xaxis_tickformat=".0%")
            st.plotly_chart(plotly_layout(fig, height=400), width='stretch')
        with c2:
            chips_row([chip("🔴 En recul", "bad")])
            fig = px.bar(decliners.sort_values("Growth_PY", ascending=False), x="Growth_PY", y="THERAPEUTIC_CLASS",
                         orientation="h", color_discrete_sequence=["#F87171"], title="Top déclin")
            fig.update_layout(yaxis_title="", xaxis_title="Croissance vs N-1", xaxis_tickformat=".0%")
            st.plotly_chart(plotly_layout(fig, height=400), width='stretch')

    st.caption(
        f"Sources : {meta.get('iqvia_file','—')} (marché ville) · {meta.get('nom_file','—')} (nomenclature) · "
        f"{meta.get('pch_file','—')} (hospitalier). Conversion USD : 1 USD = {me.CONFIG['DZD_PER_USD']:.0f} DZD."
    )
