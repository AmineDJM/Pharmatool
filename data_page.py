"""Data management — update the source files from inside the app (no GitHub).
Upload a new IQVIA / PCH / Nomenclature Excel; it is saved, pinned as the active
source, and the fast cache is rebuilt automatically."""

from pathlib import Path

import streamlit as st

import market_engine as me
from ui_theme import hero, section_title, chip, chips_row


_SLOTS = [
    ("iqvia", "📈 IQVIA (marché de ville)", "Feuille principale 'ATC Prod Mol Lab' + agrégats."),
    ("nom", "📚 Nomenclature officielle", "Feuille 'Nomenclature Avril ...' + Non renouvelés / Retraits."),
    ("pch", "🏥 PCH (réceptions hospitalières)", "Fichier des réceptions / achats hospitaliers."),
]


def _save_upload(kind, uploaded) -> Path:
    dest = Path(me.CONFIG["DATA_DIR"]) / uploaded.name
    dest.write_bytes(uploaded.getbuffer())
    me.set_source_override(kind, dest)
    return dest


def render_data_page(data: dict) -> None:
    meta = data.get("meta", {})
    hero(
        "Données<br/>& mises à jour",
        "Mets à jour les fichiers sources directement ici, sans passer par GitHub. "
        "Après l'envoi, l'outil recalcule tout automatiquement.",
        badge="📤 Data Manager",
    )

    section_title("Sources actuellement chargées")
    chips_row([
        chip(f"📈 {meta.get('iqvia_file', '—')}", "accent"),
        chip(f"📚 {meta.get('nom_file', '—')}", "default"),
        chip(f"🏥 {meta.get('pch_file', '—')}", "default"),
        chip(f"Année IQVIA : {meta.get('iqvia_year', '—')}", "good"),
    ])

    st.info(
        "ℹ️ Sur l'hébergement gratuit, un fichier envoyé reste actif tant que l'app tourne. "
        "Pour qu'il soit **permanent** (gardé après un redémarrage), il faut aussi l'ajouter au dépôt GitHub. "
        "Je peux le faire pour toi si tu me l'envoies."
    )

    section_title("Envoyer un nouveau fichier")
    for kind, label, helptext in _SLOTS:
        up = st.file_uploader(label, type=["xlsx", "xls"], key=f"up_{kind}", help=helptext)
        if up is not None:
            try:
                dest = _save_upload(kind, up)
                me.load_prepared_data.clear() if hasattr(me.load_prepared_data, "clear") else None
                st.cache_data.clear()
                with st.spinner("Recalcul des données et du cache…"):
                    me.build_cache()
                st.success(f"✅ {label} mis à jour : **{dest.name}**. L'app utilise maintenant ce fichier.")
                st.button("🔄 Rafraîchir l'application", on_click=st.rerun, key=f"refresh_{kind}")
            except Exception as e:
                st.error(f"Échec de la mise à jour : {e}")

    st.markdown("---")
    if st.button("♻️ Forcer le recalcul du cache", help="Reconstruit le cache rapide à partir des fichiers actuels."):
        with st.spinner("Reconstruction du cache…"):
            st.cache_data.clear()
            me.build_cache()
        st.success("Cache reconstruit. Clique pour rafraîchir.")
        st.button("🔄 Rafraîchir", on_click=st.rerun)
