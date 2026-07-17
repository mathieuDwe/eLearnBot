"""❓ Page d'Aide — Documentation utilisateur."""

import streamlit as st

from core.auth import get_current_user


def show():
    """Affiche la page d'aide."""
    st.title("❓ Aide — eLearnBot")
    st.markdown(
        "Bienvenue sur l'aide d'eLearnBot. "
        "Retrouvez ici toutes les informations pour utiliser l'application."
    )

    # ── Informations utilisateur connecté ───────────────────────────────
    user = get_current_user()
    if user:
        role_icon = {"admin": "👑", "professeur": "👨‍🏫", "eleve": "👨‍🎓"}.get(
            user.get("type", user["role"]), "👤"
        )
        user_type = user.get("type", user["role"])
        st.markdown("---")
        col1, col2 = st.columns([1, 4])
        with col1:
            st.markdown(f"### {role_icon}")
        with col2:
            st.markdown(f"### {user.get('name', user['username'])}")
            st.caption(f"@{user['username']}  ·  `{user_type}`")
            st.caption(
                f"Connecté depuis cette session · "
                f"Rôle basé sur le champ `type` de la table utilisateurs"
            )
        st.markdown("---")

    # ── Déterminer le type pour le filtrage des sections ─────────────
    user = get_current_user()  # récupération propre (hors du bloc if)
    user_type = user.get("type", user["role"]) if user else "admin"
    is_admin = user_type == "admin"
    is_prof = user_type == "professeur"
    is_eleve = user_type == "eleve"

    # ── Questions fréquentes (filtrées par type d'utilisateur) ─────────

    # Tout le monde : présentation générale
    if is_admin or is_prof or is_eleve:
        with st.expander("🤔 Qu'est-ce qu'eLearnBot ?"):
            st.markdown("""
            eLearnBot est un **chatbot éducatif** qui permet aux professeurs
            d'uploader leurs cours (PDF) et aux élèves de poser des questions
            en langage naturel. Le système utilise l'IA pour trouver la réponse
            dans les cours et citer la source exacte.
            """)

    # Élèves + admins : poser une question
    if is_admin or is_eleve:
        with st.expander("👨‍🎓 Comment poser une question ?"):
            st.markdown("""
            1. Allez dans le **Mode Élève**
            2. Sélectionnez un cours dans la liste
            3. Tapez votre question dans la zone de chat
            4. Recevez une réponse avec les sources citées
            """)

    # Professeurs + admins : upload, formats, vidéo, limitations
    if is_admin or is_prof:
        with st.expander("👨‍🏫 Comment uploader un cours ?"):
            st.markdown("""
            1. Allez dans le **Mode Professeur**
            2. Cliquez sur **"Uploader un cours"**
            3. Glissez-déposez votre fichier PDF (max 10 Mo)
            4. Attendez l'indexation (quelques secondes)
            5. Le cours est disponible pour les élèves !
            """)

        with st.expander("📄 Quels formats sont supportés ?"):
            st.markdown("""
            - **PDF** : fichiers texte (pas de PDF scannés)
            - **MP4** : vidéos avec transcription automatique
            - Taille max : **10 Mo** par PDF, **100 Mo** par vidéo
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

    # Tout le monde : vie privée
    if is_admin or is_prof or is_eleve:
        with st.expander("🔒 Mes données sont-elles privées ?"):
            st.markdown("""
            Oui ! Les cours sont stockés de manière sécurisée dans
            Supabase. Aucune donnée n'est partagée avec des tiers.
            """)

    # Admin uniquement : configuration technique
    if is_admin:
        with st.expander("🛠️ Configuration technique"):
            st.markdown("""
            **Stack technique :**
            - **Frontend** : Streamlit
            - **Backend** : Python / FastAPI
            - **Stockage** : Supabase (PostgreSQL + Storage)
            - **Base vectorielle** : ChromaDB
            - **Recherche** : BM25 + embeddings (sentence-transformers)
            - **LLM** : Groq / Gemini (fallback automatique)
            - **Transcription** : Whisper (Groq)

            **Code source :** [GitHub](https://github.com/mathieuDwe/eLearnBot)
            """)

    # ── Contact ────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("💬 Besoin d'aide ?")
    st.info(
        "Si vous rencontrez un problème, ouvrez une **Issue GitHub** "
        "ou contactez votre administrateur."
    )