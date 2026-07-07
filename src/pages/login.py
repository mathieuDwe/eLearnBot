"""🔐 Page de connexion."""

import streamlit as st

from core.auth import (
    authenticate_user,
    login_user,
)


def show():
    """Affiche le formulaire de connexion."""
    st.markdown(
        "<div class='main-header'>",
        unsafe_allow_html=True,
    )
    st.title("🎓 eLearnBot")
    st.markdown(
        "<p>Connectez-vous pour accéder à votre espace</p>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("🔑 Connexion")

    with st.form("form_connexion"):
        username = st.text_input(
            "Nom d'utilisateur",
            placeholder="ex: jean.dupont",
        )
        password = st.text_input(
            "Mot de passe",
            type="password",
            placeholder="Votre mot de passe",
        )

        submitted = st.form_submit_button(
            "🔑 Se connecter",
            use_container_width=True,
        )

        if submitted:
            if not username or not password:
                st.error("❌ Veuillez remplir tous les champs.")
            else:
                result = authenticate_user(username, password)
                if result["success"]:
                    login_user(result["user"])
                    st.success(
                        f"✅ Bienvenue, {result['user']['name']} !"
                    )
                    st.rerun()
                else:
                    st.error(f"❌ {result['message']}")