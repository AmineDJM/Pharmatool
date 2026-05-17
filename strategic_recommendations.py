"""
Strategic recommendations page for Algeria Pharma Market Intelligence.
This module is intentionally isolated from app.py and market_engine.py.
It can be modified independently without touching the DCI analysis workflow.
"""

from __future__ import annotations

from io import BytesIO
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from market_engine import CONFIG, norm_text, safe_unique, tokens
from ui_theme import format_dataframe_for_display


DEFAULT_RULES = {
    "small_market_usd": 3_000_000.0,
    "large_market_usd": 7_000_000.0,
}


def _fmt_money(x: float) -> str:
    try:
        x = float(x)
    except Exception:
        return "—"
    if np.isnan(x):
        return "—"
    def sp(v, d=0):
        return f"{v:,.{d}f}".replace(",", " ")
    if abs(x) >= 1_000_000_000:
        return f"{sp(x/1_000_000_000, 2)} B"
    if abs(x) >= 1_000_000:
        return f"{sp(x/1_000_000, 1)} M"
    if abs(x) >= 1_000:
        return sp(x, 0)
    return sp(x, 0)


def _status_bucket(status: object) -> str:
    """Return F/I/OTHER using cautious nomenclature status parsing."""
    s = norm_text(status)
    if not s:
        return "OTHER"
    parts = set(s.replace("/", " ").replace("-", " ").split())
    if s == "F" or "F" in parts or "FAB" in s or "FABRI" in s or "PROD" in s:
        return "F"
    if s == "I" or "I" in parts or "IMP" in s or "IMPORT" in s:
        return "I"
    return "OTHER"


def _active_scope(nom: pd.DataFrame, active_only: bool) -> pd.DataFrame:
    if nom is None or nom.empty:
        return pd.DataFrame()
    x = nom.copy()
    if active_only and "SOURCE_NOMENCLATURE" in x.columns:
        x = x[x["SOURCE_NOMENCLATURE"].astype(str).str.upper().eq("ACTIVE")].copy()
    return x


@st.cache_data(show_spinner=False)
def build_competition_table(nom: pd.DataFrame, active_only: bool = True) -> pd.DataFrame:
    """Competition from nomenclature only: count manufacturers vs importers by controlled DCI."""
    x = _active_scope(nom, active_only)
    if x.empty or "DCI" not in x.columns:
        return pd.DataFrame(columns=["DCI", "DCI_NORM_KEY", "Manufacturers", "Importers", "Other players", "Manufacturer labs", "Importer labs"])

    for c in ["DCI", "LABORATOIRE", "STATUT"]:
        if c not in x.columns:
            x[c] = ""
    x = x[x["DCI"].notna() & x["DCI"].astype(str).str.strip().ne("")].copy()
    x["DCI_NORM_KEY"] = x["DCI"].map(norm_text)
    x["LAB_CLEAN"] = x["LABORATOIRE"].fillna("").astype(str).str.strip()
    x["STATUS_BUCKET"] = x["STATUT"].map(_status_bucket)
    x = x[x["DCI_NORM_KEY"].ne("")]

    rows = []
    for key, g in x.groupby("DCI_NORM_KEY", dropna=False):
        dci_label = safe_unique(g["DCI"], 20)[0] if len(g) else key
        f_labs = sorted(set(g.loc[g["STATUS_BUCKET"].eq("F"), "LAB_CLEAN"].replace("", pd.NA).dropna().astype(str)))
        i_labs = sorted(set(g.loc[g["STATUS_BUCKET"].eq("I"), "LAB_CLEAN"].replace("", pd.NA).dropna().astype(str)))
        other_labs = sorted(set(g.loc[g["STATUS_BUCKET"].eq("OTHER"), "LAB_CLEAN"].replace("", pd.NA).dropna().astype(str)))
        rows.append({
            "DCI": dci_label,
            "DCI_NORM_KEY": key,
            "Manufacturers": len(f_labs),
            "Importers": len(i_labs),
            "Other players": len(other_labs),
            "Manufacturer labs": "; ".join(f_labs[:12]),
            "Importer labs": "; ".join(i_labs[:12]),
            "Nomenclature lines": len(g),
        })
    return pd.DataFrame(rows)


def _build_pch_inverted_index(pch: pd.DataFrame) -> Dict[str, Set[int]]:
    idx: Dict[str, Set[int]] = {}
    if pch is None or pch.empty or "TEXT_NORM" not in pch.columns:
        return idx
    for i, text in pch["TEXT_NORM"].fillna("").astype(str).items():
        for tok in set(t for t in tokens(text) if len(t) >= 3):
            idx.setdefault(tok, set()).add(i)
    return idx


def _dci_query_tokens(dci_norm_key: str) -> List[str]:
    return [t for t in tokens(dci_norm_key) if len(t) >= 3]


@st.cache_data(show_spinner=False)
def build_iqvia_market_by_dci(nom: pd.DataFrame, iqvia: pd.DataFrame, active_only: bool = True) -> pd.DataFrame:
    """Fast IQVIA aggregation by controlled nomenclature DCI.
    Uses exact normalized molecule first, then token containment for combinations.
    """
    comp = build_competition_table(nom, active_only)
    if comp.empty or iqvia is None or iqvia.empty:
        return pd.DataFrame()
    x = iqvia.copy()
    for c in ["MOLECULE_NORM", "MARKET_VALUE_DZD", "MARKET_VALUE_USD", "MARKET_VOLUME", "LABORATOIRE", "PRODUCT_FULL"]:
        if c not in x.columns:
            x[c] = 0 if c.startswith("MARKET") else ""
    rows = []
    # Group once by normalized molecule for speed.
    grouped_exact = {k: g for k, g in x.groupby("MOLECULE_NORM", dropna=False)}
    molecule_norms = pd.Series(list(grouped_exact.keys()), dtype="object")

    for _, d in comp.iterrows():
        key = d["DCI_NORM_KEY"]
        if not key:
            continue
        matched_parts = []
        if key in grouped_exact:
            matched_parts.append(grouped_exact[key])
        else:
            qtokens = _dci_query_tokens(key)
            if qtokens:
                mask = pd.Series(True, index=molecule_norms.index)
                for tok in qtokens:
                    mask &= molecule_norms.astype(str).str.contains(rf"(?<![A-Z0-9]){tok}(?![A-Z0-9])", regex=True, na=False)
                candidate_keys = molecule_norms[mask].tolist()
                # Avoid exploding: only accept token containment, not fuzzy suffix similarity.
                for ck in candidate_keys:
                    if ck in grouped_exact:
                        matched_parts.append(grouped_exact[ck])
        if not matched_parts:
            continue
        m = pd.concat(matched_parts, ignore_index=False).drop_duplicates()
        value_dzd = float(pd.to_numeric(m["MARKET_VALUE_DZD"], errors="coerce").fillna(0).sum())
        volume = float(pd.to_numeric(m["MARKET_VOLUME"], errors="coerce").fillna(0).sum())
        labs = sorted(set(m["LABORATOIRE"].fillna("").astype(str).str.strip().replace("", pd.NA).dropna()))
        products = "; ".join(m.sort_values("MARKET_VALUE_DZD", ascending=False)["PRODUCT_FULL"].fillna("").astype(str).head(5).tolist())
        rows.append({
            "DCI_NORM_KEY": key,
            "DCI": d["DCI"],
            "Source": "IQVIA VILLE",
            "Market value DZD": value_dzd,
            "Market value USD": value_dzd / CONFIG["DZD_PER_USD"],
            "Market volume": volume,
            "Market labs detected": len(labs),
            "Top market products": products,
        })
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def build_pch_market_by_dci(nom: pd.DataFrame, pch: pd.DataFrame, active_only: bool = True) -> pd.DataFrame:
    """PCH aggregation by controlled nomenclature DCI using an inverted token index.
    This avoids scanning the full PCH table for every DCI.
    """
    comp = build_competition_table(nom, active_only)
    if comp.empty or pch is None or pch.empty:
        return pd.DataFrame()
    x = pch.copy()
    for c in ["TEXT_NORM", "MARKET_VALUE_DZD", "MARKET_VALUE_USD", "MARKET_VOLUME", "LABORATOIRE", "PRODUCT_FULL"]:
        if c not in x.columns:
            x[c] = 0 if c.startswith("MARKET") else ""
    inv = _build_pch_inverted_index(x)
    rows = []
    for _, d in comp.iterrows():
        key = d["DCI_NORM_KEY"]
        qtokens = _dci_query_tokens(key)
        if not qtokens:
            continue
        sets = [inv.get(tok, set()) for tok in qtokens]
        if not sets or any(len(s) == 0 for s in sets):
            continue
        matched_idx = set.intersection(*sets)
        if not matched_idx:
            continue
        m = x.loc[sorted(matched_idx)].copy()
        # Final exact token guard.
        for tok in qtokens:
            m = m[m["TEXT_NORM"].fillna("").astype(str).str.contains(rf"(?<![A-Z0-9]){tok}(?![A-Z0-9])", regex=True, na=False)]
        if m.empty:
            continue
        value_dzd = float(pd.to_numeric(m["MARKET_VALUE_DZD"], errors="coerce").fillna(0).sum())
        volume = float(pd.to_numeric(m["MARKET_VOLUME"], errors="coerce").fillna(0).sum())
        labs = sorted(set(m["LABORATOIRE"].fillna("").astype(str).str.strip().replace("", pd.NA).dropna()))
        products = "; ".join(m.sort_values("MARKET_VALUE_DZD", ascending=False)["PRODUCT_FULL"].fillna("").astype(str).head(5).tolist())
        rows.append({
            "DCI_NORM_KEY": key,
            "DCI": d["DCI"],
            "Source": "PCH HOSPITALIER",
            "Market value DZD": value_dzd,
            "Market value USD": value_dzd / CONFIG["DZD_PER_USD"],
            "Market volume": volume,
            "Market labs detected": len(labs),
            "Top market products": products,
        })
    return pd.DataFrame(rows)


def _allowed_manufacturers(value_usd: float, small_market_usd: float, large_market_usd: float) -> int:
    if value_usd >= large_market_usd:
        return 3
    if value_usd >= small_market_usd:
        return 2
    return 1


def _market_bucket(value_usd: float, small_market_usd: float, large_market_usd: float) -> str:
    if value_usd >= large_market_usd:
        return f">= ${large_market_usd/1_000_000:.0f}M"
    if value_usd >= small_market_usd:
        return f"${small_market_usd/1_000_000:.0f}M–${large_market_usd/1_000_000:.0f}M"
    return f"< ${small_market_usd/1_000_000:.0f}M"


def _strategic_label(mfg: int, allowed: int, value_usd: float) -> str:
    if mfg == 0:
        return "White space: aucun fabricant local détecté"
    if mfg < allowed:
        return "Attractif: concurrence locale inférieure au seuil"
    if mfg == allowed:
        return "À étudier: concurrence au seuil maximum"
    return "Rejeté: trop de fabricants pour la taille du marché"


def build_recommendations(
    nom: pd.DataFrame,
    iqvia: pd.DataFrame,
    pch: pd.DataFrame,
    market_sources: Sequence[str],
    active_only: bool = True,
    small_market_usd: float = DEFAULT_RULES["small_market_usd"],
    large_market_usd: float = DEFAULT_RULES["large_market_usd"],
    max_manufacturers_absolute: int = 3,
    min_value_usd: float = 0.0,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    comp = build_competition_table(nom, active_only)
    parts = []
    if "IQVIA VILLE" in market_sources:
        parts.append(build_iqvia_market_by_dci(nom, iqvia, active_only))
    if "PCH HOSPITALIER" in market_sources:
        parts.append(build_pch_market_by_dci(nom, pch, active_only))
    market = pd.concat([p for p in parts if p is not None and not p.empty], ignore_index=True, sort=False) if parts else pd.DataFrame()
    if market.empty or comp.empty:
        return pd.DataFrame(), market

    agg = market.groupby(["DCI_NORM_KEY", "DCI"], dropna=False).agg(
        **{
            "Market value DZD": ("Market value DZD", "sum"),
            "Market value USD": ("Market value USD", "sum"),
            "Market volume": ("Market volume", "sum"),
            "Sources found": ("Source", lambda s: ", ".join(sorted(set(s.dropna().astype(str))))),
            "Market labs detected": ("Market labs detected", "max"),
            "Top market products": ("Top market products", lambda s: "; ".join([x for x in s.dropna().astype(str).head(3) if x])[:1000]),
        }
    ).reset_index()

    out = agg.merge(comp, on=["DCI_NORM_KEY", "DCI"], how="left")
    out["Manufacturers"] = pd.to_numeric(out["Manufacturers"], errors="coerce").fillna(0).astype(int)
    out["Importers"] = pd.to_numeric(out["Importers"], errors="coerce").fillna(0).astype(int)
    out["Allowed manufacturers"] = out["Market value USD"].map(lambda v: _allowed_manufacturers(v, small_market_usd, large_market_usd))
    out["Market bucket"] = out["Market value USD"].map(lambda v: _market_bucket(v, small_market_usd, large_market_usd))
    out["Recommendation"] = out.apply(lambda r: _strategic_label(int(r["Manufacturers"]), int(r["Allowed manufacturers"]), float(r["Market value USD"])), axis=1)
    out["Eligible"] = (out["Manufacturers"] <= out["Allowed manufacturers"]) & (out["Manufacturers"] <= max_manufacturers_absolute) & (out["Market value USD"] >= min_value_usd)

    # Opportunity score: bigger market, fewer manufacturers, importer presence useful as proof of demand.
    value_score = np.log1p(out["Market value USD"].clip(lower=0)) / np.log1p(max(out["Market value USD"].max(), 1)) * 55
    competition_score = (max_manufacturers_absolute - out["Manufacturers"].clip(upper=max_manufacturers_absolute)) / max(max_manufacturers_absolute, 1) * 30
    importer_score = out["Importers"].clip(upper=6) / 6 * 15
    out["Opportunity score"] = (value_score + competition_score + importer_score).round(1)

    display_cols = [
        "Eligible", "Opportunity score", "Recommendation", "DCI", "Sources found",
        "Market bucket", "Market value USD", "Market value DZD", "Market volume",
        "Manufacturers", "Allowed manufacturers", "Importers", "Market labs detected",
        "Manufacturer labs", "Importer labs", "Top market products", "Nomenclature lines",
    ]
    out = out[[c for c in display_cols if c in out.columns]].sort_values(["Eligible", "Opportunity score", "Market value USD"], ascending=[False, False, False])
    return out, market


def export_recommendations_excel(recommendations: pd.DataFrame, market_detail: pd.DataFrame) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="xlsxwriter") as writer:
        recommendations.to_excel(writer, sheet_name="Strategic Recommendations", index=False)
        market_detail.to_excel(writer, sheet_name="Market Build", index=False)
        wb = writer.book
        header = wb.add_format({"bold": True, "font_color": "white", "bg_color": "#0F766E", "border": 1, "align": "center"})
        money_fmt = wb.add_format({"num_format": "#,##0"})
        for sheet, df in [("Strategic Recommendations", recommendations), ("Market Build", market_detail)]:
            ws = writer.sheets[sheet]
            ws.freeze_panes(1, 0)
            if not df.empty:
                ws.autofilter(0, 0, max(len(df), 1), max(len(df.columns) - 1, 0))
            for i, col in enumerate(df.columns):
                width = min(max(12, int(max([len(str(col))] + [len(str(v)) for v in df[col].head(200).fillna("").astype(str)]) * 1.05)), 55)
                ws.set_column(i, i, width)
                ws.write(0, i, col, header)
                if "value" in str(col).lower() or "volume" in str(col).lower():
                    ws.set_column(i, i, width, money_fmt)
    return bio.getvalue()


def render_strategic_recommendations_page(nom: pd.DataFrame, iqvia: pd.DataFrame, pch: pd.DataFrame) -> None:
    st.markdown(
        """
        <div class="hero">
          <div class="badge">🧠 Strategic Recommendation Engine · Build v4.4 separate-module</div>
          <h1>Strategic Product<br/>Recommendation Engine</h1>
          <p>Screening automatique des DCI à potentiel selon la taille du marché IQVIA / PCH et l’intensité concurrentielle locale dans la Nomenclature. Règle centrale : plus le marché est petit, moins il doit y avoir de fabricants locaux.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown("### 🧠 Paramètres recommandations")
        market_sources = st.multiselect(
            "Sources marché à scanner",
            ["IQVIA VILLE", "PCH HOSPITALIER"],
            default=["IQVIA VILLE", "PCH HOSPITALIER"],
            help="L'outil peut scanner le marché ville, hospitalier, ou les deux.",
        ) or ["IQVIA VILLE", "PCH HOSPITALIER"]
        active_only = st.toggle("Nomenclature active uniquement", value=True)
        small_market_usd = st.number_input("Seuil petit/moyen marché USD", min_value=0.0, value=3_000_000.0, step=500_000.0, format="%.0f")
        large_market_usd = st.number_input("Seuil moyen/grand marché USD", min_value=0.0, value=7_000_000.0, step=500_000.0, format="%.0f")
        min_value_usd = st.number_input("Valeur minimum affichée USD", min_value=0.0, value=0.0, step=250_000.0, format="%.0f")
        only_eligible = st.toggle("Afficher uniquement les opportunités éligibles", value=True)
        top_n = st.slider("Nombre maximum de lignes", min_value=20, max_value=500, value=120, step=20)
        run_scan = st.button("🚀 Scanner les opportunités", type="primary", use_container_width=True)

    st.markdown(
        f"""
        <div class="card">
        <b>Règle appliquée</b><br/>
        • Marché &lt; <b>${small_market_usd/1_000_000:.1f}M</b> → maximum <b>1 fabricant</b><br/>
        • Marché entre <b>${small_market_usd/1_000_000:.1f}M</b> et <b>${large_market_usd/1_000_000:.1f}M</b> → maximum <b>2 fabricants</b><br/>
        • Marché ≥ <b>${large_market_usd/1_000_000:.1f}M</b> → maximum <b>3 fabricants</b><br/>
        Les importateurs ne bloquent pas l’opportunité : ils servent plutôt de preuve de demande marché.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not run_scan and "strategic_recommendations" not in st.session_state:
        st.info("Clique sur Scanner les opportunités pour lancer l’analyse automatique.")
        return

    if run_scan or "strategic_recommendations" not in st.session_state:
        with st.spinner("Screening stratégique en cours : Nomenclature → IQVIA/PCH → règles fabricants/marché…"):
            recs, market_build = build_recommendations(
                nom=nom,
                iqvia=iqvia,
                pch=pch,
                market_sources=market_sources,
                active_only=active_only,
                small_market_usd=small_market_usd,
                large_market_usd=large_market_usd,
                min_value_usd=min_value_usd,
            )
            st.session_state["strategic_recommendations"] = recs
            st.session_state["strategic_market_build"] = market_build

    recs = st.session_state.get("strategic_recommendations", pd.DataFrame()).copy()
    market_build = st.session_state.get("strategic_market_build", pd.DataFrame()).copy()

    if recs.empty:
        st.warning("Aucune recommandation n’a été générée. Essaie de scanner les deux sources ou de baisser le seuil minimum.")
        return

    if only_eligible and "Eligible" in recs.columns:
        shown = recs[recs["Eligible"].eq(True)].copy()
    else:
        shown = recs.copy()
    shown = shown.head(top_n)

    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f'<div class="metric-card"><div class="metric-label">Opportunités</div><div class="metric-value">{len(shown):,}</div><div class="metric-sub">lignes affichées</div></div>', unsafe_allow_html=True)
    k2.markdown(f'<div class="metric-card"><div class="metric-label">Valeur USD</div><div class="metric-value">${_fmt_money(shown.get("Market value USD", pd.Series(dtype=float)).sum())}</div><div class="metric-sub">marché cumulé</div></div>', unsafe_allow_html=True)
    k3.markdown(f'<div class="metric-card"><div class="metric-label">Sans fabricant</div><div class="metric-value">{int((shown.get("Manufacturers", pd.Series(dtype=int)) == 0).sum())}</div><div class="metric-sub">white spaces</div></div>', unsafe_allow_html=True)
    k4.markdown(f'<div class="metric-card"><div class="metric-label">Score médian</div><div class="metric-value">{shown.get("Opportunity score", pd.Series(dtype=float)).median():.1f}</div><div class="metric-sub">sur 100</div></div>', unsafe_allow_html=True)

    excel = export_recommendations_excel(shown, market_build)
    st.download_button(
        "⬇️ Télécharger les recommandations Excel",
        data=excel,
        file_name="strategic_product_recommendations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    tab_table, tab_charts, tab_market_build = st.tabs(["📌 Recommandations", "📊 Graphiques", "🧾 Construction marché"])
    with tab_table:
        st.caption("Liste priorisée selon valeur marché, fabricants locaux détectés dans la Nomenclature, importateurs et score d’opportunité.")
        st.dataframe(format_dataframe_for_display(shown), use_container_width=True, height=620)
    with tab_charts:
        if shown.empty:
            st.info("Aucune donnée à grapher.")
        else:
            fig = px.scatter(
                shown,
                x="Manufacturers",
                y="Market value USD",
                size="Market value USD",
                color="Market bucket",
                hover_name="DCI",
                hover_data=["Recommendation", "Importers", "Sources found", "Opportunity score"],
                title="Valeur marché vs nombre de fabricants locaux",
            )
            fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", yaxis_title="Market value USD", xaxis_title="Fabricants locaux")
            st.plotly_chart(fig, use_container_width=True)

            top = shown.sort_values("Market value USD", ascending=False).head(25)
            fig2 = px.bar(top, x="Market value USD", y="DCI", color="Manufacturers", orientation="h", title="Top opportunités par valeur marché")
            fig2.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig2, use_container_width=True)
    with tab_market_build:
        st.caption("Table technique de construction : agrégation par DCI et source marché. Utile pour audit / contrôle.")
        st.dataframe(format_dataframe_for_display(market_build), use_container_width=True, height=560)
