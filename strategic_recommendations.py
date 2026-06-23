"""Strategic Opportunities — automatic screening of DCIs worth launching or
manufacturing locally, combining IQVIA/PCH market size, YoY growth and the local
competitive intensity (fabricants vs importateurs) read from the Nomenclature.

Core rule: the smaller the market, the fewer local manufacturers it should
already have. Markets supplied only by imports are flagged as import-substitution
opportunities — a strategic priority for local production in Algeria."""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

import market_engine as me
from market_engine import CONFIG, norm_text, safe_unique, tokens, weighted_growth_py
from ui_theme import (
    hero, kpi_row, fmt_money, fmt_int, format_dataframe_for_display, plotly_layout,
)


DEFAULT_RULES = {"small_market_usd": 3_000_000.0, "large_market_usd": 7_000_000.0}


def _active_scope(nom: pd.DataFrame, active_only: bool) -> pd.DataFrame:
    if nom is None or nom.empty:
        return pd.DataFrame()
    x = nom.copy()
    if active_only and "SOURCE_NOMENCLATURE" in x.columns:
        x = x[x["SOURCE_NOMENCLATURE"].astype(str).str.upper().eq("ACTIVE")].copy()
    return x


@st.cache_data(show_spinner=False)
def build_competition_table(nom: pd.DataFrame, active_only: bool = True) -> pd.DataFrame:
    """Local manufacturers vs importers by controlled DCI, from the Nomenclature."""
    x = _active_scope(nom, active_only)
    if x.empty or "DCI" not in x.columns:
        return pd.DataFrame(columns=["DCI", "DCI_NORM_KEY", "Manufacturers", "Importers", "Other players", "Manufacturer labs", "Importer labs", "Nomenclature lines"])
    for c in ["DCI", "LABORATOIRE", "ORIGIN"]:
        if c not in x.columns:
            x[c] = ""
    x = x[x["DCI"].notna() & x["DCI"].astype(str).str.strip().ne("")].copy()
    x["DCI_NORM_KEY"] = x["DCI"].map(norm_text)
    x["LAB_CLEAN"] = x["LABORATOIRE"].fillna("").astype(str).str.strip()
    x = x[x["DCI_NORM_KEY"].ne("")]
    rows = []
    for key, g in x.groupby("DCI_NORM_KEY", dropna=False):
        dci_label = safe_unique(g["DCI"], 20)[0] if len(g) else key
        f_labs = sorted(set(g.loc[g["ORIGIN"].eq("LOCAL"), "LAB_CLEAN"].replace("", pd.NA).dropna()))
        i_labs = sorted(set(g.loc[g["ORIGIN"].eq("IMPORT"), "LAB_CLEAN"].replace("", pd.NA).dropna()))
        o_labs = sorted(set(g.loc[g["ORIGIN"].eq("OTHER"), "LAB_CLEAN"].replace("", pd.NA).dropna()))
        rows.append({
            "DCI": dci_label, "DCI_NORM_KEY": key,
            "Manufacturers": len(f_labs), "Importers": len(i_labs), "Other players": len(o_labs),
            "Manufacturer labs": "; ".join(f_labs[:12]), "Importer labs": "; ".join(i_labs[:12]),
            "Nomenclature lines": len(g),
        })
    return pd.DataFrame(rows)


def _dci_query_tokens(key: str) -> List[str]:
    return [t for t in tokens(key) if len(t) >= 3]


def _build_inverted_index(series_norm: pd.Series) -> Dict[str, Set[int]]:
    idx: Dict[str, Set[int]] = {}
    for i, text in series_norm.fillna("").astype(str).items():
        for tok in set(t for t in tokens(text) if len(t) >= 3):
            idx.setdefault(tok, set()).add(i)
    return idx


@st.cache_data(show_spinner=False)
def build_iqvia_market_by_dci(nom: pd.DataFrame, iqvia: pd.DataFrame, active_only: bool = True) -> pd.DataFrame:
    comp = build_competition_table(nom, active_only)
    if comp.empty or iqvia is None or iqvia.empty:
        return pd.DataFrame()
    x = iqvia.copy()
    grouped = {k: g for k, g in x.groupby("MOLECULE_NORM", dropna=False)}
    mol_norms = pd.Series(list(grouped.keys()), dtype="object")
    rows = []
    for _, d in comp.iterrows():
        key = d["DCI_NORM_KEY"]
        if not key:
            continue
        parts = []
        if key in grouped:
            parts.append(grouped[key])
        else:
            qtokens = _dci_query_tokens(key)
            if qtokens:
                mask = pd.Series(True, index=mol_norms.index)
                for tok in qtokens:
                    mask &= mol_norms.astype(str).str.contains(rf"(?<![A-Z0-9]){tok}(?![A-Z0-9])", regex=True, na=False)
                for ck in mol_norms[mask].tolist():
                    if ck in grouped:
                        parts.append(grouped[ck])
        if not parts:
            continue
        m = pd.concat(parts, ignore_index=False)
        if "PROD_KEY" in m.columns:  # de-dup combos so a product is counted once
            m = m.sort_values("MARKET_VALUE_DZD", ascending=False).drop_duplicates(subset=["PROD_KEY"])
        else:
            m = m.drop_duplicates()
        value = float(pd.to_numeric(m["MARKET_VALUE_DZD"], errors="coerce").fillna(0).sum())
        volume = float(pd.to_numeric(m["MARKET_VOLUME"], errors="coerce").fillna(0).sum())
        growth = weighted_growth_py(m["MARKET_VALUE_DZD"], m.get("GROWTH_PY", pd.Series(dtype=float)))
        labs = sorted(set(m["LABORATOIRE"].fillna("").astype(str).str.strip().replace("", pd.NA).dropna()))
        products = "; ".join(m.sort_values("MARKET_VALUE_DZD", ascending=False)["PRODUCT_FULL"].fillna("").astype(str).head(5))
        rows.append({"DCI_NORM_KEY": key, "DCI": d["DCI"], "Source": me.SRC_IQVIA,
                     "Market value DZD": value, "Market value USD": value / CONFIG["DZD_PER_USD"],
                     "Market volume": volume, "Growth_PY": growth, "Market labs detected": len(labs),
                     "Top market products": products})
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def build_pch_market_by_dci(nom: pd.DataFrame, pch: pd.DataFrame, active_only: bool = True) -> pd.DataFrame:
    comp = build_competition_table(nom, active_only)
    if comp.empty or pch is None or pch.empty:
        return pd.DataFrame()
    x = pch.copy()
    inv = _build_inverted_index(x["TEXT_NORM"])
    rows = []
    for _, d in comp.iterrows():
        key = d["DCI_NORM_KEY"]
        qtokens = _dci_query_tokens(key)
        if not qtokens:
            continue
        sets = [inv.get(tok, set()) for tok in qtokens]
        if not sets or any(len(s) == 0 for s in sets):
            continue
        matched = set.intersection(*sets)
        if not matched:
            continue
        m = x.loc[sorted(matched)].copy()
        for tok in qtokens:
            m = m[m["TEXT_NORM"].fillna("").astype(str).str.contains(rf"(?<![A-Z0-9]){tok}(?![A-Z0-9])", regex=True, na=False)]
        if m.empty:
            continue
        value = float(pd.to_numeric(m["MARKET_VALUE_DZD"], errors="coerce").fillna(0).sum())
        volume = float(pd.to_numeric(m["MARKET_VOLUME"], errors="coerce").fillna(0).sum())
        labs = sorted(set(m["LABORATOIRE"].fillna("").astype(str).str.strip().replace("", pd.NA).dropna()))
        products = "; ".join(m.sort_values("MARKET_VALUE_DZD", ascending=False)["PRODUCT_FULL"].fillna("").astype(str).head(5))
        rows.append({"DCI_NORM_KEY": key, "DCI": d["DCI"], "Source": me.SRC_PCH,
                     "Market value DZD": value, "Market value USD": value / CONFIG["DZD_PER_USD"],
                     "Market volume": volume, "Growth_PY": np.nan, "Market labs detected": len(labs),
                     "Top market products": products})
    return pd.DataFrame(rows)


def _allowed_manufacturers(value_usd, small, large):
    return 3 if value_usd >= large else (2 if value_usd >= small else 1)


def _market_bucket(value_usd, small, large):
    if value_usd >= large:
        return f"≥ ${large/1e6:.0f}M"
    if value_usd >= small:
        return f"${small/1e6:.0f}M–${large/1e6:.0f}M"
    return f"< ${small/1e6:.0f}M"


def _label(mfg, allowed, importers):
    if mfg == 0 and importers > 0:
        return "🎯 Substitution import : aucun fabricant local, demande prouvée"
    if mfg == 0:
        return "⚪ White space : aucun fabricant local"
    if mfg < allowed:
        return "🟢 Attractif : concurrence locale sous le seuil"
    if mfg == allowed:
        return "🟡 À étudier : concurrence au seuil"
    return "🔴 Saturé : trop de fabricants pour la taille"


def build_recommendations(nom, iqvia, pch, market_sources, active_only=True,
                          small_market_usd=DEFAULT_RULES["small_market_usd"],
                          large_market_usd=DEFAULT_RULES["large_market_usd"],
                          max_manufacturers_absolute=3, min_value_usd=0.0) -> Tuple[pd.DataFrame, pd.DataFrame]:
    comp = build_competition_table(nom, active_only)
    parts = []
    if me.SRC_IQVIA in market_sources:
        parts.append(build_iqvia_market_by_dci(nom, iqvia, active_only))
    if me.SRC_PCH in market_sources:
        parts.append(build_pch_market_by_dci(nom, pch, active_only))
    market = pd.concat([p for p in parts if p is not None and not p.empty], ignore_index=True, sort=False) if parts else pd.DataFrame()
    if market.empty or comp.empty:
        return pd.DataFrame(), market

    agg = market.groupby(["DCI_NORM_KEY", "DCI"], dropna=False).agg(**{
        "Market value DZD": ("Market value DZD", "sum"),
        "Market value USD": ("Market value USD", "sum"),
        "Market volume": ("Market volume", "sum"),
        "Sources found": ("Source", lambda s: ", ".join(sorted(set(s.dropna().astype(str))))),
        "Market labs detected": ("Market labs detected", "max"),
        "Top market products": ("Top market products", lambda s: "; ".join([x for x in s.dropna().astype(str).head(3) if x])[:1000]),
    }).reset_index()
    # value-weighted growth across sources for each DCI
    gr = market.groupby(["DCI_NORM_KEY", "DCI"]).apply(
        lambda d: weighted_growth_py(d["Market value DZD"], d["Growth_PY"])
    ).rename("Growth_PY").reset_index()
    agg = agg.merge(gr, on=["DCI_NORM_KEY", "DCI"], how="left")

    out = agg.merge(comp, on=["DCI_NORM_KEY", "DCI"], how="left")
    out["Manufacturers"] = pd.to_numeric(out["Manufacturers"], errors="coerce").fillna(0).astype(int)
    out["Importers"] = pd.to_numeric(out["Importers"], errors="coerce").fillna(0).astype(int)
    out["Allowed manufacturers"] = out["Market value USD"].map(lambda v: _allowed_manufacturers(v, small_market_usd, large_market_usd))
    out["Market bucket"] = out["Market value USD"].map(lambda v: _market_bucket(v, small_market_usd, large_market_usd))
    out["Recommendation"] = out.apply(lambda r: _label(int(r["Manufacturers"]), int(r["Allowed manufacturers"]), int(r["Importers"])), axis=1)
    out["Import substitution"] = (out["Manufacturers"] == 0) & (out["Importers"] > 0)
    out["Eligible"] = (out["Manufacturers"] <= out["Allowed manufacturers"]) & (out["Manufacturers"] <= max_manufacturers_absolute) & (out["Market value USD"] >= min_value_usd)

    # Opportunity score 0-100: market value (50) + low local competition (25) + import demand (10) + growth (15)
    value_score = np.log1p(out["Market value USD"].clip(lower=0)) / np.log1p(max(out["Market value USD"].max(), 1)) * 50
    competition_score = (max_manufacturers_absolute - out["Manufacturers"].clip(upper=max_manufacturers_absolute)) / max(max_manufacturers_absolute, 1) * 25
    importer_score = out["Importers"].clip(upper=6) / 6 * 10
    growth_score = out["Growth_PY"].fillna(0).clip(-0.5, 0.5).add(0.5) * 15
    out["Opportunity score"] = (value_score + competition_score + importer_score + growth_score).round(1)

    cols = ["Eligible", "Import substitution", "Opportunity score", "Recommendation", "DCI", "Sources found",
            "Market bucket", "Market value USD", "Market value DZD", "Market volume", "Growth_PY",
            "Manufacturers", "Allowed manufacturers", "Importers", "Market labs detected",
            "Manufacturer labs", "Importer labs", "Top market products", "Nomenclature lines"]
    out = out[[c for c in cols if c in out.columns]].sort_values(
        ["Eligible", "Opportunity score", "Market value USD"], ascending=[False, False, False])
    return out, market


def render_strategic_recommendations_page(data: dict) -> None:
    nom, iqvia, pch = data["nom"], data["iqvia"], data["pch"]

    hero(
        "Opportunités<br/>stratégiques produit",
        "Screening automatique des DCI à fort potentiel : taille de marché (IQVIA ville + PCH hospitalier), "
        "croissance et intensité concurrentielle locale. Les marchés couverts uniquement par l'import sont "
        "priorisés comme opportunités de production locale.",
        badge="🧠 Strategic Opportunity Engine",
    )

    with st.sidebar:
        st.markdown("### 🧠 Paramètres")
        market_sources = st.multiselect("Sources marché", [me.SRC_IQVIA, me.SRC_PCH],
                                        default=[me.SRC_IQVIA, me.SRC_PCH]) or [me.SRC_IQVIA, me.SRC_PCH]
        active_only = st.toggle("Nomenclature active uniquement", value=True)
        small_market_usd = st.number_input("Seuil petit/moyen marché (USD)", min_value=0.0, value=3_000_000.0, step=500_000.0, format="%.0f")
        large_market_usd = st.number_input("Seuil moyen/grand marché (USD)", min_value=0.0, value=7_000_000.0, step=500_000.0, format="%.0f")
        min_value_usd = st.number_input("Valeur minimum affichée (USD)", min_value=0.0, value=0.0, step=250_000.0, format="%.0f")
        view = st.radio("Affichage", ["Toutes les opportunités éligibles", "Substitution import uniquement", "Tout"], index=0)
        top_n = st.slider("Nombre maximum de lignes", 20, 500, 120, 20)
        run_scan = st.button("🚀 Scanner les opportunités", type="primary", width='stretch')

    st.markdown(
        f"""
        <div class="card">
        <b>Règle de concurrence locale appliquée</b><br/>
        • Marché &lt; <b>${small_market_usd/1e6:.1f}M</b> → max <b>1 fabricant</b> local &nbsp;·&nbsp;
        • <b>${small_market_usd/1e6:.1f}M–${large_market_usd/1e6:.1f}M</b> → max <b>2</b> &nbsp;·&nbsp;
        • ≥ <b>${large_market_usd/1e6:.1f}M</b> → max <b>3</b><br/>
        Les importateurs ne bloquent pas l'opportunité : ils prouvent la demande. <b>0 fabricant + importateurs = substitution import 🎯</b>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if run_scan or "strategic_recommendations" not in st.session_state:
        with st.spinner("Screening : Nomenclature → IQVIA/PCH → règles fabricants / croissance…"):
            recs, market_build = build_recommendations(
                nom=nom, iqvia=iqvia, pch=pch, market_sources=market_sources, active_only=active_only,
                small_market_usd=small_market_usd, large_market_usd=large_market_usd, min_value_usd=min_value_usd)
            st.session_state["strategic_recommendations"] = recs
            st.session_state["strategic_market_build"] = market_build

    recs = st.session_state.get("strategic_recommendations", pd.DataFrame()).copy()
    market_build = st.session_state.get("strategic_market_build", pd.DataFrame()).copy()
    if recs.empty:
        st.warning("Aucune recommandation générée. Essaie de scanner les deux sources ou baisse le seuil minimum.")
        return

    if view == "Substitution import uniquement" and "Import substitution" in recs.columns:
        shown = recs[recs["Import substitution"].eq(True)].copy()
    elif view == "Toutes les opportunités éligibles" and "Eligible" in recs.columns:
        shown = recs[recs["Eligible"].eq(True)].copy()
    else:
        shown = recs.copy()
    shown = shown.head(top_n)

    kpi_row([
        ("Opportunités", fmt_int(len(shown)), "lignes affichées"),
        ("Valeur cumulée", fmt_money(shown.get("Market value USD", pd.Series(dtype=float)).sum(), "$"), "marché adressable"),
        ("Substitution import", fmt_int(int(shown.get("Import substitution", pd.Series(dtype=bool)).sum())), "0 fabricant local", "good"),
        ("Score médian", f"{shown.get('Opportunity score', pd.Series(dtype=float)).median():.0f}", "sur 100"),
    ])

    st.download_button(
        "⬇️ Télécharger les recommandations (Excel)",
        data=me.export_excel_bytes(("Opportunites", shown), ("Construction marche", market_build)),
        file_name="opportunites_strategiques.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width='stretch',
    )

    t_tab, t_charts = st.tabs(["📌 Opportunités", "📊 Graphiques"])
    with t_tab:
        st.caption("Priorisé par éligibilité, score d'opportunité, valeur de marché. 🎯 = substitution aux importations.")
        disp = shown.rename(columns={
            "Market value USD": "Valeur USD", "Market value DZD": "Valeur DZD", "Market volume": "Volume",
            "Growth_PY": "Croissance", "Manufacturers": "Fabricants", "Importers": "Importateurs",
            "Allowed manufacturers": "Fabricants max", "Opportunity score": "Score", "Market bucket": "Taille",
            "Recommendation": "Recommandation", "Sources found": "Sources",
            "Manufacturer labs": "Fabricants (labos)", "Importer labs": "Importateurs (labos)",
            "Top market products": "Produits", "Import substitution": "Substit. import", "Eligible": "Éligible",
        })
        st.dataframe(format_dataframe_for_display(disp), width='stretch', height=620)
    with t_charts:
        if shown.empty:
            st.info("Aucune donnée à grapher.")
        else:
            fig = px.scatter(shown, x="Manufacturers", y="Market value USD", size="Market value USD",
                             color="Market bucket", hover_name="DCI",
                             hover_data=["Recommendation", "Importers", "Growth_PY", "Opportunity score"],
                             title="Valeur marché vs nombre de fabricants locaux")
            fig.update_layout(yaxis_title="Valeur marché USD", xaxis_title="Fabricants locaux")
            st.plotly_chart(plotly_layout(fig, height=460), width='stretch')
            top = shown.sort_values("Market value USD", ascending=False).head(25)
            fig2 = px.bar(top, x="Market value USD", y="DCI", color="Opportunity score",
                          color_continuous_scale="Tealgrn", orientation="h", title="Top opportunités par valeur")
            fig2.update_layout(yaxis={"categoryorder": "total ascending"}, yaxis_title="", xaxis_title="Valeur USD")
            st.plotly_chart(plotly_layout(fig2, height=620), width='stretch')
