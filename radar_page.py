"""Radar — opportunity & registration signals.
  • Nouveaux enregistrements : DCI enregistrées récemment, marché attractif, peu de concurrence.
  • Expirations / renouvellements : produits dont l'enregistrement arrive à échéance.
  • White spaces : marchés réels sans fabricant local (substitution import)."""

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

import market_engine as me
from strategic_recommendations import build_recommendations
from ui_theme import (
    hero, kpi_row, section_title, fmt_money, fmt_int, fmt_growth,
    format_dataframe_for_display, plotly_layout, chip, chips_row,
)


@st.cache_data(show_spinner=False)
def _recommendations(_nom, _iqvia, _pch, sig):
    recs, _ = build_recommendations(_nom, _iqvia, _pch, [me.SRC_IQVIA, me.SRC_PCH], active_only=True)
    return recs


@st.cache_data(show_spinner=False)
def _dci_dates(_nom, sig):
    return me.nomenclature_dci_dates(_nom, active_only=True)


def _data_sig(meta):
    return f"{meta.get('iqvia_file')}|{meta.get('nom_file')}|{meta.get('pch_file')}"


def _render_new_registrations(recs, dates):
    section_title("Nouveaux enregistrements à fort potentiel",
                  "DCI enregistrées récemment, sur un marché attractif et encore peu disputé.")
    c1, c2, c3 = st.columns(3)
    months = c1.slider("Enregistré il y a moins de (mois)", 3, 36, 6, 1)
    min_usd = c2.number_input("Marché minimum (USD)", min_value=0, value=500_000, step=100_000)
    max_comp = c3.slider("Concurrents maximum", 0, 10, 2, 1)

    if recs.empty or dates.empty:
        st.info("Données insuffisantes.")
        return
    m = recs.merge(dates[["DCI", "Last_registration", "Next_expiry"]], on="DCI", how="left")
    m["Concurrents"] = pd.to_numeric(m.get("Manufacturers", 0), errors="coerce").fillna(0) + pd.to_numeric(m.get("Importers", 0), errors="coerce").fillna(0)
    cutoff = pd.Timestamp.now() - pd.DateOffset(months=months)
    sel = m[(pd.to_datetime(m["Last_registration"], errors="coerce") >= cutoff)
            & (m["Market value USD"] >= min_usd)
            & (m["Concurrents"] <= max_comp)].copy()
    sel = sel.sort_values(["Market value USD"], ascending=False)

    kpi_row([
        ("Opportunités détectées", fmt_int(len(sel)), f"≤ {months} mois · ≤ {max_comp} conc."),
        ("Marché cumulé", fmt_money(sel["Market value USD"].sum(), "$"), "adressable"),
        ("Sans fabricant local", fmt_int(int((sel.get("Manufacturers", pd.Series(dtype=int)) == 0).sum())), "white space"),
        ("Marché médian", fmt_money(sel["Market value USD"].median() if len(sel) else 0, "$"), "par opportunité"),
    ])
    if sel.empty:
        st.info("Aucune opportunité avec ces critères. Élargis la période, baisse le marché minimum ou augmente le nb de concurrents.")
        return
    disp = sel.rename(columns={
        "Market value USD": "Marché USD", "Market value DZD": "Marché DZD", "Growth_PY": "Croissance",
        "Manufacturers": "Fabricants", "Importers": "Importateurs", "Last_registration": "Dernier enregistrement",
        "Top market products": "Produits", "Sources found": "Sources",
    })
    cols = [c for c in ["DCI", "Dernier enregistrement", "Marché USD", "Croissance", "Concurrents",
                        "Fabricants", "Importateurs", "Sources", "Produits"] if c in disp.columns]
    st.dataframe(format_dataframe_for_display(disp[cols]), width='stretch', height=460)
    st.download_button("⬇️ Exporter (Excel)", data=me.export_excel_bytes(("Nouveaux enregistrements", disp[cols])),
                       file_name="radar_nouveaux_enregistrements.xlsx", width='stretch',
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def _render_expirations(nom):
    section_title("Expirations / renouvellements à venir",
                  "Produits dont l'enregistrement arrive à échéance — fenêtre d'opportunité si un concurrent ne renouvelle pas.")
    c1, c2 = st.columns(2)
    validity = c1.slider("Validité d'un enregistrement (ans)", 3, 10, 5, 1,
                         help="L'échéance est estimée = dernière décision + validité.")
    horizon = c2.slider("Horizon (mois)", 3, 36, 24, 1)

    x = nom[nom["SOURCE_NOMENCLATURE"].astype(str).str.upper().eq("ACTIVE")].copy() if "SOURCE_NOMENCLATURE" in nom.columns else nom.copy()
    last = pd.to_datetime(x["DATE_ENR_FINAL"], errors="coerce").fillna(pd.to_datetime(x["DATE_ENR_INITIAL"], errors="coerce"))
    x["Echeance_estimee"] = last + pd.DateOffset(years=validity)
    now = pd.Timestamp.now()
    upper = now + pd.DateOffset(months=horizon)
    sel = x[(x["Echeance_estimee"].notna()) & (x["Echeance_estimee"] >= now - pd.DateOffset(months=6)) & (x["Echeance_estimee"] <= upper)].copy()
    sel = sel.sort_values("Echeance_estimee")

    chips_row([chip(f"⏳ Échéance estimée = dernière décision + {validity} ans", "warn"),
               chip(f"🔭 Fenêtre : prochains {horizon} mois", "default")])
    kpi_row([
        ("Produits concernés", fmt_int(len(sel)), f"≤ {horizon} mois"),
        ("DCI distinctes", fmt_int(sel["DCI"].nunique() if len(sel) else 0), "molécules"),
        ("Laboratoires", fmt_int(sel["LABORATOIRE"].nunique() if len(sel) else 0), "détenteurs"),
        ("Dont importés", fmt_int(int((sel.get("ORIGIN", pd.Series(dtype=str)) == "IMPORT").sum())), "I"),
    ])
    if sel.empty:
        st.info("Aucune échéance dans cette fenêtre. Augmente l'horizon ou ajuste la validité.")
        return
    disp = sel.rename(columns={
        "DCI": "DCI", "BRAND": "Produit", "LABORATOIRE": "Laboratoire", "PAYS": "Pays",
        "FORME": "Forme", "DOSAGE": "Dosage", "ORIGIN": "Origine",
        "DATE_ENR_FINAL": "Dernière décision", "Echeance_estimee": "Échéance estimée",
    })
    cols = [c for c in ["DCI", "Produit", "Laboratoire", "Pays", "Origine", "Forme", "Dosage",
                        "Dernière décision", "Échéance estimée"] if c in disp.columns]
    disp = disp[cols].copy()
    for dc in ["Dernière décision", "Échéance estimée"]:
        if dc in disp.columns:
            disp[dc] = pd.to_datetime(disp[dc], errors="coerce").dt.date.astype(str)
    st.dataframe(disp, width='stretch', height=460)
    st.download_button("⬇️ Exporter (Excel)", data=me.export_excel_bytes(("Expirations", disp)),
                       file_name="radar_expirations.xlsx", width='stretch',
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def _render_white_spaces(recs):
    section_title("White spaces — marchés sans fabricant local",
                  "Demande réelle (marché IQVIA/PCH) mais aucun fabricant local : cibles prioritaires de production locale.")
    min_usd = st.number_input("Marché minimum (USD)", min_value=0, value=300_000, step=100_000, key="ws_min")
    if recs.empty:
        st.info("Données insuffisantes.")
        return
    sel = recs[(recs.get("Manufacturers", 1) == 0) & (recs["Market value USD"] >= min_usd)].copy()
    sel = sel.sort_values("Market value USD", ascending=False)
    kpi_row([
        ("White spaces", fmt_int(len(sel)), f"marché ≥ {fmt_money(min_usd,'$')}"),
        ("Marché cumulé", fmt_money(sel["Market value USD"].sum(), "$"), "adressable"),
        ("Avec demande import", fmt_int(int((sel.get("Importers", pd.Series(dtype=int)) > 0).sum())), "substitution"),
        ("Marché médian", fmt_money(sel["Market value USD"].median() if len(sel) else 0, "$"), "par molécule"),
    ])
    if sel.empty:
        st.info("Aucun white space avec ce seuil.")
        return
    top = sel.head(25)
    fig = px.bar(top.sort_values("Market value USD"), x="Market value USD", y="DCI", orientation="h",
                 color="Importers", color_continuous_scale="Tealgrn", title="Top white spaces par valeur (couleur = importateurs)")
    fig.update_layout(yaxis_title="", xaxis_title="Marché USD")
    st.plotly_chart(plotly_layout(fig, height=max(380, 22 * len(top))), width='stretch')
    disp = sel.rename(columns={
        "Market value USD": "Marché USD", "Growth_PY": "Croissance", "Importers": "Importateurs",
        "Importer labs": "Importateurs (labos)", "Top market products": "Produits", "Sources found": "Sources",
    })
    cols = [c for c in ["DCI", "Marché USD", "Croissance", "Importateurs", "Sources", "Importateurs (labos)", "Produits"] if c in disp.columns]
    st.dataframe(format_dataframe_for_display(disp[cols]), width='stretch', height=420)
    st.download_button("⬇️ Exporter (Excel)", data=me.export_excel_bytes(("White spaces", disp[cols])),
                       file_name="radar_white_spaces.xlsx", width='stretch',
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def render_radar_page(data: dict) -> None:
    nom, iqvia, pch = data["nom"], data["iqvia"], data["pch"]
    meta = data.get("meta", {})

    hero(
        "Radar<br/>opportunités",
        "Trois signaux automatiques : nouveaux enregistrements à fort potentiel, échéances de "
        "renouvellement, et marchés sans fabricant local. Tous les seuils sont ajustables.",
        badge="📡 Opportunity Radar",
    )

    sig = _data_sig(meta)
    with st.spinner("Calcul des marchés et de la concurrence par DCI…"):
        recs = _recommendations(nom, iqvia, pch, sig)
        dates = _dci_dates(nom, sig)

    t1, t2, t3 = st.tabs(["🆕 Nouveaux enregistrements", "⏳ Expirations / renouvellements", "⚪ White spaces"])
    with t1:
        _render_new_registrations(recs, dates)
    with t2:
        _render_expirations(nom)
    with t3:
        _render_white_spaces(recs)
