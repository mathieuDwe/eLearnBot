"""👨‍🎓 Page Élève — Consultation et questions sur les cours."""

import streamlit as st

from core.auth import require_role, get_current_user
from core.rag_pipeline import answer_question, get_available_documents


def show():
    """Affiche l'interface élève."""
    # Vérification du rôle
    if not require_role("professeur", "eleve"):
        st.error("⛔ Veuillez vous connecter pour accéder à cette page.")
        return

    user = get_current_user()
    st.title("👨‍🎓 Mode Élève")
    st.markdown(
        f"Bienvenue **{user['name']}** ! Posez une question sur un cours. "
        "Le chatbot vous répondra en citant les passages sources."
    )

    # ── Initialisation de l'historique ─────────────────────────────────
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # ── Sélection du cours ─────────────────────────────────────────────
    st.subheader("📚 Sélectionner un cours")

    documents = get_available_documents()

    if not documents:
        st.warning(
            "📭 Aucun cours disponible pour le moment. "
            "Demandez à votre professeur d'en uploader."
        )
        selected_doc = None
    else:
        # Afficher la liste des cours avec leur type
        doc_options = []
        for d in documents:
            meta = d.get("metadata", {})
            content_type = meta.get("content_type", "pdf")
            icon = "🎬" if content_type == "mp4" else "📄"
            duration = meta.get("duration_display", "")
            label = f"{icon} {d['filename']}"
            if duration:
                label += f" ({duration})"
            doc_options.append(label)

        selected_label = st.selectbox(
            "Choisissez un cours",
            doc_options,
        )

        # Récupérer le filename depuis le label
        selected_idx = doc_options.index(selected_label)
        selected_doc = documents[selected_idx]["filename"]
        selected_meta = documents[selected_idx].get("metadata", {})

        # Afficher une info sur le type de cours sélectionné
        content_type = selected_meta.get("content_type", "pdf")
        if content_type == "mp4":
            duration = selected_meta.get("duration_display", "")
            st.caption(
                f"🎬 Cours vidéo — Durée : {duration}"
                if duration
                else "🎬 Cours vidéo"
            )
        else:
            st.caption("📄 Cours (PDF)")

        st.caption(f"{len(documents)} cours disponible(s)")

    # ── Zone de chat ───────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("💬 Poser une question")

    # Afficher l'historique
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if "sources" in msg and msg["sources"]:
                with st.expander("📖 Sources"):
                    for i, src in enumerate(msg["sources"], 1):
                        st.markdown(f"**Source {i}** : {src}")

    # Champ de saisie
    if prompt := st.chat_input(
        "Posez votre question sur le cours...",
        disabled=(selected_doc is None),
    ):
        # Ajouter la question
        st.session_state.messages.append(
            {"role": "user", "content": prompt}
        )
        with st.chat_message("user"):
            st.markdown(prompt)

        # Générer la réponse
        with st.chat_message("assistant"):
            with st.spinner("🔍 Recherche dans les cours..."):
                try:
                    result = answer_question(
                        question=prompt,
                        document_name=selected_doc,
                    )

                    response = result["answer"]
                    sources = result.get("sources", [])

                    st.markdown(response)
                    if sources:
                        with st.expander("📖 Sources"):
                            for i, src in enumerate(sources, 1):
                                st.markdown(f"**Source {i}** : {src}")

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": response,
                        "sources": sources,
                    })

                except Exception as e:
                    st.error(f"❌ Erreur : {e}")
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"❌ Désolé, une erreur est survenue : {e}",
                        "sources": [],
                    })

    # ── Exemples de questions ──────────────────────────────────────────
    if selected_doc and not st.session_state.messages:
        st.markdown("---")
        st.subheader("💡 Exemples de questions")
        examples = [
            "Résume ce chapitre en 3 points",
            "Explique le concept principal",
            "Donne un exemple concret",
            "Quelle est la formule la plus importante ?",
        ]
        cols = st.columns(2)
        for i, example in enumerate(examples):
            with cols[i % 2]:
                if st.button(f"💬 {example}", use_container_width=True):
                    # Simuler le clic en remplissant le chat
                    st.session_state.messages.append(
                        {"role": "user", "content": example}
                    )
                    st.rerun()

    # ── Bouton d'effacement ────────────────────────────────────────────
    if st.session_state.messages:
        st.markdown("---")
        if st.button("🗑️ Effacer l'historique"):
            st.session_state.messages = []
            st.rerun()