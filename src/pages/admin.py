"""👑 Page Administrateur — Gestion des utilisateurs et des cours."""

import streamlit as st
from datetime import datetime

from core.auth import (
    require_role,
    get_current_user,
    get_all_users,
    delete_user,
    update_user_role,
    count_users,
    admin_create_user,
    ROLES,
)
from core.rag_pipeline import get_available_documents
from core.document_store import delete_document as delete_doc_store
from core.reindexer import (
    check_sync_status,
    reindex_all,
    reindex_file,
    format_sync_summary,
)


def show():
    """Affiche le panneau d'administration."""
    if not require_role("admin"):
        st.error("⛔ Accès réservé aux administrateurs.")
        return

    user = get_current_user()
    st.title("👑 Panneau d'Administration")
    st.markdown(
        f"Bienvenue **{user['name']}**. "
        "Gérez les utilisateurs et les cours de la plateforme."
    )

    # ── Onglets ─────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Tableau de bord",
        "👥 Utilisateurs",
        "📚 Cours",
        "🔄 Synchronisation",
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
                content_hash = doc.get("content_hash") or meta.get("content_hash", "")

                with st.container(border=True):
                    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                    with col1:
                        st.markdown(f"**{icon} {doc['filename']}**")
                        info = f"🔢 {doc['chunks']} passages"
                        if content_type == "mp4":
                            duration = meta.get("duration_display", "")
                            if duration:
                                info += f" | 🎬 {duration}"
                        if content_hash:
                            info += f" | 🧬 `{content_hash[:10]}...`"
                        st.caption(info)
                    with col2:
                        if content_type == "mp4":
                            st.markdown("🎬 Vidéo")
                        else:
                            st.markdown("📄 PDF")
                    with col3:
                        if content_hash:
                            st.markdown("✅ Versionné")
                        else:
                            st.markdown("⚠️ Non versionné")
                    with col4:
                        if st.button(
                            "🗑️ Supprimer",
                            key=f"admin_del_{doc['filename']}",
                            use_container_width=True,
                        ):
                            deleted = delete_doc_store(doc["filename"])
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

    # ── Onglet 4 : Synchronisation ───────────────────────────────────────
    with tab4:
        st.subheader("🔄 Synchronisation cloud ↔ index local")
        st.markdown(
            "Tous les fichiers présents dans Supabase Storage sont "
            "**automatiquement ré-indexés** sans action manuelle. "
            "Cette page vous donne la visibilité sur l'opération."
        )

        # ── Ré-indexation automatique (une fois par session) ─────────────
        if "_auto_reindex_admin" not in st.session_state:
            st.session_state._auto_reindex_admin = True
            status = check_sync_status()
            if status["new_files"] or status["modified_files"]:
                with st.spinner("🔄 Synchronisation automatique avec Supabase..."):
                    report = reindex_all()
                if report["total_processed"] > 0:
                    n_new = len(report.get("indexed", []))
                    n_upd = len(report.get("updated", []))
                    n_err = len(report.get("errors", []))
                    if n_new:
                        st.toast(f"📥 {n_new} nouveau(x) fichier(s) indexé(s) depuis Supabase")
                    if n_upd:
                        st.toast(f"🔄 {n_upd} fichier(s) mis à jour")
                    if n_err:
                        st.toast(f"❌ {n_err} erreur(s) lors de la synchronisation")
                st.rerun()

        # ── Statut actuel ────────────────────────────────────────────────
        status = check_sync_status()

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("☁️ Fichiers Supabase", status["total_in_supabase"])
        col2.metric("📚 Indexés localement", status["total_indexed"])
        diff = status["total_in_supabase"] - status["total_indexed"]
        delta_color = "inverse" if diff > 0 else "normal"
        col3.metric("📥 Non indexés", max(0, diff), delta_color=delta_color)
        col4.metric("✅ Synchronisés", len(status["synced_files"]))

        st.markdown("---")

        # ── Nouveaux fichiers ────────────────────────────────────────────
        with st.expander(
            f"🆕 Nouveaux fichiers ({len(status['new_files'])})",
            expanded=False,
        ):
            if not status["new_files"]:
                st.success("✅ Aucun nouveau fichier à indexer")
            else:
                for f in status["new_files"]:
                    size_kb = f.get("size", 0) / 1024
                    st.markdown(
                        f"- **{f['name']}** ({size_kb:.1f} Ko) "
                        f"— mis à jour : {str(f.get('updated_at', '?'))[:19]}"
                    )

        # ── Fichiers modifiés ────────────────────────────────────────────
        with st.expander(
            f"🔄 Fichiers modifiés ({len(status['modified_files'])})",
            expanded=False,
        ):
            if not status["modified_files"]:
                st.success("✅ Aucun fichier modifié")
            else:
                for f in status["modified_files"]:
                    st.markdown(
                        f"- **{f['name']}** — "
                        f"ancien hash: `{f['old_hash'][:12]}...` "
                        f"→ nouveau: `{f['new_hash'][:12]}...`"
                    )

        # ── Fichiers manquants ───────────────────────────────────────────
        with st.expander(
            f"🗑️ Fichiers manquants ({len(status['missing_files'])})",
        ):
            if not status["missing_files"]:
                st.success("✅ Aucun fichier manquant dans Supabase")
            else:
                st.warning(
                    "Ces fichiers sont dans l'index local mais n'existent "
                    "plus dans Supabase Storage."
                )
                for fname in status["missing_files"]:
                    col_a, col_b = st.columns([3, 1])
                    with col_a:
                        st.markdown(f"- **{fname}**")
                    with col_b:
                        if st.button(
                            "🗑️ Supprimer de l'index",
                            key=f"del_missing_{fname}",
                            use_container_width=True,
                        ):
                            delete_doc_store(fname)
                            st.success(f"✅ {fname} supprimé de l'index")
                            st.rerun()

        # ── Forcer une ré-indexation complète (action manuelle avancée) ──
        with st.expander("🔧 Actions avancées", expanded=False):
            st.warning(
                "En temps normal, la synchronisation est automatique. "
                "Utilisez ces actions uniquement en cas de besoin."
            )
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button(
                    "🔄 Re-vérifier maintenant",
                    use_container_width=True,
                ):
                    st.rerun()
            with col_b:
                if st.button(
                    "📥 Ré-indexation complète de tous les fichiers",
                    use_container_width=True,
                    help="Télécharge et ré-indexe tous les fichiers depuis Supabase",
                ):
                    storage_files = []
                    try:
                        from integrations.supabase_storage import SupabaseStorage
                        s = SupabaseStorage()
                        storage_files = [
                            f["name"] for f in s.list_files()
                            if f["name"].lower().endswith((".pdf", ".mp4"))
                        ]
                    except Exception:
                        st.error("Impossible de lister Supabase")

                    if storage_files:
                        with st.spinner(
                            f"Ré-indexation de {len(storage_files)} fichier(s)..."
                        ):
                            report = reindex_all(storage_files)
                        st.success(
                            f"✅ {report['total_success']} fichier(s) traités, "
                            f"{report['total_errors']} erreur(s)"
                        )
                        st.rerun()

        st.caption(f"Dernière vérification : {status['last_checked'][:19]} UTC")

    # ── Footer ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.caption(
        "👑 Panneau d'administration eLearnBot — "
        "Seuls les administrateurs ont accès à cette page."
    )