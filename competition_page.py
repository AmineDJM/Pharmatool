"""Competitive Landscape — analyse the competition two ways:
  • inside a therapeutic class (who competes, shares, growth, concentration)
  • for a given laboratory (portfolio, exposure, momentum)."""

import plotly.express as px
import streamlit as st

import market_engine as me
from ui_theme import (
    hero, kpi_row, section_title, fmt_money, fmt_int, fmt_pct, fmt_growth,
    growth_tone, format_dataframe_for_display, plotly_layout, chip, chips_row,
)


@st.cache_data(show_spinner=False)
def _class_options(_iqvia):
    return me.class_list(_iqvia)


@st.cache_data(show_spinner=False)
def _lab_options(_iqvia):
    return me.lab_list_iqvia(_iqvia)


@st.cache_data(show_spinner=False)
def _class_competition(_iqvia, class_name, fx):
    return me.class_competition(_iqvia, class_name)


@st.cache_data(show_spinner=False)
def _lab_portfolio(_iqvia, lab_name, fx):
    return me.lab_portfolio(_iqvia, lab_name)


def _render_by_class(iqvia, nom):
    classes = _class_options(iqvia)
    if not classes:
        st.info("Aucune classe thérapeutique disponible.")
        return
    pick = st.selectbox("Classe thérapeutique (ATC4)", classes, key="comp_class",
                        help="Choisis une classe pour voir tous les acteurs, parts, croissance et concentration.")
    labs, products, summ = _class_competition(iqvia, pick, me.CONFIG["DZD_PER_USD"])
    if labs.empty:
        st.info("Aucune donnée pour cette classe.")
        return

    kpi_row([
        ("Valeur classe", fmt_money(summ["value_dzd"]), f"≈ {fmt_money(summ['value_usd'], '$')} USD"),
        ("Croissance vs N-1", fmt_growth(summ["growth_py"]), "valeur", growth_tone(summ["growth_py"])),
        ("Concurrents", fmt_int(summ["n_labs"]), f"{summ['n_products']} produits"),
        ("Concentration", me.hhi_label(summ["hhi"]), f"HHI {fmt_int(summ['hhi'])} · leader {fmt_pct(summ['leader_share'])}",
         "bad" if (summ["hhi"] or 0) >= 2500 else "good"),
    ])

    chips_row([
        chip(f"🥇 Leader : {summ['leader']} ({fmt_pct(summ['leader_share'])})", "accent"),
        chip(f"🧪 {summ['n_products']} produits", "default"),
        chip(f"🏭 {summ['n_labs']} laboratoires", "default"),
    ])

    c1, c2 = st.columns([0.55, 0.45])
    with c1:
        section_title("Parts de marché des concurrents")
        top = labs.head(12).copy()
        fig = px.pie(top, names="LABORATOIRE", values="Value_DZD", hole=0.45,
                     title="Répartition de la valeur (top 12)")
        fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(plotly_layout(fig, height=420), width='stretch')
    with c2:
        section_title("Croissance des principaux acteurs")
        top = labs.head(12).copy()
        fig = px.bar(top.sort_values("Growth_PY"), x="Growth_PY", y="LABORATOIRE", orientation="h",
                     color="Growth_PY", color_continuous_scale="RdYlGn", color_continuous_midpoint=0)
        fig.update_layout(yaxis_title="", xaxis_title="Croissance vs N-1", xaxis_tickformat=".0%", coloraxis_showscale=False)
        st.plotly_chart(plotly_layout(fig, height=420), width='stretch')

    section_title("Tableau concurrentiel — laboratoires")
    disp = labs.rename(columns={
        "LABORATOIRE": "Laboratoire", "Value_DZD": "Valeur DZD", "Value_USD": "Valeur USD",
        "Share": "Part de marché", "Growth_PY": "Croissance", "Products": "Produits", "Volume": "Volume",
    })[["Laboratoire", "Valeur DZD", "Valeur USD", "Part de marché", "Croissance", "Produits", "Volume"]]
    st.dataframe(format_dataframe_for_display(disp), width='stretch', height=360)

    with st.expander(f"🧪 Détail produits de la classe ({len(products)})", expanded=False):
        pdisp = products.rename(columns={
            "BRAND": "Produit", "LABORATOIRE": "Laboratoire", "Value_DZD": "Valeur DZD",
            "Value_USD": "Valeur USD", "Share": "Part de marché", "Growth_PY": "Croissance", "Volume": "Volume",
        })[["Produit", "Laboratoire", "Valeur DZD", "Valeur USD", "Part de marché", "Croissance", "Volume"]]
        st.dataframe(format_dataframe_for_display(pdisp), width='stretch', height=420)

    from market_engine import export_excel_bytes
    st.download_button(
        "⬇️ Exporter cette classe (Excel)",
        data=export_excel_bytes(("Concurrents", disp), ("Produits", products)),
        file_name=f"concurrence_{str(pick).split()[0]}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width='stretch',
    )


def _render_by_lab(iqvia):
    labs = _lab_options(iqvia)
    if not labs:
        st.info("Aucun laboratoire disponible.")
        return
    default_idx = labs.index("EL KENDI") if "EL KENDI" in labs else 0
    pick = st.selectbox("Laboratoire", labs, index=default_idx, key="comp_lab")
    by_class, products, summ = _lab_portfolio(iqvia, pick, me.CONFIG["DZD_PER_USD"])
    if by_class.empty:
        st.info("Aucune donnée pour ce laboratoire.")
        return

    kpi_row([
        ("Chiffre marché", fmt_money(summ["value_dzd"]), f"≈ {fmt_money(summ['value_usd'], '$')} USD"),
        ("Croissance vs N-1", fmt_growth(summ["growth_py"]), "valeur", growth_tone(summ["growth_py"])),
        ("Classes couvertes", fmt_int(summ["n_classes"]), "présence thérapeutique"),
        ("Produits", fmt_int(summ["n_products"]), "références actives"),
    ])

    section_title("Répartition du portefeuille par classe thérapeutique")
    top = by_class.head(15).copy()
    fig = px.bar(top.sort_values("Value_DZD"), x="Value_DZD", y="THERAPEUTIC_CLASS", orientation="h",
                 color="Growth_PY", color_continuous_scale="RdYlGn", color_continuous_midpoint=0,
                 title="Valeur par classe (couleur = croissance)")
    fig.update_layout(yaxis_title="", xaxis_title="Valeur DZD", coloraxis_colorbar_title="Croiss.")
    st.plotly_chart(plotly_layout(fig, height=max(380, 26 * len(top))), width='stretch')

    cdisp = by_class.rename(columns={
        "THERAPEUTIC_CLASS": "Classe thérapeutique", "Value_DZD": "Valeur DZD", "Value_USD": "Valeur USD",
        "Growth_PY": "Croissance", "Products": "Produits", "Volume": "Volume",
    })[["Classe thérapeutique", "Valeur DZD", "Valeur USD", "Croissance", "Produits"]]
    st.dataframe(format_dataframe_for_display(cdisp), width='stretch', height=340)

    with st.expander(f"🧪 Produits du laboratoire ({len(products)})", expanded=False):
        pdisp = products.rename(columns={
            "BRAND": "Produit", "PRESENTATION": "Présentation", "THERAPEUTIC_CLASS": "Classe",
            "MARKET_VALUE_DZD": "Valeur DZD", "MARKET_VOLUME": "Volume", "GROWTH_PY": "Croissance",
        })[["Produit", "Présentation", "Classe", "Valeur DZD", "Volume", "Croissance"]]
        st.dataframe(format_dataframe_for_display(pdisp), width='stretch', height=420)


def render_competition_page(data: dict) -> None:
    iqvia = data["iqvia"]
    nom = data["nom"]

    hero(
        "Analyse<br/>concurrentielle",
        "Cartographie de la concurrence sur le marché de ville IQVIA : parts de marché, croissance "
        "des acteurs, concentration (indice HHI) et portefeuilles laboratoires. Choisis un angle ci-dessous.",
        badge="🏟️ Competitive Landscape",
    )

    mode = st.radio(
        "Angle d'analyse", ["Par classe thérapeutique", "Par laboratoire"],
        horizontal=True, key="comp_mode", label_visibility="collapsed",
    )
    st.markdown("---")
    if mode == "Par laboratoire":
        _render_by_lab(iqvia)
    else:
        _render_by_class(iqvia, nom)
