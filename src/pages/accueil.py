"""🏠 Page d'accueil — eLearnBot."""

import streamlit as st


def show():
    """Affiche la page d'accueil."""
    # ── En-tête ────────────────────────────────────────────────────────
    st.markdown("<div class='main-header'>", unsafe_allow_html=True)
    st.title("🎓 eLearnBot")
    st.markdown(
        "<p>Transformez vos cours en assistant interactif !</p>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Cartes fonctionnalités ──────────────────────────────────────────
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            """
            <div class='feature-card'>
                <h3>👨‍🏫 Mode Professeur</h3>
                <p>Uploader vos cours PDF, gérer vos documents, 
                et voir comment les élèves interagissent avec le contenu.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class='feature-card'>
                <h3>📄 Upload simplifié</h3>
                <p>Glissez-déposez vos fichiers PDF. 
                Le système les indexe automatiquement.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            """
            <div class='feature-card'>
                <h3>👨‍🎓 Mode Élève</h3>
                <p>Posez des questions en langage naturel sur n'importe 
                quel cours. Obtenez des réponses sourcées.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class='feature-card'>
                <h3>🔍 Réponses sourcées</h3>
                <p>Chaque réponse cite le passage exact du cours, 
                pour une vérification facile.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Boutons d'action rapide ────────────────────────────────────────
    st.markdown("---")
    st.subheader("🚀 Commencer")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("👨‍🏫 Mode Professeur", use_container_width=True):
            st.switch_page("pages/professeur.py")
    with col_b:
        if st.button("👨‍🎓 Mode Élève", use_container_width=True):
            st.switch_page("pages/eleve.py")
    with col_c:
        if st.button("❓ Aide", use_container_width=True):
            st.switch_page("pages/aide.py")

    # ── Statistiques ───────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📊 En un coup d'œil")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("📚 Cours disponibles", "—")
    m2.metric("💬 Questions posées", "—")
    m3.metric("👨‍🎓 Élèves actifs", "—")
    m4.metric("✅ Réponses données", "—")

    st.caption(
        "Les statistiques apparaîtront une fois les premiers cours uploadés."
    )