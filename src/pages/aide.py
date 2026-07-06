"""❓ Page d'Aide — Documentation utilisateur."""

import streamlit as st


def show():
    """Affiche la page d'aide."""
    st.title("❓ Aide — eLearnBot")
    st.markdown(
        "Bienvenue sur l'aide d'eLearnBot. "
        "Retrouvez ici toutes les informations pour utiliser l'application."
    )

    # ── Questions fréquentes ───────────────────────────────────────────
    with st.expander("🤔 Qu'est-ce qu'eLearnBot ?"):
        st.markdown("""
        eLearnBot est un **chatbot éducatif** qui permet aux professeurs
        d'uploader leurs cours (PDF) et aux élèves de poser des questions
        en langage naturel. Le système utilise l'IA pour trouver la réponse
        dans les cours et citer la source exacte.
        """)

    with st.expander("👨‍🏫 Comment uploader un cours ?"):
        st.markdown("""
        1. Allez dans le **Mode Professeur**
        2. Cliquez sur **"Uploader un cours"**
        3. Glissez-déposez votre fichier PDF (max 10 Mo)
        4. Attendez l'indexation (quelques secondes)
        5. Le cours est disponible pour les élèves !
        """)

    with st.expander("👨‍🎓 Comment poser une question ?"):
        st.markdown("""
        1. Allez dans le **Mode Élève**
        2. Sélectionnez un cours dans la liste
        3. Tapez votre question dans la zone de chat
        4. Recevez une réponse avec les sources citées
        """)

    with st.expander("📄 Quels formats sont supportés ?"):
        st.markdown("""
        - **PDF** : fichiers texte (pas de PDF scannés)
        - **YouTube** : liens vidéo (bientôt disponible)
        - Taille max : **10 Mo** par fichier
        """)

    with st.expander("🔒 Mes données sont-elles privées ?"):
        st.markdown("""
        Oui ! Toutes les données sont stockées sur votre propre
        **Google Drive**. L'application ne partage rien avec des tiers.
        Les embeddings sont générés localement.
        """)

    with st.expander("🎥 Puis-je ajouter des vidéos YouTube ?"):
        st.markdown("""
        Cette fonctionnalité est en développement. Vous pourrez bientôt
        ajouter un lien YouTube et les élèves pourront poser des questions
        sur la transcription de la vidéo.
        """)

    with st.expander("⚠️ Limitations connues"):
        st.markdown("""
        - **Pas d'OCR** : les PDF scannés ne sont pas supportés en v1
        - **Taille max** : 10 Mo par PDF
        - **Rate limit** : les APIs LLM gratuites ont des limites
          (ex: 30 req/min avec Groq)
        - **YouTube** : seuls les liens sont stockés, pas de transcription
        """)

    with st.expander("🛠️ Configuration technique"):
        st.markdown("""
        **Stack technique :**
        - **Frontend** : Streamlit
        - **Backend** : Python / FastAPI
        - **Vector Store** : ChromaDB
        - **Stockage** : Google Drive
        - **LLM** : Groq / Gemini / OpenAI

        **Code source :** [GitHub](https://github.com) (bientôt disponible)
        """)

    # ── Contact ────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("💬 Besoin d'aide ?")
    st.info(
        "Si vous rencontrez un problème, ouvrez une **Issue GitHub** "
        "ou contactez votre administrateur."
    )