"""Product / DCI Analysis — search a molecule and get its full market read:
size (city + hospital), competitive landscape, local vs import footprint,
concentration and an Excel export."""

from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

import market_engine as me
from market_engine import (
    build_option_universe, build_opportunity_table, export_excel_bytes, facet_filter,
    filter_iqvia, filter_nomenclature, filter_options, filter_pch,
    get_nomenclature_dci_options, dci_input_to_list, safe_unique,
    nomenclature_origin_for_dci, compute_hhi, hhi_label, SRC_IQVIA, SRC_PCH,
)
from ui_theme import (
    hero, kpi_row, section_title, fmt_money, fmt_int, fmt_growth, growth_tone,
    format_dataframe_for_display, plotly_layout, chip, chips_row,
)


def _sidebar_controls(nom, iqvia, pch):
    with st.sidebar:
        st.markdown("### 🔎 Recherche DCI")
        dci_search = st.text_input(
            "Chercher une molécule (Nomenclature)",
            placeholder="ex: paracetamol, amoxicilline, dolutegravir",
            help="Quelques lettres suffisent. Les propositions viennent uniquement de la Nomenclature officielle.",
        )
        dci_options = get_nomenclature_dci_options(nom, dci_search, limit=350)
        previous = st.session_state.get("selected_dcis", [])
        dci_options = list(dict.fromkeys(list(previous) + list(dci_options)))
        selected_dcis = st.multiselect(
            "DCI sélectionnée(s)", dci_options, default=previous, key="selected_dcis",
            placeholder="Choisir une ou plusieurs DCI / associations",
        )
        dci_text = ", ".join(selected_dcis) if selected_dcis else dci_search
        markets = st.multiselect(
            "Marché analysé", [SRC_IQVIA, SRC_PCH], default=[SRC_IQVIA, SRC_PCH],
            help="Ville (IQVIA) et/ou hospitalier (PCH). Vide = les deux.",
        ) or [SRC_IQVIA, SRC_PCH]

        universe = build_option_universe(dci_text, markets, nom, iqvia, pch)
        st.markdown("---")
        st.markdown("### 🎛️ Filtres dynamiques")
        st.caption("Chaque filtre met à jour les autres.")

        cur_dos = st.session_state.get("dosage", [])
        cur_for = st.session_state.get("formes", [])
        cur_lab = st.session_state.get("labs", [])
        cur_sta = st.session_state.get("statuts", [])

        dosage_search = st.text_input("Dosage", placeholder="ex: 1 g, 500 mg, 5 mg/ml")
        base = dict(dosage=cur_dos, formes=cur_for, labs=cur_lab, statuts=cur_sta, markets=markets)
        dosage_options = [] if universe.empty else filter_options(safe_unique(facet_filter(universe, **base, ignore={"dosage"})["dosage"], 1200), dosage_search, 350)
        cur_dos = [x for x in cur_dos if x in dosage_options]
        dosage = st.multiselect("Dosage(s)", dosage_options, default=cur_dos, key="dosage", label_visibility="collapsed")

        forme_search = st.text_input("Forme", placeholder="ex: injectable, comprimé")
        base = dict(dosage=dosage, formes=cur_for, labs=cur_lab, statuts=cur_sta, markets=markets)
        forme_options = [] if universe.empty else filter_options(safe_unique(facet_filter(universe, **base, ignore={"forme"})["forme"], 600), forme_search, 200)
        cur_for = [x for x in cur_for if x in forme_options]
        formes = st.multiselect("Forme(s)", forme_options, default=cur_for, key="formes", label_visibility="collapsed")

        base = dict(dosage=dosage, formes=formes, labs=cur_lab, statuts=cur_sta, markets=markets)
        lab_options = [] if universe.empty else safe_unique(facet_filter(universe, **base, ignore={"lab"})["lab"], 2000)
        cur_lab = [x for x in cur_lab if x in lab_options]
        labs = st.multiselect("Laboratoire(s)", lab_options, default=cur_lab, key="labs",
                              placeholder="Filtrer par laboratoire")

        base = dict(dosage=dosage, formes=formes, labs=labs, statuts=cur_sta, markets=markets)
        statut_options = [] if universe.empty else [x for x in safe_unique(facet_filter(universe, **base, ignore={"statut"})["statut"], 80) if x]
        cur_sta = [x for x in cur_sta if x in statut_options]
        statuts = st.multiselect("Statut Nomenclature", statut_options, default=cur_sta, key="statuts")

        live = pd.DataFrame() if universe.empty else facet_filter(universe, dosage=dosage, formes=formes, labs=labs, statuts=statuts, markets=markets)
        st.markdown("---")
        st.markdown(f"**Candidats actifs :** `{len(live):,}`")
        if not live.empty:
            st.caption(
                f"Nomenclature {(live['source']=='NOMENCLATURE').sum():,} · "
                f"IQVIA {(live['source']==SRC_IQVIA).sum():,} · PCH {(live['source']==SRC_PCH).sum():,}"
            )
    return dci_search, selected_dcis, dci_text, markets, universe, live, dosage, formes, labs, statuts


def _competitive_landscape(market_detail, nom, dci_list):
    """Players table (city+hospital combined), shares, growth, local vs import."""
    if market_detail is None or market_detail.empty:
        return
    section_title("🏟️ Paysage concurrentiel", "Acteurs présents sur le marché, parts, croissance et empreinte locale vs import.")

    by_lab = market_detail.groupby("LABORATOIRE", dropna=False).agg(
        Value_DZD=("Market_Size_Value_DZD", "sum"),
        Volume=("Market_Size_Volume", "sum"),
    ).reset_index()
    # value-weighted growth per lab
    gr = market_detail.groupby("LABORATOIRE").apply(
        lambda d: me.weighted_growth_py(d["Market_Size_Value_DZD"], d.get("Growth_PY", pd.Series(dtype=float)))
    ).rename("Growth_PY").reset_index()
    by_lab = by_lab.merge(gr, on="LABORATOIRE", how="left")
    total = by_lab["Value_DZD"].sum()
    by_lab["Share"] = np.where(total > 0, by_lab["Value_DZD"] / total, np.nan)
    by_lab = by_lab.sort_values("Value_DZD", ascending=False).reset_index(drop=True)

    origin = nomenclature_origin_for_dci(nom, dci_list)
    n_local, n_import = len(origin["local_labs"]), len(origin["import_labs"])
    hhi = compute_hhi(by_lab["Share"])

    chips_row([
        chip(f"🏭 {n_local} fabricant(s) local(aux)", "good" if n_local else "warn"),
        chip(f"📦 {n_import} importateur(s)", "default"),
        chip(f"📊 Concentration : {hhi_label(hhi)} (HHI {fmt_int(hhi)})", "bad" if (hhi or 0) >= 2500 else "good"),
    ])

    c1, c2 = st.columns([0.52, 0.48])
    with c1:
        top = by_lab.head(12)
        fig = px.pie(top, names="LABORATOIRE", values="Value_DZD", hole=0.45, title="Parts de marché (top 12)")
        fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(plotly_layout(fig, height=380), width='stretch')
    with c2:
        top = by_lab.head(12)
        fig = px.bar(top.sort_values("Growth_PY"), x="Growth_PY", y="LABORATOIRE", orientation="h",
                     color="Growth_PY", color_continuous_scale="RdYlGn", color_continuous_midpoint=0,
                     title="Croissance des acteurs")
        fig.update_layout(yaxis_title="", xaxis_title="Croissance vs N-1", xaxis_tickformat=".0%", coloraxis_showscale=False)
        st.plotly_chart(plotly_layout(fig, height=380), width='stretch')

    disp = by_lab.rename(columns={
        "LABORATOIRE": "Laboratoire", "Value_DZD": "Valeur DZD", "Share": "Part de marché",
        "Growth_PY": "Croissance", "Volume": "Volume",
    })[["Laboratoire", "Valeur DZD", "Part de marché", "Croissance", "Volume"]]
    st.dataframe(format_dataframe_for_display(disp), width='stretch', height=320)

    if n_local or n_import:
        with st.expander("🏭 Détail fabricants locaux vs importateurs (Nomenclature active)", expanded=False):
            cc1, cc2 = st.columns(2)
            cc1.markdown("**Fabricants locaux**")
            cc1.markdown("\n".join(f"- {l}" for l in origin["local_labs"]) or "_Aucun_")
            cc2.markdown("**Importateurs**")
            cc2.markdown("\n".join(f"- {l}" for l in origin["import_labs"]) or "_Aucun_")
    return disp


def render_market_analysis_page(data: dict) -> None:
    nom, iqvia, pch = data["nom"], data["iqvia"], data["pch"]

    hero(
        "Analyse produit<br/>& opportunité DCI",
        "Recherche stricte et pharma-safe par DCI, filtres connectés, marché ville (IQVIA) et hospitalier (PCH), "
        "paysage concurrentiel, empreinte locale vs import et export Excel prêt pour décision.",
        badge="🔬 Product & DCI Analysis",
    )

    (dci_search, selected_dcis, dci_text, markets, universe, live,
     dosage, formes, labs, statuts) = _sidebar_controls(nom, iqvia, pch)

    run = st.button("🚀 Lancer l'analyse", width='stretch', type="primary")

    if not dci_text.strip():
        st.info("👈 Tape une DCI dans la barre latérale puis sélectionne une proposition issue de la Nomenclature.")
        return
    if universe.empty:
        st.warning("Aucun candidat trouvé pour cette DCI. Élargis l'orthographe ou retire des filtres.")
        return

    kpi_row([
        ("Candidats", fmt_int(len(live)), "intersection filtres"),
        ("Laboratoires", fmt_int(live["lab"].replace("", pd.NA).dropna().nunique()), "acteurs potentiels"),
        ("Formes", fmt_int(live["forme"].replace("", pd.NA).dropna().nunique()), "formes associées"),
        ("Sources", fmt_int(live["source"].nunique()), "nomenclature / marchés"),
    ])

    preview_dcis = dci_input_to_list(selected_dcis, dci_search)
    with st.expander("👁️ Aperçu des lignes associées", expanded=False):
        pn = filter_nomenclature(nom, preview_dcis, dosage, formes, labs, statuts) if preview_dcis else pd.DataFrame()
        pi = filter_iqvia(iqvia, preview_dcis, dosage, formes, labs) if preview_dcis and SRC_IQVIA in markets else pd.DataFrame()
        pp = filter_pch(pch, preview_dcis, dosage, formes, labs) if preview_dcis and SRC_PCH in markets else pd.DataFrame()
        tn, ti, tp = st.tabs([f"📚 Nomenclature ({len(pn):,})", f"🏙️ IQVIA ville ({len(pi):,})", f"🏥 PCH hospitalier ({len(pp):,})"])
        with tn:
            cols = [c for c in ["_QUERY_DCI", "DCI", "BRAND", "FORME", "DOSAGE", "CONDITIONNEMENT", "LABORATOIRE", "PAYS", "STATUT", "TYPE", "ORIGIN", "SOURCE_NOMENCLATURE"] if c in pn.columns]
            st.dataframe(format_dataframe_for_display(pn[cols].head(1000)) if not pn.empty else pd.DataFrame(), width='stretch', height=340)
        with ti:
            cols = [c for c in ["_QUERY_DCI", "MOLECULE", "BRAND", "PRESENTATION", "LABORATOIRE", "THERAPEUTIC_CLASS", "MARKET_VOLUME", "MARKET_VALUE_DZD", "GROWTH_PY"] if c in pi.columns]
            st.dataframe(format_dataframe_for_display(pi[cols].head(1000)) if not pi.empty else pd.DataFrame(), width='stretch', height=340)
        with tp:
            cols = [c for c in ["_QUERY_DCI", "PRODUCT_FULL", "LABORATOIRE", "THERAPEUTIC_CLASS", "QTE", "UNIT_PRICE", "DEVISE", "MARKET_VALUE_DZD", "DATESTOCKAGE"] if c in pp.columns]
            st.dataframe(format_dataframe_for_display(pp[cols].head(1000)) if not pp.empty else pd.DataFrame(), width='stretch', height=340)

    if run:
        dci_list = dci_input_to_list(selected_dcis, dci_search)
        with st.spinner("Matching intelligent · agrégation des marchés · calcul de la concurrence…"):
            nom_m = filter_nomenclature(nom, dci_list, dosage, formes, labs, statuts)
            iq_m = filter_iqvia(iqvia, dci_list, dosage, formes, labs) if SRC_IQVIA in markets else pd.DataFrame()
            pch_m = filter_pch(pch, dci_list, dosage, formes, labs) if SRC_PCH in markets else pd.DataFrame()
            main, market_detail, nom_detail = build_opportunity_table(nom_m, iq_m, pch_m)
            st.session_state["analysis_result"] = (main, market_detail, nom_detail, dci_list)

    if "analysis_result" not in st.session_state:
        st.info("Configure tes filtres puis clique **Lancer l'analyse**.")
        return

    main, market_detail, nom_detail, dci_list = st.session_state["analysis_result"]
    if main.empty:
        st.warning("Analyse terminée, mais aucun marché agrégé exploitable avec ces filtres.")
        return

    st.success("Analyse terminée — résultat prêt à exporter.")

    total_dzd = main["Valeur DZD"].sum() if "Valeur DZD" in main else 0
    total_usd = main["Valeur USD"].sum() if "Valeur USD" in main else 0
    total_vol = main["Volume"].sum() if "Volume" in main else 0
    n_players = market_detail["LABORATOIRE"].replace("", pd.NA).dropna().nunique() if not market_detail.empty else 0
    overall_growth = me.weighted_growth_py(market_detail.get("Market_Size_Value_DZD", pd.Series(dtype=float)),
                                           market_detail.get("Growth_PY", pd.Series(dtype=float))) if not market_detail.empty else np.nan
    kpi_row([
        ("Marché total DZD", fmt_money(total_dzd), f"≈ {fmt_money(total_usd, '$')} USD"),
        ("Croissance vs N-1", fmt_growth(overall_growth), "ville (IQVIA)", growth_tone(overall_growth)),
        ("Volume", fmt_money(total_vol), "unités / réceptions"),
        ("Concurrents", fmt_int(n_players), "laboratoires détectés"),
    ])

    comp_disp = _competitive_landscape(market_detail, nom, dci_list)

    # City vs hospital split
    ville = market_detail[market_detail["SOURCE_MARKET"].eq(SRC_IQVIA)].copy()
    hosp = market_detail[market_detail["SOURCE_MARKET"].eq(SRC_PCH)].copy()

    def _clean(df):
        if df is None or df.empty:
            return pd.DataFrame()
        x = df.rename(columns={
            "_QUERY_DCI": "DCI", "PRODUCT_FULL": "Produit", "LABORATOIRE": "Laboratoire",
            "Therapeutic_Class": "Classe", "Market_Size_Volume": "Volume",
            "Market_Size_Value_DZD": "Valeur DZD", "Market_Size_Value_USD": "Valeur USD", "Growth_PY": "Croissance",
        })
        cols = [c for c in ["DCI", "Produit", "Laboratoire", "Classe", "Volume", "Valeur DZD", "Valeur USD", "Croissance"] if c in x.columns]
        return x[cols]

    ville_disp, hosp_disp = _clean(ville), _clean(hosp)
    summary_disp = main.drop(columns=[c for c in ["Dossier nomenclature"] if c in main.columns])

    st.download_button(
        "⬇️ Télécharger l'analyse complète (Excel)",
        data=export_excel_bytes(
            ("Synthese", summary_disp),
            ("Concurrence", comp_disp if comp_disp is not None else pd.DataFrame()),
            ("Marche ville IQVIA", ville_disp),
            ("Hospitalier PCH", hosp_disp),
        ),
        file_name=f"analyse_dci_{datetime.now():%Y%m%d_%H%M}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width='stretch',
    )

    t_syn, t_ville, t_hosp, t_nom = st.tabs(["📌 Synthèse", "🏙️ Marché ville", "🏥 Hospitalier PCH", "📚 Nomenclature"])
    with t_syn:
        st.dataframe(format_dataframe_for_display(summary_disp), width='stretch', height=420)
    with t_ville:
        st.dataframe(format_dataframe_for_display(ville_disp) if not ville_disp.empty else pd.DataFrame(), width='stretch', height=460) if not ville_disp.empty else st.info("Aucune donnée IQVIA ville pour ces filtres.")
    with t_hosp:
        st.dataframe(format_dataframe_for_display(hosp_disp) if not hosp_disp.empty else pd.DataFrame(), width='stretch', height=460) if not hosp_disp.empty else st.info("Aucune donnée hospitalière PCH pour ces filtres.")
    with t_nom:
        if nom_detail is not None and not nom_detail.empty:
            cols = [c for c in ["_QUERY_DCI", "DCI", "BRAND", "FORME", "DOSAGE", "CONDITIONNEMENT", "LABORATOIRE", "PAYS", "STATUT", "TYPE", "ORIGIN", "SOURCE_NOMENCLATURE"] if c in nom_detail.columns]
            st.dataframe(format_dataframe_for_display(nom_detail[cols].head(1500)), width='stretch', height=460)
        else:
            st.info("Aucun match nomenclature avec les filtres actuels.")
