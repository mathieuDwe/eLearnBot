#!/usr/bin/env python3
"""🚀 eLearnBot — Point d'entrée de l'application Streamlit."""

from dotenv import load_dotenv

load_dotenv()

import os
import streamlit as st

from core.auth import init_session, is_authenticated, get_current_user, logout_user
from core.vector_store import load_chroma_from_cloud

# ── Configuration de la page ──────────────────────────────────────────────
st.set_page_config(
    page_title="eLearnBot — Chatbot Éducatif",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialiser la session (authentification, etc.)
init_session()

# ── Initialisation des connexions persistantes ────────────────────────────
# Restaurer ChromaDB depuis le cloud (nécessaire après redémarrage
# sur Streamlit Cloud où le filesystem est éphémère)
with st.spinner("🔄 Restauration de la base vectorielle..."):
    load_chroma_from_cloud()

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
    /* Masquer la navigation automatique Streamlit (pages/*.py) */
    [data-testid="stSidebarNav"] {
        display: none;
    }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────
col_logo, col_title = st.sidebar.columns([1, 3])
with col_logo:
    st.image(
        "https://img.icons8.com/fluency/96/books.png",
        width=70,
    )
with col_title:
    st.markdown("## 🎓 eLearnBot")

# ── Indicateurs d'état des connexions ────────────────────────────────
with st.sidebar:
    st.divider()
    st.caption("🔌 **Connexions**")

    # Supabase
    supabase_ok = bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"))
    if supabase_ok:
        st.caption("✅ **Supabase** — connectée")
    else:
        st.caption("⚠️ **Supabase** — non configurée")

    # ChromaDB
    chroma_ok = os.path.isdir(os.getenv("CHROMA_DB_PATH", "./chroma_db"))
    if chroma_ok:
        st.caption("✅ **ChromaDB** — base locale présente")
    else:
        st.caption("ℹ️ **ChromaDB** — sera créée au 1er upload")
    st.divider()

# ── Affichage selon authentification ──────────────────────────────────────
if is_authenticated():
    user = get_current_user()

    # ── Navigation ────────────────────────────────────────────────────
    role = user["role"]

    pages_config = {
        "admin": [
            ("🏠", "Accueil", "accueil"),
            ("👨‍🏫", "Professeur", "professeur"),
            ("👨‍🎓", "Élève", "eleve"),
            ("⚖️", "Légifrance", "legifrance"),
            ("❓", "Aide", "aide"),
        ],
        "professeur": [
            ("👨‍🏫", "Professeur", "professeur"),
            ("⚖️", "Légifrance", "legifrance"),
            ("❓", "Aide", "aide"),
        ],
        "eleve": [
            ("👨‍🎓", "Élève", "eleve"),
            ("⚖️", "Légifrance", "legifrance"),
            ("❓", "Aide", "aide"),
        ],
    }

    if "current_page" not in st.session_state:
        st.session_state.current_page = pages_config[role][0][2]

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

    # ── Déconnexion (tout en bas de la sidebar) ──────────────────────
    st.sidebar.markdown("---")
    st.sidebar.caption(f"Connecté en tant que **{user['name']}** ({role})")
    if st.sidebar.button("🚪 Déconnexion", use_container_width=True):
        logout_user()
        st.rerun()

    # Routage selon la page sélectionnée
    page = st.session_state.current_page
    if page == "accueil":
        from pages.accueil import show
        show()
    elif page == "admin":
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
    from pages.login import show
    show()