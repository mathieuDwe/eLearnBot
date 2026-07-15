"""👑 Page Administrateur — Gestion des utilisateurs et des cours."""

import streamlit as st
from datetime import datetime

from core.auth import (
    require_role,
    get_current_user,
    logout_user,
    get_all_users,
    delete_user,
    update_user_role,
    count_users,
    admin_create_user,
    ROLES,
)
from core.rag_pipeline import get_available_documents
from core.vector_store import get_vector_store


def show():
    """Affiche le panneau d'administration."""
    if not require_role("admin"):
        st.error("⛔ Accès réservé aux administrateurs.")
        return

    user = get_current_user()

    # ── Barre supérieure : titre + déconnexion ───────────────────────────
    col_titre, col_deco = st.columns([5, 1])
    with col_titre:
        st.title("👑 Panneau d'Administration")
    with col_deco:
        if st.button("🚪 Déconnexion", use_container_width=True):
            logout_user()
            st.rerun()

    st.markdown(
        f"Bienvenue **{user['name']}**. "
        "Gérez les utilisateurs et les cours de la plateforme."
    )

    # ── Onglets ─────────────────────────────────────────────────────────
    tab1, tab2, tab3 = st.tabs([
        "📊 Tableau de bord",
        "👥 Utilisateurs",
        "📚 Cours",
    ])

    # ── Onglet 1 : Dashboard ────────────────────────────────────────────
    with tab1:
        st.subheader("📊 Statistiques de la plateforme")

        user_counts = count_users()
        documents = get_available_documents()

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("👥 Total utilisateurs", user_counts["total"])
        col2.metric(
            "👑 Administrateurs",
            user_counts["admin"],
            help="Comptes avec accès au panneau admin",
        )
        col3.metric(
            "👨‍🏫 Professeurs",
            user_counts["professeur"],
        )
        col4.metric(
            "👨‍🎓 Élèves",
            user_counts["eleve"],
        )

        col_a, col_b = st.columns(2)
        col_a.metric("📚 Cours indexés", len(documents))
        col_b.metric(
            "📝 Total chunks",
            sum(d.get("chunks", 0) for d in documents),
        )

        st.markdown("---")
        st.caption(f"Dernière mise à jour : {datetime.now().strftime('%H:%M:%S')}")

        if st.button("🔄 Rafraîchir les stats", use_container_width=True):
            st.rerun()

    # ── Onglet 2 : Utilisateurs ─────────────────────────────────────────
    with tab2:
        st.subheader("👥 Gestion des utilisateurs")

        # ── Formulaire d'ajout ────────────────────────────────────
        with st.expander("➕ Ajouter un utilisateur", expanded=False):
            with st.form("add_user_form", clear_on_submit=True):
                col_a1, col_a2 = st.columns(2)
                new_username = col_a1.text_input(
                    "Nom d'utilisateur *", placeholder="ex: jean.dupont"
                )
                col_b1, col_b2 = st.columns(2)
                new_password = col_b1.text_input(
                    "Mot de passe *",
                    type="password",
                    placeholder="Au moins 6 caractères",
                )
                new_role = col_b2.selectbox(
                    "Rôle *", options=ROLES, index=2
                )
                submitted = st.form_submit_button(
                    "✅ Créer l'utilisateur",
                    use_container_width=True,
                    type="primary",
                )

                if submitted:
                    if not new_username or not new_password:
                        st.error("Tous les champs sont requis.")
                    else:
                        result = admin_create_user(
                            username=new_username.strip(),
                            name=new_username.strip(),  # username sert de nom
                            password=new_password,
                            role=new_role,
                        )
                        if result["success"]:
                            st.success(
                                f"✅ Utilisateur {new_username} ({new_role}) créé avec succès !"
                            )
                            st.rerun()
                        else:
                            st.error(result["message"])

        users = get_all_users()

        if not users:
            st.info("📭 Aucun utilisateur.")
        else:
            # En-tête du tableau
            cols = st.columns([3, 2, 1.5, 1, 1])
            cols[0].markdown("**Utilisateur**")
            cols[1].markdown("**Identifiant**")
            cols[2].markdown("**Rôle**")
            cols[3].markdown("**Inscription**")
            cols[4].markdown("**Actions**")
            st.divider()

            for u in users:
                col1, col2, col3, col4, col5 = st.columns([3, 2, 1.5, 1, 1])

                # Icône selon rôle
                icon = {
                    "admin": "👑",
                    "professeur": "👨‍🏫",
                    "eleve": "👨‍🎓",
                }.get(u["role"], "👤")
                col1.markdown(f"{icon} `{u['username']}`")

                col2.markdown(f"`{u['username']}`")

                # Sélecteur de rôle
                current_role = u["role"]
                role_idx = ROLES.index(current_role) if current_role in ROLES else 0
                new_role = col3.selectbox(
                    "Rôle",
                    ROLES,
                    index=role_idx,
                    key=f"role_{u['username']}",
                    label_visibility="collapsed",
                )
                if new_role != current_role:
                    result = update_user_role(u["username"], new_role)
                    if result["success"]:
                        st.success(result["message"])
                        st.rerun()

                # Date d'inscription
                created = u.get("created_at", "")[:10]
                col4.markdown(created)

                # Bouton supprimer
                if u["username"] != user["username"]:  # Ne pas pouvoir se supprimer soi-même
                    if col5.button(
                        "🗑️",
                        key=f"del_{u['username']}",
                        help=f"Supprimer {u['username']}",
                    ):
                        result = delete_user(u["username"])
                        if result["success"]:
                            st.success(result["message"])
                            st.rerun()
                        else:
                            st.error(result["message"])
                else:
                    col5.markdown("—")

            st.divider()
            st.caption(
                f"Total : **{len(users)}** utilisateur(s) "
                f"| 👑 {user_counts['admin']} admin(s) "
                f"| 👨‍🏫 {user_counts['professeur']} prof(s) "
                f"| 👨‍🎓 {user_counts['eleve']} élève(s)"
            )

    # ── Onglet 3 : Cours ────────────────────────────────────────────────
    with tab3:
        st.subheader("📚 Gestion des cours indexés")

        documents = get_available_documents()

        if not documents:
            st.info("📭 Aucun cours indexé pour le moment.")
        else:
            for doc in documents:
                meta = doc.get("metadata", {})
                content_type = meta.get("content_type", "pdf")
                icon = "🎬" if content_type == "mp4" else "📄"

                with st.container(border=True):
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        st.markdown(f"**{icon} {doc['filename']}**")
                        info = f"🔢 {doc['chunks']} passages"
                        if content_type == "mp4":
                            duration = meta.get("duration_display", "")
                            if duration:
                                info += f" | 🎬 {duration}"
                        st.caption(info)
                    with col2:
                        if content_type == "mp4":
                            st.markdown("🎬 Vidéo")
                        else:
                            st.markdown("📄 PDF")
                    with col3:
                        if st.button(
                            "🗑️ Supprimer",
                            key=f"admin_del_{doc['filename']}",
                            use_container_width=True,
                        ):
                            # Supprimer de ChromeDB
                            deleted = get_vector_store().delete_document(
                                doc["filename"]
                            )
                            # Supprimer de Supabase Storage
                            try:
                                from integrations.supabase_storage import SupabaseStorage
                                storage = SupabaseStorage()
                                storage.delete_file(doc["filename"])
                                st.success(f"✅ {deleted} passages supprimés + fichier effacé du cloud.")
                            except Exception as e:
                                st.success(f"✅ {deleted} passages supprimés (cloud: {e}).")
                            st.rerun()

            st.divider()
            st.caption(f"Total : **{len(documents)}** cours indexés")

    # ── Footer ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.caption(
        "👑 Panneau d'administration eLearnBot — "
        "Seuls les administrateurs ont accès à cette page."
    )