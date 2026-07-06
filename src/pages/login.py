"""🔐 Page de connexion et d'inscription (via Supabase)."""

import streamlit as st

from core.auth import (
    register_user,
    authenticate_user,
    login_user,
    ROLES,
    ADMIN_SECRET_CODE,
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

        st.markdown("---")
        st.caption("💡 Créez un compte dans l'onglet Inscription.")

    # ── Inscription ─────────────────────────────────────────────────────
    with tab_inscription:
        st.subheader("Créer un compte")

        with st.form("form_inscription"):
            username = st.text_input(
                "Nom d'utilisateur",
                placeholder="ex: jean.dupont",
                help="Identifiant unique (2-30 car., lettres, chiffres, tirets).",
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

            user_type = st.selectbox(
                "Vous êtes...",
                options=("eleve", "professeur"),
                format_func=lambda r: {
                    "professeur": "👨‍🏫 Professeur — Je crée et gère des cours",
                    "eleve": "👨‍🎓 Élève — Je consulte et pose des questions",
                }.get(r, r),
            )

            # ── Option admin (dépliée) ────────────────────────────────
            with st.expander("👑 Administrateur (code requis)"):
                st.markdown(
                    "Réservé aux administrateurs. "
                    "Le code secret est configuré dans le fichier `.env`."
                )
                admin_code = st.text_input(
                    "Code administrateur",
                    type="password",
                    placeholder="Code secret admin",
                    help="Demandez le code à votre administrateur.",
                )

            submitted = st.form_submit_button(
                "📝 Créer mon compte",
                use_container_width=True,
            )

            if submitted:
                errors = []
                if not username:
                    errors.append("Le nom d'utilisateur est requis.")
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
                    final_role = user_type
                    if admin_code:
                        if admin_code == ADMIN_SECRET_CODE:
                            final_role = "admin"
                        else:
                            st.error("❌ Code administrateur invalide.")
                            st.stop()

                    result = register_user(
                        username=username,
                        name=username,  # Pas de colonne 'name' → username
                        password=password,
                        role=final_role,
                    )
                    if result["success"]:
                        role_label = {
                            "admin": "👑 Administrateur",
                            "professeur": "👨‍🏫 Professeur",
                            "eleve": "👨‍🎓 Élève",
                        }.get(final_role, final_role)
                        st.success(
                            f"✅ Compte **{role_label}** créé avec succès ! "
                            f"Vous pouvez maintenant vous connecter."
                        )
                        st.balloons()
                    else:
                        st.error(f"❌ {result['message']}")

        st.markdown("---")
        st.caption("💡 Les mots de passe sont hachés avec bcrypt.")