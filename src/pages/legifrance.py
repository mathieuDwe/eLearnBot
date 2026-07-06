"""⚖️ Page Legifrance — Recherche et exploration d'articles juridiques."""

import streamlit as st

from core.auth import require_role
from core.rag_pipeline import index_document, answer_question, get_available_documents
from integrations.legifrance import (
    PISTE_API_KEY,
    search_via_piste,
    get_article_via_piste,
    fetch_article_from_url,
    create_manual_article,
    format_article_for_rag,
    get_article_metadata,
)


def show():
    """Affiche l'interface Legifrance."""
    from core.auth import get_current_user
    user = get_current_user()
    if not user:
        st.error("⛔ Vous devez être connecté.")
        return

    st.title("⚖️ Recherche Juridique")
    st.markdown(
        "Consultez des articles de loi, indexez-les et posez des questions "
        "via le moteur RAG."
    )

    # ── Onglets ──────────────────────────────────────────────────────────
    tabs = st.tabs(["🔍 Rechercher un article", "📝 Saisie manuelle", "💬 Chat juridique"])

    # ── Onglet 1 : Recherche ────────────────────────────────────────────
    with tabs[0]:
        col1, col2 = st.columns([3, 1])
        with col1:
            query = st.text_input(
                "Recherche (mot-clé, article, code…)",
                placeholder="Ex: article 1240 code civil, liberté d'expression...",
                key="legi_search_query",
            )
        with col2:
            max_results = st.number_input("Résultats", 1, 20, 5, key="legi_max")

        if query:
            with st.spinner("Recherche en cours..."):
                if PISTE_API_KEY:
                    results = search_via_piste(query, max_results)
                else:
                    results = []

            if not results:
                st.info(
                    "Aucun résultat trouvé.\n\n"
                    "💡 Pour une recherche en ligne, créez un compte gratuit sur "
                    "[api.piste.gouv.fr](https://api.piste.gouv.fr) "
                    "et ajoutez `PISTE_API_KEY` dans votre fichier `.env`.\n\n"
                    "Sinon, utilisez l'onglet **Saisie manuelle** pour coller "
                    "directement le texte d'un article."
                )
            else:
                st.success(f"{len(results)} résultat(s) trouvé(s)")
                for r in results:
                    with st.container(border=True):
                        st.markdown(f"**{r.title}**")
                        if r.snippet:
                            st.markdown(f"*{r.snippet[:300]}...*")
                        cols = st.columns([3, 1])
                        with cols[0]:
                            if r.url:
                                st.markdown(f"[Voir sur Legifrance]({r.url})")
                        with cols[1]:
                            if r.article_id and st.button(
                                "📥 Indexer", key=f"index_{r.article_id}"
                            ):
                                with st.spinner("Récupération de l'article..."):
                                    article = get_article_via_piste(r.article_id)
                                    if article:
                                        text = format_article_for_rag(article)
                                        meta = get_article_metadata(article)
                                        doc_id = index_document(
                                            text, article.title, meta
                                        )
                                        if doc_id:
                                            st.success(f"✅ Indexé : {article.title}")
                                            st.rerun()
                                        else:
                                            st.error("❌ Échec de l'indexation.")
                                    else:
                                        st.error(
                                            "❌ Impossible de récupérer l'article. "
                                            "Utilisez la saisie manuelle."
                                        )

    # ── Onglet 2 : Saisie manuelle ──────────────────────────────────────
    with tabs[1]:
        st.markdown("Collez ici le texte d'un article juridique à indexer.")

        col1, col2 = st.columns(2)
        with col1:
            article_title = st.text_input(
                "Titre de l'article",
                placeholder="Ex: Article 1240 du Code civil",
                key="manual_title",
            )
        with col2:
            code_name = st.text_input(
                "Code / Source",
                placeholder="Ex: Code civil, Légifrance",
                value="Document juridique",
                key="manual_code",
            )

        article_text = st.text_area(
            "Texte de l'article",
            placeholder="Collez le contenu de l'article ici...",
            height=300,
            key="manual_text",
        )

        if st.button("📥 Indexer cet article", use_container_width=True, type="primary"):
            if not article_title or not article_text:
                st.warning("Veuillez remplir le titre et le texte.")
            else:
                article = create_manual_article(article_title, article_text, code_name)
                text = format_article_for_rag(article)
                meta = get_article_metadata(article)
                with st.spinner("Indexation en cours..."):
                    doc_id = index_document(text, article_title, meta)
                if doc_id:
                    st.success(f"✅ Article indexé : {article_title}")
                    st.rerun()
                else:
                    st.error("❌ Échec de l'indexation.")

    # ── Onglet 3 : Chat juridique ──────────────────────────────────────
    with tabs[2]:
        all_docs = get_available_documents()
        legal_docs = [d for d in all_docs if d.get("metadata", {}).get("type") == "legal"]

        if not legal_docs:
            st.info(
                "Aucun article juridique indexé. "
                "Utilisez l'onglet **Saisie manuelle** ou la **Recherche** "
                "pour indexer des articles."
            )
        else:
            total = len(all_docs)
            legal = len(legal_docs)
            courses = total - legal
            st.markdown(
                f"📚 **{legal} article(s) juridique(s)** indexé(s) "
                f"— {courses} cours disponible(s)"
            )

            # Filtre : tous (cours + juridique) ou un article spécifique
            doc_names = [d["filename"] for d in all_docs]
            filter_options = ["🌐 Tous (cours + juridique)"] + [
                d["filename"] for d in legal_docs
            ]
            selected = st.selectbox(
                "Filtrer la recherche",
                filter_options,
                key="legal_doc_filter",
            )

            st.markdown("---")
            st.markdown("### 💬 Posez votre question")
            st.caption(
                "L'agent cherche la réponse à la fois dans les cours et dans "
                "les articles juridiques indexés."
            )

            if "legal_chat_history" not in st.session_state:
                st.session_state.legal_chat_history = []

            for msg in st.session_state.legal_chat_history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

            question = st.chat_input(
                "Ex: Que dit l'article 1240 du Code civil ?"
            )
            if question:
                st.session_state.legal_chat_history.append(
                    {"role": "user", "content": question}
                )
                with st.chat_message("user"):
                    st.markdown(question)

                with st.chat_message("assistant"):
                    with st.spinner("Recherche dans tous les contenus..."):
                        doc_filter = (
                            selected if selected != "🌐 Tous (cours + juridique)"
                            else None
                        )
                        result = answer_question(question, document_name=doc_filter)

                    st.markdown(result["answer"])
                    if result["sources"]:
                        with st.expander("📖 Sources"):
                            for s in result["sources"]:
                                st.markdown(f"- {s}")

                st.session_state.legal_chat_history.append(
                    {"role": "assistant", "content": result["answer"]}
                )