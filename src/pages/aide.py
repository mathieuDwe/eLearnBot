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
        - **MP4** : vidéos avec transcription automatique
        - Taille max : **10 Mo** par PDF, **100 Mo** par vidéo
        """)

    with st.expander("🔒 Mes données sont-elles privées ?"):
        st.markdown("""
        Oui ! Les cours sont stockés localement et indexés dans une base
        de données JSON. Aucune donnée n'est partagée avec des tiers.
        """)

    with st.expander("🎥 Comment ajouter une vidéo ?"):
        st.markdown("""
        Uploadez un fichier **MP4** directement depuis l'interface
        Professeur. L'audio est extrait et transcrit automatiquement
        (Whisper) pour être indexé dans la base de connaissances.
        """)

    with st.expander("⚠️ Limitations connues"):
        st.markdown("""
        - **Pas d'OCR** : les PDF scannés ne sont pas supportés en v1
        - **Taille max** : 10 Mo par PDF, 200 Mo par vidéo
        - **Rate limit** : les APIs LLM gratuites ont des limites
          (ex: 30 req/min avec Groq)
        - **Vidéos longues** : la transcription peut prendre plusieurs minutes
        """)

    with st.expander("🛠️ Configuration technique"):
        st.markdown("""
        **Stack technique :**
        - **Frontend** : Streamlit
        - **Backend** : Python
        - **Stockage** : Supabase + JSON local
        - **Recherche** : mots-clés (pas de LLM)
        - **Transcription** : Whisper (Groq)

        **Code source :** [GitHub](https://github.com) (bientôt disponible)
        """)

    # ── Contact ────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("💬 Besoin d'aide ?")
    st.info(
        "Si vous rencontrez un problème, ouvrez une **Issue GitHub** "
        "ou contactez votre administrateur."
    )