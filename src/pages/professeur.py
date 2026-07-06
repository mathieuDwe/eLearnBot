"""👨‍🏫 Page Professeur — Upload et gestion des cours."""

import streamlit as st
import tempfile
import os

from core.auth import require_role, get_current_user
from core.pdf_extractor import extract_text_from_pdf
from core.rag_pipeline import index_document, get_available_documents
from integrations.google_drive import GoogleDriveClient


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
        f"Bienvenue **{user['name']}** ! Uploader vos cours PDF. "
        "Les élèves pourront ensuite poser des questions dessus."
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

        uploaded_file = st.file_uploader(
            "Choisissez un fichier PDF",
            type=["pdf"],
            help="Taille max : 10 Mo",
        )

        if uploaded_file is not None:
            if uploaded_file.size > 10 * 1024 * 1024:
                st.error("❌ Le fichier dépasse 10 Mo.")
            else:
                with st.spinner("⏳ Traitement en cours..."):
                    # Sauvegarder le fichier temporairement
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=".pdf"
                    ) as tmp:
                        tmp.write(uploaded_file.getvalue())
                        tmp_path = tmp.name

                    try:
                        # 1. Extraire le texte
                        text = extract_text_from_pdf(tmp_path)

                        if not text.strip():
                            st.warning(
                                "⚠️ Le PDF semble vide ou contient uniquement "
                                "des images (OCR non supporté en v1)."
                            )
                        else:
                            # 2. Uploader vers Google Drive
                            try:
                                drive = GoogleDriveClient()
                                drive.upload_pdf(
                                    tmp_path, uploaded_file.name
                                )
                                st.success(
                                    f"✅ Fichier uploadé sur Google Drive"
                                )
                            except Exception as e:
                                st.warning(
                                    f"⚠️ Google Drive indisponible : {e}. "
                                    "Le document sera indexé localement."
                                )

                            # 3. Indexer dans ChromaDB
                            doc_id = index_document(
                                text=text,
                                filename=uploaded_file.name,
                                metadata={
                                    "source": "upload",
                                    "size": uploaded_file.size,
                                },
                            )
                            st.success(
                                f"✅ **{uploaded_file.name}** indexé avec "
                                f"succès ! (ID: {doc_id[:8]}...)"
                            )

                            st.info(
                                "💡 Les élèves peuvent maintenant poser "
                                "des questions sur ce cours."
                            )
                    except Exception as e:
                        st.error(f"❌ Erreur lors du traitement : {e}")
                    finally:
                        os.unlink(tmp_path)

        # ── Upload par URL YouTube (optionnel) ─────────────────────────
        st.markdown("---")
        st.subheader("🎥 Ajouter une vidéo YouTube")
        st.info(
            "Fonctionnalité à venir : ajoutez un lien YouTube et "
            "les élèves pourront poser des questions sur la transcription."
        )
        youtube_url = st.text_input(
            "Lien YouTube",
            placeholder="https://www.youtube.com/watch?v=...",
        )
        if youtube_url and st.button("Ajouter la vidéo"):
            st.info("🔧 Fonctionnalité en développement.")

    # ── Onglet 2 : Mes cours ───────────────────────────────────────────
    with tab2:
        st.subheader("Cours indexés")

        documents = get_available_documents()

        if not documents:
            st.info("📭 Aucun cours pour le moment. Uploader un PDF dans l'onglet précédent.")
        else:
            for doc in documents:
                with st.container(border=True):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"**📄 {doc['filename']}**")
                        st.caption(f"🔢 {doc['chunks']} passages indexés")
                    with col2:
                        if st.button("🗑️ Supprimer", key=f"del_{doc['filename']}"):
                            from core.vector_store import get_vector_store
                            deleted = get_vector_store().delete_document(doc['filename'])
                            st.success(f"✅ {deleted} passages supprimés.")
                            st.rerun()

    # ── Onglet 3 : Paramètres ──────────────────────────────────────────
    with tab3:
        st.subheader("Paramètres du compte")

        st.markdown(f"**Email** : {user['email']}")
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