#!/usr/bin/env python3
"""🚀 eLearnBot — Point d'entrée de l'application Streamlit."""

from dotenv import load_dotenv

load_dotenv()

import streamlit as st

from core.auth import init_session, is_authenticated, get_current_user, logout_user

# ── Configuration de la page ──────────────────────────────────────────────
st.set_page_config(
    page_title="eLearnBot — Chatbot Éducatif",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialiser la session (authentification, etc.)
init_session()

# ── CSS personnalisé ──────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 2rem 0;
    }
    .main-header h1 {
        font-size: 2.8rem;
        color: #4A90D9;
        margin-bottom: 0.5rem;
    }
    .main-header p {
        font-size: 1.2rem;
        color: #666;
    }
    .feature-card {
        background: #f8f9fa;
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1rem 0;
        border-left: 4px solid #4A90D9;
        transition: transform 0.2s;
    }
    .feature-card:hover {
        transform: translateX(4px);
    }
    .stButton button {
        border-radius: 8px;
        font-weight: 600;
        padding: 0.5rem 2rem;
    }
    /* Style pour le badge utilisateur dans la sidebar */
    .user-badge {
        background: #e8f0fe;
        border-radius: 8px;
        padding: 0.8rem;
        margin: 0.5rem 0;
        font-size: 0.9rem;
        text-align: center;
    }
    .user-badge-admin {
        border-left: 3px solid #FFD700;
    }
    .user-badge-prof {
        border-left: 3px solid #4A90D9;
    }
    .user-badge-eleve {
        border-left: 3px solid #34A853;
    }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────
st.sidebar.image(
    "https://img.icons8.com/fluency/96/books.png",
    width=80,
)
st.sidebar.title("🎓 eLearnBot")
st.sidebar.markdown("---")

# ── Affichage selon authentification ──────────────────────────────────────
if is_authenticated():
    user = get_current_user()

    # ── Badge utilisateur ───────────────────────────────────────────────
    role_class = {
        "admin": "user-badge-admin",
        "professeur": "user-badge-prof",
        "eleve": "user-badge-eleve",
    }.get(user["role"], "user-badge-eleve")

    role_icon = {
        "admin": "👑",
        "professeur": "👨‍🏫",
        "eleve": "👨‍🎓",
    }.get(user["role"], "👤")

    st.sidebar.markdown(
        f"<div class='user-badge {role_class}'>"
        f"  <strong>{role_icon} {user['name']}</strong><br>"
        f"  <small>@{user['username']}</small><br>"
        f"  <small>Rôle : {user['role']}</small>"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.sidebar.markdown("---")

    # ── Bouton de déconnexion ───────────────────────────────────────────
    if st.sidebar.button("🚪 Déconnexion", use_container_width=True):
        logout_user()
        st.rerun()

    # ── Navigation ────────────────────────────────────────────────────
    # Définir les pages disponibles selon le rôle
    role = user["role"]

    pages_config = {
        "admin": [
            ("🏠", "Dashboard", "admin"),
            ("👨‍🏫", "Professeur", "professeur"),
            ("👨‍🎓", "Élève", "eleve"),
            ("⚖️", "Légifrance", "legifrance"),
            ("❓", "Aide", "aide"),
        ],
        "professeur": [
            ("👨‍🏫", "Tableau de bord", "professeur"),
            ("⚖️", "Légifrance", "legifrance"),
            ("❓", "Aide", "aide"),
        ],
        "eleve": [
            ("👨‍🎓", "Tableau de bord", "eleve"),
            ("⚖️", "Légifrance", "legifrance"),
            ("❓", "Aide", "aide"),
        ],
    }

    # Session : mémoriser la page active
    if "current_page" not in st.session_state:
        st.session_state.current_page = pages_config[role][0][2]

    # Sidebar : liens de navigation
    st.sidebar.markdown("### 📍 Navigation")
    for icon, label, page_id in pages_config[role]:
        active = st.session_state.current_page == page_id
        btn_style = "primary" if active else "secondary"
        if st.sidebar.button(
            f"{icon} {label}",
            use_container_width=True,
            type=btn_style,
            key=f"nav_{page_id}",
        ):
            st.session_state.current_page = page_id
            st.rerun()

    st.sidebar.markdown("---")

    # Routage selon la page sélectionnée
    page = st.session_state.current_page
    if page == "admin":
        from pages.admin import show
        show()
    elif page == "professeur":
        from pages.professeur import show
        show()
    elif page == "eleve":
        from pages.eleve import show
        show()
    elif page == "legifrance":
        from pages.legifrance import show
        show()
    elif page == "aide":
        from pages.aide import show
        show()

else:
    # ── Non connecté : uniquement l'écran de connexion ─────────────────
    from pages.login import show
    show()