"""Pricing — intelligent price lookup.
Type a molecule (optionally with dosage/forme); the app detects the DCI, dosage
and forme, then returns retail (IQVIA ville) and hospital (PCH) prices with range
and per-product detail."""

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

import market_engine as me
from market_engine import parse_smart_query, price_for_dci, SRC_IQVIA, SRC_PCH
from ui_theme import (
    hero, kpi_row, section_title, fmt_money, fmt_int, format_dataframe_for_display,
    plotly_layout, chip, chips_row,
)


@st.cache_data(show_spinner=False)
def _price(_iqvia, _pch, _nom, dci_list, dosage, formes, markets, fx):
    return price_for_dci(_iqvia, _pch, _nom, dci_list, dosage or None, formes or None, None, markets)


def _price_block(title, stats, unit_label):
    if not stats or not stats.get("n"):
        st.info(f"Aucune donnée de prix ({title}).")
        return
    kpi_row([
        (f"Prix moyen — {title}", fmt_money(stats["avg_dzd"], "DZD"), f"≈ {fmt_money(stats['avg_usd'], '$')} · {unit_label}"),
        ("Médiane", fmt_money(stats["median"], "DZD"), unit_label),
        ("Minimum", fmt_money(stats["min"], "DZD"), unit_label),
        ("Maximum", fmt_money(stats["max"], "DZD"), unit_label),
    ])


def render_pricing_page(data: dict) -> None:
    nom, iqvia, pch = data["nom"], data["iqvia"], data["pch"]

    hero(
        "Prix<br/>par molécule",
        "Tape une molécule (avec dosage et forme si tu veux) : l'outil reconnaît la DCI, le dosage et la "
        "forme, puis te donne le prix marché ville (IQVIA) et hospitalier (PCH), fourchette et détail par produit.",
        badge="💰 Pricing Intelligence",
    )

    query = st.text_input(
        "🔎 Recherche intelligente",
        placeholder="ex: amoxicilline 500 mg comprimé   ·   paracetamol 1 g   ·   insuline glargine",
        help="Tape librement : DCI + dosage + forme. L'outil détecte tout automatiquement.",
    )
    if not query.strip():
        st.info("👆 Tape une molécule pour obtenir son prix.")
        return

    parsed = parse_smart_query(query, nom)
    if not parsed["dci_candidates"]:
        st.warning("Aucune DCI reconnue. Essaie une autre orthographe.")
        return

    chips = [chip(f"🧬 DCI détectée : {parsed['dci_candidates'][0]}", "accent")]
    if parsed["dosage"]:
        chips.append(chip("💊 Dosage : " + ", ".join(parsed["dosage"]), "default"))
    if parsed["forme"]:
        chips.append(chip("🧪 Forme : " + ", ".join(parsed["forme"]), "default"))
    chips_row(chips)

    c1, c2, c3 = st.columns([0.5, 0.25, 0.25])
    with c1:
        dci = st.selectbox("DCI", parsed["dci_candidates"], index=0)
    with c2:
        use_dosage = st.toggle("Filtrer dosage", value=bool(parsed["dosage"]), disabled=not parsed["dosage"])
    with c3:
        use_forme = st.toggle("Filtrer forme", value=bool(parsed["forme"]), disabled=not parsed["forme"])

    dosage = parsed["dosage"] if (use_dosage and parsed["dosage"]) else None
    formes = parsed["forme"] if (use_forme and parsed["forme"]) else None
    markets = [SRC_IQVIA, SRC_PCH]

    res = _price(iqvia, pch, nom, [dci], dosage, formes, markets, me.CONFIG["DZD_PER_USD"])

    tab_ville, tab_hosp = st.tabs(["🏙️ Prix marché ville (IQVIA)", "🏥 Prix hospitalier (PCH)"])

    with tab_ville:
        _price_block("ville", res["ville"], "prix / boîte")
        rows = res["ville_rows"]
        if rows is not None and not rows.empty:
            disp = rows.rename(columns={
                "BRAND": "Produit", "PRESENTATION": "Présentation", "LABORATOIRE": "Laboratoire",
                "MARKET_VOLUME": "Volume", "MARKET_VALUE_DZD": "Valeur DZD",
                "Prix_boite_DZD": "Prix boîte DZD", "GROWTH_PY": "Croissance",
            })
            section_title("Prix par produit")
            st.dataframe(format_dataframe_for_display(disp), width='stretch', height=340)
            if disp["Prix boîte DZD"].notna().sum() > 1:
                fig = px.box(rows[rows["Prix_boite_DZD"].notna()], y="Prix_boite_DZD", points="all",
                             title="Distribution des prix / boîte (positionnement)")
                fig.update_layout(yaxis_title="Prix boîte DZD", xaxis_title="")
                st.plotly_chart(plotly_layout(fig, height=340), width='stretch')

    with tab_hosp:
        _price_block("hôpital", res["hospital"], "prix / unité")
        rows = res["hospital_rows"]
        if rows is not None and not rows.empty:
            disp = rows.rename(columns={
                "PRODUCT_FULL": "Produit", "LABORATOIRE": "Fournisseur", "QTE": "Quantité",
                "Prix_unitaire_DZD": "Prix unitaire DZD", "MARKET_VALUE_DZD": "Valeur DZD",
                "DEVISE": "Devise", "DATESTOCKAGE": "Date réception",
            })
            section_title("Réceptions hospitalières (prix unitaire)")
            st.dataframe(format_dataframe_for_display(disp), width='stretch', height=340)
