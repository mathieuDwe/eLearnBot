"""👨‍🏫 Page Professeur — Upload et gestion des cours (PDF + Vidéos MP4)."""

import streamlit as st
import tempfile
import os
from datetime import datetime

from core.auth import require_role, get_current_user
from core.pdf_extractor import extract_text_from_pdf
from core.video_processor import process_video
from core.rag_pipeline import index_document, get_available_documents
from core import response_cache
from core.document_store import delete_document as delete_doc_store
from integrations.supabase_storage import SupabaseStorage

from core.reindexer import (
    check_sync_status,
    reindex_all,
    format_sync_summary,
)


def _format_size(size_bytes: int) -> str:
    """Formate une taille en bytes vers une lisible (Ko, Mo)."""
    if size_bytes < 1024:
        return f"{size_bytes} o"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} Ko"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} Mo"


def show():
    """Affiche l'interface professeur."""
    # Vérification du rôle
    if not require_role("professeur"):
        st.error("⛔ Accès réservé aux professeurs.")
        st.info("Connectez-vous avec un compte professeur.")
        return

    user = get_current_user()
    st.title("👨‍🏫 Mode Professeur")
    st.markdown(
        f"Bienvenue **{user['name']}** ! "
        "Uploader vos cours (PDF ou MP4). Les élèves pourront ensuite "
        "poser des questions dessus."
    )

    # ── Onglets ────────────────────────────────────────────────────────
    tab1, tab2, tab3 = st.tabs([
        "📤 Uploader un cours",
        "📚 Mes cours",
        "⚙️ Paramètres",
    ])

    # ── Onglet 1 : Upload ──────────────────────────────────────────────
    with tab1:
        st.subheader("Uploader un nouveau cours")

        upload_type = st.radio(
            "Type de fichier",
            ["📄 PDF (document texte)", "🎬 MP4 (vidéo)"],
            horizontal=True,
            index=0,
        )

        # ── Upload PDF ─────────────────────────────────────────────────
        if "PDF" in upload_type:
            uploaded_file = st.file_uploader(
                "Choisissez un fichier PDF",
                type=["pdf"],
                help="Taille max : 10 Mo. Les PDF scannés ne sont pas supportés.",
                key="pdf_uploader",
            )

            if uploaded_file is not None:
                if uploaded_file.size > 10 * 1024 * 1024:
                    st.error("❌ Le fichier dépasse 10 Mo.")
                else:
                    with st.spinner("⏳ Traitement du PDF en cours..."):
                        with tempfile.NamedTemporaryFile(
                            delete=False, suffix=".pdf"
                        ) as tmp:
                            tmp.write(uploaded_file.getvalue())
                            tmp_path = tmp.name

                        try:
                            text = extract_text_from_pdf(tmp_path)

                            if not text.strip():
                                st.warning(
                                    "⚠️ Le PDF semble vide ou contient uniquement "
                                    "des images (OCR non supporté en v1)."
                                )
                            else:
                                _index_and_store(
                                    tmp_path, uploaded_file.name, text, "pdf"
                                )
                        except Exception as e:
                            st.error(f"❌ Erreur lors du traitement : {e}")
                        finally:
                            os.unlink(tmp_path)

        # ── Upload MP4 ─────────────────────────────────────────────────
        else:
            uploaded_file = st.file_uploader(
                "Choisissez une vidéo MP4",
                type=["mp4"],
                help="Taille max : 100 Mo. La piste audio sera transcrite en texte.",
                key="mp4_uploader",
            )

            if uploaded_file is not None:
                if uploaded_file.size > 100 * 1024 * 1024:
                    st.error("❌ Le fichier dépasse 100 Mo.")
                else:
                    # Progression
                    progress_bar = st.progress(0, text="Préparation...")

                    with st.spinner("⏳ Traitement de la vidéo en cours..."):
                        with tempfile.NamedTemporaryFile(
                            delete=False, suffix=".mp4"
                        ) as tmp:
                            tmp.write(uploaded_file.getvalue())
                            tmp_path = tmp.name

                        try:
                            progress_bar.progress(20, text="📦 Fichier sauvegardé")

                            # Transcrire avec Whisper
                            progress_bar.progress(
                                40, text="🎤 Transcription audio (Whisper)..."
                            )
                            result = process_video(tmp_path, language="fr")

                            text = result["text"]

                            if not text.strip():
                                st.warning(
                                    "⚠️ Aucun texte détecté dans la vidéo. "
                                    "Vérifiez qu'il y a bien une piste audio."
                                )
                            else:
                                duration = result.get("duration", 0)
                                mins, secs = divmod(int(duration), 60)

                                progress_bar.progress(
                                    80, text="💾 Indexation..."
                                )

                                _index_and_store(
                                    tmp_path,
                                    uploaded_file.name,
                                    text,
                                    "mp4",
                                    metadata={
                                        "duration": duration,
                                        "duration_display": f"{mins}:{secs:02d}",
                                        "language": result.get("language", "fr"),
                                    },
                                )
                                progress_bar.progress(
                                    100, text="✅ Terminé !"
                                )

                        except Exception as e:
                            st.error(f"❌ Erreur lors du traitement vidéo : {e}")
                        finally:
                            os.unlink(tmp_path)
                            progress_bar.empty()

    # ── Onglet 2 : Mes cours ───────────────────────────────────────────
    with tab2:
        st.subheader("Cours indexés")

        # ── Ré-indexation automatique depuis Supabase ────────────────────
        # Se déclenche tout seul : pas besoin de bouton, ça se fait
        # à chaque fois que la page est chargée (une seule fois par session
        # utilisateur, grâce au flag _auto_synced).
        if "_auto_reindex_prof" not in st.session_state:
            st.session_state._auto_reindex_prof = True
            status = check_sync_status()
            if status["new_files"] or status["modified_files"]:
                with st.spinner("🔄 Synchronisation automatique avec Supabase..."):
                    report = reindex_all()
                if report["total_processed"] > 0:
                    n_new = len(report.get("indexed", []))
                    n_upd = len(report.get("updated", []))
                    n_err = len(report.get("errors", []))
                    if n_new:
                        st.toast(f"📥 {n_new} nouveau(x) cours indexé(s) depuis Supabase")
                    if n_upd:
                        st.toast(f"🔄 {n_upd} cours mis à jour depuis Supabase")
                    if n_err:
                        st.toast(f"❌ {n_err} erreur(s) lors de la synchro")
                st.rerun()

        # ── Barre d'état de synchronisation ──────────────────────────────
        with st.container(border=True):
            status = check_sync_status()
            st.caption(format_sync_summary(status))

        documents = get_available_documents()

        if not documents:
            st.info(
                "📭 Aucun cours pour le moment. Uploader un PDF ou une "
                "vidéo MP4 dans l'onglet précédent."
            )
        else:
            for doc in documents:
                meta = doc.get("metadata", {})
                content_type = meta.get("content_type", "pdf")
                icon = "🎬" if content_type == "mp4" else "📄"
                content_hash = doc.get("content_hash") or meta.get("content_hash", "")

                with st.container(border=True):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"**{icon} {doc['filename']}**")
                        chunks_info = f"🔢 {doc['chunks']} passages indexés"
                        if content_type == "mp4":
                            duration = meta.get("duration_display", "")
                            chunks_info += (
                                f" | 🎬 Durée : {duration}"
                                if duration
                                else ""
                            )
                        if content_hash:
                            chunks_info += " · ✅ Versionné"
                        st.caption(chunks_info)
                    with col2:
                        if st.button(
                            "🗑️ Supprimer",
                            key=f"del_{doc['filename']}",
                        ):
                            deleted = delete_doc_store(doc["filename"])
                            # Supprimer aussi de Supabase Storage
                            try:
                                from integrations.supabase_storage import SupabaseStorage
                                storage = SupabaseStorage()
                                storage.delete_file(doc["filename"])
                                st.success(f"✅ {deleted} passages supprimés + fichier effacé du cloud.")
                            except Exception as e:
                                st.success(f"✅ {deleted} passages supprimés (cloud: {e}).")
                            st.rerun()

        # ── Fichiers dans le bucket Supabase ────────────────────────────
        with st.expander("☁️ Fichiers dans le bucket Supabase", expanded=False):
            try:
                from integrations.supabase_storage import SupabaseStorage
                storage = SupabaseStorage()
                bucket_files = storage.list_files()

                if not bucket_files:
                    st.caption("📭 Le bucket est vide.")
                else:
                    indexed_names = {d["filename"] for d in documents}
                    for f in bucket_files:
                        fname = f.get("name", "?")
                        already_indexed = fname in indexed_names
                        with st.container(border=True):
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.markdown(f"**{fname}**")
                                if already_indexed:
                                    st.caption("✅ Déjà indexé")
                                else:
                                    st.caption("⏳ Non indexé — cliquer pour restaurer")
                            with col2:
                                if already_indexed:
                                    st.button(
                                        "✅ Indexé",
                                        disabled=True,
                                        key=f"bucket_done_{fname}",
                                    )
                                else:
                                    if st.button(
                                        "📥 Restaurer",
                                        key=f"restore_{fname}",
                                    ):
                                        from core.pdf_extractor import extract_text_from_bytes
                                        from core.rag_pipeline import index_document

                                        file_bytes = storage.download_file(fname)
                                        if file_bytes:
                                            text = extract_text_from_bytes(file_bytes)
                                            if text.strip():
                                                index_document(
                                                    text=text,
                                                    filename=fname,
                                                    metadata={"content_type": "pdf", "restored": True},
                                                )
                                                st.success(f"✅ **{fname}** restauré et indexé !")
                                                st.rerun()
                                            else:
                                                st.warning(f"⚠️ {fname} : texte vide (PDF scanné ?)")
                                        else:
                                            st.error(f"❌ Impossible de télécharger {fname}")

            except Exception as e:
                st.caption(f"⚠️ Bucket non accessible : {e}")

    # ── Onglet 3 : Paramètres ──────────────────────────────────────────
    with tab3:
        st.subheader("Paramètres du compte")

        st.markdown(f"**Identifiant** : `{user['username']}`")
        st.markdown(f"**Rôle** : 👨‍🏫 Professeur")

        st.markdown("---")
        st.text_input(
            "Nom d'affichage",
            value=user["name"],
            placeholder="Votre nom",
        )

        st.selectbox(
            "Matière par défaut",
            ["", "Mathématiques", "Physique", "Français",
             "Histoire", "Sciences", "Informatique", "Autre"],
        )

        if st.button("💾 Sauvegarder les paramètres"):
            st.success("✅ Paramètres sauvegardés !")

        # ── Cache des réponses ───────────────────────────────────────────
        st.markdown("---")
        st.subheader("🧠 Cache des réponses")
        cache_stats = response_cache.stats()
        st.caption(
            f"**{cache_stats['entries']}** questions en cache "
            f"({cache_stats['file_size']})"
        )
        if st.button("🗑️ Vider le cache", use_container_width=True):
            response_cache.clear()
            st.success("✅ Cache vidé !")
            st.rerun()

        # ── Synchronisation ───────────────────────────────────────────────
        st.markdown("---")
        with st.expander("🔄 Synchronisation cloud", expanded=False):
            status = check_sync_status()
            st.markdown(format_sync_summary(status))

            if status["new_files"]:
                st.markdown("#### 🆕 Nouveaux fichiers à indexer")
                for f in status["new_files"]:
                    st.markdown(f"- **{f['name']}** ({f.get('size', 0) / 1024:.1f} Ko)")

            if status["modified_files"]:
                st.markdown("#### 🔄 Fichiers modifiés (ré-indexation nécessaire)")
                for f in status["modified_files"]:
                    st.markdown(f"- **{f['name']}** — hash changé")

            if status["missing_files"]:
                st.markdown("#### 🗑️ Fichiers supprimés de Supabase")
                for fname in status["missing_files"]:
                    st.markdown(f"- **{fname}** — plus présent dans le cloud")

            if status["synced_files"]:
                st.markdown(f"✅ **{len(status['synced_files'])}** fichier(s) à jour")

            if not status["new_files"] and not status["modified_files"]:
                st.success("✅ Tout est synchronisé automatiquement.")

            st.caption(
                f"🔄 La synchronisation est automatique — "
                f"dernière vérification : {status['last_checked'][:19]} UTC"
            )

        # ── Informations stockage cloud ─────────────────────────────────
        st.markdown("---")
        with st.expander("☁️ Informations sur le stockage cloud", expanded=True):
            from core.document_store import is_cloud_configured
            cloud_ok = is_cloud_configured()

            docs = get_available_documents()
            total_chunks = sum(d.get("chunks", 0) for d in docs)

            if cloud_ok:
                st.markdown(f"""
                | Élément | Valeur |
                |---|---|
                | ☁️ **Stockage** | Supabase Storage (bucket `cours`) |
                | 📚 **Cours indexés** | `{len(docs)}` |
                | 🔢 **Total passages** | `{total_chunks}` |
                | 🔄 **Persistance** | Immédiate (chaque écriture sync) |
                """)
                st.success("✅ Stockage cloud actif — données persistées dans Supabase.")
            else:
                st.markdown(f"""
                | Élément | Valeur |
                |---|---|
                | 📚 **Cours indexés** | `{len(docs)}` (session uniquement) |
                | 🔢 **Total passages** | `{total_chunks}` |
                | ⚠️ **Persistance** | Aucune (mode mémoire) |
                """)
                st.warning(
                    "⚠️ Supabase non configuré. Les données ne sont pas persistées "
                    "entre les sessions. Configurez SUPABASE_URL et SUPABASE_KEY "
                    "dans les secrets Streamlit."
                )


# ── Fonction utilitaire partagée ─────────────────────────────────────────


def _index_and_store(
    tmp_path: str,
    filename: str,
    text: str,
    content_type: str,
    metadata: dict = None,
):
    """Indexe le texte dans le stockage local.

    Calcule le hash du fichier source pour permettre la détection
    automatique des modifications futures (ré-indexation).

    Args:
        tmp_path: Chemin du fichier temporaire.
        filename: Nom d'affichage.
        text: Texte extrait/transcrit.
        content_type: "pdf" ou "mp4".
        metadata: Métadonnées supplémentaires.
    """
    metadata = metadata or {}
    metadata["content_type"] = content_type
    metadata["size"] = os.path.getsize(tmp_path)

    # ── Calcul du hash du fichier source ─────────────────────────────
    from core.document_store import compute_content_hash
    with open(tmp_path, "rb") as f:
        content_hash = compute_content_hash(f.read())
    metadata["content_hash"] = content_hash
    metadata["hash_algorithm"] = "sha256"

    # ── Upload vers Supabase ──────────────────────────────────────────
    try:
        storage = SupabaseStorage()
        public_url = storage.upload_file(tmp_path, filename)
        metadata["storage_url"] = public_url
        st.success(f"☁️ Fichier sauvegardé sur Supabase Storage")
    except Exception as e:
        st.warning(f"⚠️ Supabase : {e}")

    # ── Logs de stockage cloud ──────────────────────────────────────
    from core.document_store import is_cloud_configured
    cloud_ok = is_cloud_configured()
    cloud_status = (
        "☁️ Données persistées dans Supabase Storage."
        if cloud_ok
        else "⚠️ Supabase non configuré — données en mémoire uniquement."
    )
    st.info(
        f"📂 **Fichier :** `{filename}`\n\n"
        f"📦 {cloud_status}\n\n"
        f"🧬 **Hash :** `{content_hash[:16]}...`"
    )

    # Indexation
    doc_id = index_document(
        text=text,
        filename=filename,
        metadata=metadata,
    )

    if content_type == "mp4":
        duration = metadata.get("duration_display", "")
        st.success(
            f"✅ **{filename}** transcrit et indexé avec succès ! "
            f"(durée: {duration})"
        )
    else:
        st.success(
            f"✅ **{filename}** indexé avec succès ! (ID: {doc_id[:8]}...)"
        )

    st.info("💡 Les élèves peuvent maintenant poser des questions sur ce cours.")