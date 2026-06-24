"""AI Assistant — ask the market in plain French.
A natural-language question is translated (by Claude Haiku, the most economical
model) into a structured filter, which is then executed locally over the
opportunity table. Cost per question is tiny: one short request, no data sent
to the model — only the question and the list of available filters."""

import json

import pandas as pd
import streamlit as st

import market_engine as me
from strategic_recommendations import build_recommendations
from ui_theme import (
    hero, kpi_row, section_title, fmt_money, fmt_int, fmt_growth,
    format_dataframe_for_display, chip, chips_row,
)

MODEL = "claude-haiku-4-5"  # cheapest Claude model

_SYSTEM = """Tu convertis une question en français sur le marché pharmaceutique algérien en un FILTRE JSON.
Réponds UNIQUEMENT par un objet JSON valide, sans texte autour, avec ces clés (toutes optionnelles) :
- "min_market_usd": nombre (marché minimum en USD)
- "max_market_usd": nombre
- "min_growth": nombre décimal (ex: 0.10 pour +10%)
- "max_growth": nombre décimal
- "max_manufacturers": entier (nombre max de fabricants locaux)
- "min_manufacturers": entier
- "min_importers": entier
- "import_substitution_only": booléen (marchés sans fabricant local mais avec importateurs)
- "eligible_only": booléen
- "sort_by": une valeur parmi "market", "growth", "score"
- "top_n": entier (défaut 25)
N'invente pas de clés. Convertis les pourcentages en décimal. Exemple de question :
"molécules en croissance de plus de 10% avec un marché supérieur à 5M USD et moins de 2 fabricants locaux"
-> {"min_growth":0.10,"min_market_usd":5000000,"max_manufacturers":2,"sort_by":"market","top_n":25}"""

_EXAMPLES = [
    "Molécules en croissance > 10% avec un marché > 5M USD et moins de 2 fabricants locaux",
    "Top 10 des plus gros marchés sans fabricant local",
    "Opportunités de substitution import les plus rentables",
    "Marchés > 3M USD qui déclinent (croissance négative)",
]


@st.cache_data(show_spinner=False)
def _recommendations(_nom, _iqvia, _pch, sig):
    recs, _ = build_recommendations(_nom, _iqvia, _pch, [me.SRC_IQVIA, me.SRC_PCH], active_only=True)
    return recs


def _get_client():
    try:
        import anthropic
    except Exception:
        return None, "module"
    key = None
    try:
        key = st.secrets["anthropic_api_key"]
    except Exception:
        key = None
    if not key:
        return None, "no_key"
    try:
        return anthropic.Anthropic(api_key=str(key)), None
    except Exception as e:
        return None, str(e)


def _ask_llm(client, question):
    msg = client.messages.create(
        model=MODEL, max_tokens=400, system=_SYSTEM,
        messages=[{"role": "user", "content": question}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    if "```" in text:
        text = text.split("```")[1].replace("json", "", 1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return {}
    return json.loads(text[start:end + 1])


def _apply_filters(recs, f):
    x = recs.copy()
    if x.empty:
        return x
    g = lambda k: f.get(k)
    if g("min_market_usd") is not None:
        x = x[x["Market value USD"] >= float(g("min_market_usd"))]
    if g("max_market_usd") is not None:
        x = x[x["Market value USD"] <= float(g("max_market_usd"))]
    if g("min_growth") is not None:
        x = x[pd.to_numeric(x["Growth_PY"], errors="coerce").fillna(-99) >= float(g("min_growth"))]
    if g("max_growth") is not None:
        x = x[pd.to_numeric(x["Growth_PY"], errors="coerce").fillna(99) <= float(g("max_growth"))]
    if g("max_manufacturers") is not None:
        x = x[x["Manufacturers"] <= int(g("max_manufacturers"))]
    if g("min_manufacturers") is not None:
        x = x[x["Manufacturers"] >= int(g("min_manufacturers"))]
    if g("min_importers") is not None:
        x = x[x["Importers"] >= int(g("min_importers"))]
    if g("import_substitution_only"):
        x = x[(x["Manufacturers"] == 0) & (x["Importers"] > 0)]
    if g("eligible_only") and "Eligible" in x.columns:
        x = x[x["Eligible"].eq(True)]
    sort_map = {"market": "Market value USD", "growth": "Growth_PY", "score": "Opportunity score"}
    sort_col = sort_map.get(str(g("sort_by") or "market"), "Market value USD")
    x = x.sort_values(sort_col, ascending=False)
    top_n = int(g("top_n") or 25)
    return x.head(max(1, min(top_n, 200)))


def _filters_to_chips(f):
    out = []
    if f.get("min_market_usd") is not None:
        out.append(chip(f"marché ≥ {fmt_money(f['min_market_usd'], '$')}", "accent"))
    if f.get("max_market_usd") is not None:
        out.append(chip(f"marché ≤ {fmt_money(f['max_market_usd'], '$')}", "accent"))
    if f.get("min_growth") is not None:
        out.append(chip(f"croissance ≥ {fmt_growth(f['min_growth'])}", "good"))
    if f.get("max_growth") is not None:
        out.append(chip(f"croissance ≤ {fmt_growth(f['max_growth'])}", "warn"))
    if f.get("max_manufacturers") is not None:
        out.append(chip(f"≤ {f['max_manufacturers']} fabricant(s)", "default"))
    if f.get("min_importers") is not None:
        out.append(chip(f"≥ {f['min_importers']} importateur(s)", "default"))
    if f.get("import_substitution_only"):
        out.append(chip("substitution import", "good"))
    return out


def render_assistant_page(data: dict) -> None:
    nom, iqvia, pch = data["nom"], data["iqvia"], data["pch"]
    meta = data.get("meta", {})

    hero(
        "Assistant<br/>intelligent",
        "Pose ta question en français — l'assistant comprend ce que tu cherches et filtre le marché pour toi. "
        "Ex : « molécules en croissance > 10%, marché > 5M USD, moins de 2 fabricants locaux ».",
        badge="🤖 AI Assistant · Claude Haiku",
    )

    client, err = _get_client()
    if err == "no_key" or err == "module":
        st.info(
            "🔑 **Assistant IA non configuré.** Pour l'activer (coût minime, modèle le moins cher) :\n\n"
            "1. Crée une clé sur **console.anthropic.com** → API Keys.\n"
            "2. Sur Streamlit Cloud → ton app → **Settings → Secrets**, colle :\n\n"
            "```toml\nanthropic_api_key = \"sk-ant-...\"\n```\n\n"
            "3. Reboot l'app. En local, ajoute la même ligne dans `.streamlit/secrets.toml`."
        )
        st.caption("Les autres pages fonctionnent sans clé — l'IA est un bonus.")
        return
    if err:
        st.error(f"Problème d'initialisation de l'assistant : {err}")
        return

    st.caption("Exemples (clique pour utiliser) :")
    cols = st.columns(2)
    for i, ex in enumerate(_EXAMPLES):
        if cols[i % 2].button(ex, key=f"ex_{i}", width='stretch'):
            st.session_state["assistant_q"] = ex

    question = st.text_input(
        "Ta question", value=st.session_state.get("assistant_q", ""),
        placeholder="ex: top 10 des marchés > 2M USD sans fabricant local",
    )
    go = st.button("🤖 Demander", type="primary")

    if not (go and question.strip()):
        return

    sig = f"{meta.get('iqvia_file')}|{meta.get('nom_file')}|{meta.get('pch_file')}"
    recs = _recommendations(nom, iqvia, pch, sig)

    try:
        with st.spinner("L'assistant analyse ta question…"):
            filt = _ask_llm(client, question.strip())
    except Exception as e:
        st.error(f"L'assistant n'a pas pu répondre : {e}")
        return

    chips = _filters_to_chips(filt)
    if chips:
        st.markdown("**Critères compris :**")
        chips_row(chips)
    else:
        st.warning("Je n'ai pas extrait de critère clair. Reformule (marché, croissance, fabricants…).")

    res = _apply_filters(recs, filt)
    if res.empty:
        st.info("Aucune molécule ne correspond à ces critères. Élargis la recherche.")
        return

    kpi_row([
        ("Résultats", fmt_int(len(res)), "molécules"),
        ("Marché cumulé", fmt_money(res["Market value USD"].sum(), "$"), "adressable"),
        ("Sans fabricant local", fmt_int(int((res["Manufacturers"] == 0).sum())), "white space"),
        ("Croissance médiane", fmt_growth(pd.to_numeric(res["Growth_PY"], errors="coerce").median()), "vs N-1"),
    ])

    section_title("Réponse")
    disp = res.rename(columns={
        "Market value USD": "Marché USD", "Growth_PY": "Croissance", "Manufacturers": "Fabricants",
        "Importers": "Importateurs", "Opportunity score": "Score", "Recommendation": "Recommandation",
        "Top market products": "Produits",
    })
    cols_show = [c for c in ["DCI", "Marché USD", "Croissance", "Fabricants", "Importateurs", "Score", "Recommandation", "Produits"] if c in disp.columns]
    st.dataframe(format_dataframe_for_display(disp[cols_show]), width='stretch', height=460)

    st.download_button(
        "⬇️ Exporter (Excel)", data=me.export_excel_bytes(("Reponse assistant", disp[cols_show])),
        file_name="assistant_resultats.xlsx", width='stretch',
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    with st.expander("🔧 Filtre interprété (JSON)"):
        st.json(filt)
