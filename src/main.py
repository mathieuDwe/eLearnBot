#!/usr/bin/env python3
"""🚀 eLearnBot — Point d'entrée de l'application Streamlit."""

import streamlit as st

# ── Configuration de la page ──────────────────────────────────────────────
st.set_page_config(
    page_title="eLearnBot — Chatbot Éducatif",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
</style>
""", unsafe_allow_html=True)

# ── Sidebar : Navigation ──────────────────────────────────────────────────
st.sidebar.image(
    "https://img.icons8.com/fluency/96/books.png",
    width=80,
)
st.sidebar.title("🎓 eLearnBot")
st.sidebar.markdown("---")

mode = st.sidebar.radio(
    "Mode",
    ["🏠 Accueil", "👨‍🏫 Professeur", "👨‍🎓 Élève", "❓ Aide"],
    index=0,
)

st.sidebar.markdown("---")
st.sidebar.info(
    "💡 **Astuce :** Les professeurs peuvent uploader des cours PDF. "
    "Les élèves peuvent poser des questions en langage naturel."
)

# ── Routage des pages ─────────────────────────────────────────────────────
if mode == "🏠 Accueil":
    from pages.accueil import show
    show()
elif mode == "👨‍🏫 Professeur":
    from pages.professeur import show
    show()
elif mode == "👨‍🎓 Élève":
    from pages.eleve import show
    show()
elif mode == "❓ Aide":
    from pages.aide import show
    show()