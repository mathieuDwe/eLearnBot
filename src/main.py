#!/usr/bin/env python3
"""🚀 eLearnBot — Point d'entrée de l'application Streamlit."""

from dotenv import load_dotenv

load_dotenv()

import os
import streamlit as st

from core.auth import init_session, is_authenticated, get_current_user, logout_user, login_user
from core.document_store import sync_from_cloud
from core.session import try_auto_login, inject_cookie_check
from core.reindexer import auto_reindex_on_startup
from integrations.supabase_storage import check_supabase_health

# ── Configuration de la page ──────────────────────────────────────────────
st.set_page_config(
    page_title="eLearnBot — Chatbot Éducatif",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _show_loading_screen():
    """Affiche un écran de chargement minimal pendant la vérification du cookie.

    L'écran est volontairement simple et rapide à rendre :
    pas de composants lourds, pas d'appels réseau.
    Il disparaît dès que le JS a redirigé ou que le rerun s'exécute.
    """
    st.markdown("### 🎓 eLearnBot")
    st.info("🔍 Vérification de votre session...")


# Initialiser la session (authentification, etc.)
init_session()

# ── Connexion automatique via cookie ──────────────────────────────────────
# Vérifie si l'URL contient un token de session (redirigé depuis le cookie)
auto_user = try_auto_login()
if auto_user and not is_authenticated():
    login_user(auto_user)

# Évite le flash de la page login :
#   1ʳᵉ visite → injecte le JS cookie + écran de chargement
#   Si cookie valide → JS redirige vers ?session_token=... → auto-login
#   Si pas de cookie → JS redirige vers ?_cookie_done=1 → formulaire login
# La page login n'est jamais rendue avant la redirection JS.
if not is_authenticated() and "_cookie_attempted" not in st.session_state:
    st.session_state._cookie_attempted = True
    inject_cookie_check()
    _show_loading_screen()
    st.rerun()

# ── Initialisation : sync depuis le cloud ────────────────────────────────
with st.spinner("☁️ Synchronisation des documents depuis le cloud..."):
    sync_from_cloud()

# ── Ré-indexation automatique (une seule fois par session) ──────────────
if "_auto_reindex_done" not in st.session_state:
    st.session_state._auto_reindex_done = True
    report = auto_reindex_on_startup()
    if report.get("total_processed", 0) > 0:
        n_new = len(report.get("indexed", []))
        n_upd = len(report.get("updated", []))
        n_err = len(report.get("errors", []))
        parts = []
        if n_new:
            parts.append(f"📥 {n_new} nouveau(x) indexé(s)")
        if n_upd:
            parts.append(f"🔄 {n_upd} mis à jour")
        if n_err:
            parts.append(f"❌ {n_err} erreur(s)")
        st.toast(f"🔁 Auto-réindexation : {', '.join(parts)}")
    elif report.get("message"):
        pass  # Silencieux si tout est à jour

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


# ── Indicateurs d'état des connexions (admin uniquement, connecté uniquement) ─
def _show_connection_status():
    """Affiche les indicateurs d'état des connexions.

    N'affiche rien si Supabase n'est pas connecté (silencieux).
    Réservé aux admins (appel conditionnel dans la sidebar).
    """
    health = check_supabase_health()
    if not health["supabase"]:
        return  # Pas de connexion → rien n'est affiché

    with st.sidebar:
        st.divider()
        st.caption("🔌 **Connexions**")

        st.caption("✅ **Supabase** — connectée")
        if health["bucket"]:
            st.caption(f"📦 **Bucket** `{health['bucket_name']}` — {health['files_count']} fichier(s)")
        else:
            st.caption(f"⚠️ **Bucket** `{health['bucket_name']}` — inexistant → les uploads échoueront")
            if st.button("➕ Créer le bucket", key="create_bucket"):
                try:
                    from supabase import create_client
                    client = create_client(
                        os.getenv("SUPABASE_URL", ""),
                        os.getenv("SUPABASE_KEY", ""),
                    )
                    client.storage.create_bucket(
                        health['bucket_name'],
                        options={"public": True},
                    )
                    st.success(f"✅ Bucket `{health['bucket_name']}` créé !")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Création échouée : {e}")

        # Documents
        from core.document_store import count_documents
        nb_docs = count_documents()
        if nb_docs > 0:
            st.caption(f"📚 **Documents** — {nb_docs} cours indexés")
        else:
            st.caption("ℹ️ **Documents** — aucun cours indexé")
        st.divider()


# ── Sidebar (authentifié uniquement) ──────────────────────────────────────
if is_authenticated():
    user = get_current_user()
    role = user["role"]
    user_type = user.get("type", role)  # type de la table (admin/professeur/eleve)

    col_logo, col_title = st.sidebar.columns([1, 3])
    with col_logo:
        st.image(
            "https://img.icons8.com/fluency/96/books.png",
            width=70,
        )
    with col_title:
        st.markdown("## 🎓 eLearnBot")

    # ── Connexions : uniquement pour les admins (basé sur le type) ────
    if user_type == "admin":
        _show_connection_status()

    # ── Navigation ────────────────────────────────────────────────────
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