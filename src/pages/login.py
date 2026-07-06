"""🔐 Page de connexion et d'inscription."""

import streamlit as st

from core.auth import (
    register_user,
    authenticate_user,
    login_user,
    ROLES,
)


def show():
    """Affiche le formulaire de connexion/inscription."""
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

    # ── Onglets Connexion / Inscription ─────────────────────────────────
    tab_connexion, tab_inscription = st.tabs([
        "🔑 Connexion",
        "📝 Inscription",
    ])

    # ── Connexion ───────────────────────────────────────────────────────
    with tab_connexion:
        st.subheader("Connexion")

        with st.form("form_connexion"):
            email = st.text_input(
                "Email",
                placeholder="ex: jean.dupont@email.com",
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
                if not email or not password:
                    st.error("❌ Veuillez remplir tous les champs.")
                else:
                    result = authenticate_user(email, password)
                    if result["success"]:
                        login_user(result["user"])
                        st.success(
                            f"✅ Bienvenue, {result['user']['name']} !"
                        )
                        st.rerun()
                    else:
                        st.error(f"❌ {result['message']}")

        st.markdown("---")
        st.caption("💡 **Compte de test** : créez-en un dans l'onglet Inscription.")

    # ── Inscription ─────────────────────────────────────────────────────
    with tab_inscription:
        st.subheader("Créer un compte")

        with st.form("form_inscription"):
            name = st.text_input(
                "Nom d'affichage",
                placeholder="ex: Jean Dupont",
            )

            email = st.text_input(
                "Email",
                placeholder="ex: jean.dupont@email.com",
            )

            col1, col2 = st.columns(2)
            with col1:
                password = st.text_input(
                    "Mot de passe",
                    type="password",
                    placeholder="Au moins 6 caractères",
                )
            with col2:
                password_confirm = st.text_input(
                    "Confirmer le mot de passe",
                    type="password",
                    placeholder="Retaper le mot de passe",
                )

            role = st.selectbox(
                "Vous êtes...",
                options=ROLES,
                format_func=lambda r: {
                    "professeur": "👨‍🏫 Professeur — Je crée et gère des cours",
                    "eleve": "👨‍🎓 Élève — Je consulte et pose des questions",
                }.get(r, r),
            )

            submitted = st.form_submit_button(
                "📝 Créer mon compte",
                use_container_width=True,
            )

            if submitted:
                # Validation
                errors = []
                if not name.strip():
                    errors.append("Le nom est requis.")
                if not email:
                    errors.append("L'email est requis.")
                if not password:
                    errors.append("Le mot de passe est requis.")
                if password != password_confirm:
                    errors.append("Les mots de passe ne correspondent pas.")
                if password and len(password) < 6:
                    errors.append(
                        "Le mot de passe doit faire au moins 6 caractères."
                    )

                if errors:
                    for err in errors:
                        st.error(f"❌ {err}")
                else:
                    result = register_user(
                        email=email,
                        name=name.strip(),
                        password=password,
                        role=role,
                    )
                    if result["success"]:
                        st.success(
                            f"✅ Compte créé avec succès ! "
                            f"Vous pouvez maintenant vous connecter."
                        )
                        st.balloons()
                    else:
                        st.error(f"❌ {result['message']}")

        st.markdown("---")
        st.caption(
            "💡 Les mots de passe sont hachés avec bcrypt. "
            "Aucun email n'est envoyé."
        )