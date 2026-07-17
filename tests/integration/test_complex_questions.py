"""Tests de questions complexes — Systeme de Q&A sans LLM.

Ce fichier teste le moteur de questions-reponses sans LLM d'eLearnBot
sur des cas complexes : questions multi-parties, inter-documents,
avec négation, ambiguës, très longues, formulaires, comparaisons
multi-points, et validation de l'échelle de confiance.

Les cinq corpus de test (maths, physique, chimie, biologie, histoire)
couvrent un large eventail de types de contenu : definitions explicites,
formules, listes, entites nommees, dates, comparaisons implicites,
structures multi-sections.

Chaque test est indépendant grace a la fixture ``reset_document_store``
(autouse dans ``conftest.py``) qui reinitialise le store entre chaque test.
"""

import pytest

from core.non_llm import answer_question_non_llm, analyze_document


# ── Helpers ──────────────────────────────────────────────────────────────────

def _add_and_analyze(doc_store, text, filename):
    """Ajoute un document et l'analyse en une seule operation."""
    doc_store.add_document(text=text, filename=filename, metadata={})
    analyze_document(text, filename)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Corpus de test — 5 documents longs et riches
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def maths_text():
    """Cours de maths : Pythagore, Thalès, trigonométrie.

    Contient 3 definitions, formules, listes, sections.
    Ajout de connecteurs causaux pour les tests WHY.
    """
    return (
        "Chapitre 1 : Le théorème de Pythagore\n\n"
        "Le théorème de Pythagore est un théorème fondamental de la géométrie "
        "euclidienne. Il etablit une relation entre les longueurs des cotes "
        "d'un triangle rectangle. "
        "La formule du théorème de Pythagore est : a² + b² = c², ou c represente "
        "la longueur de l'hypoténuse et a, b les longueurs des deux autres cotes. "
        "Ce theoreme est nomme d'après Pythagore de Samos, mathematicien et "
        "philosophe grec du VIe siècle avant J.-C. "
        "L'hypoténuse est le cote oppose a l'angle droit dans un triangle rectangle. "
        "Par exemple, si un triangle rectangle a des cotes de longueur 3 cm et 4 cm, "
        "alors l'hypoténuse mesure 5 cm car 3² + 4² = 9 + 16 = 25 = 5². "
        "Ce theoreme permet de calculer la distance entre deux points dans un plan. "
        "Il existe plusieurs centaines de démonstrations de ce theoreme, "
        "ce qui lui confere une place unique dans l'histoire des mathematiques. "
        "Les proprietes du triangle rectangle sont essentielles pour comprendre "
        "ce theoreme. En effet, un triangle rectangle possède un angle droit "
        "de 90 degres, et les deux autres angles sont aigus et complémentaires. "
        "Le théorème de Pythagore est important en géométrie car il permet de "
        "calculer des distances et de résoudre de nombreux problèmes pratiques.\n\n"
        # ── Section 2 ──
        "Chapitre 2 : Le théorème de Thalès\n\n"
        "Le théorème de Thalès est un autre théorème fondamental de la géométrie. "
        "Il stipule que dans un triangle, une droite parallèle a un cote "
        "divise les deux autres cotes en segments proportionnels. "
        "La formule du théorème de Thalès s'écrit : si M est sur AB, N est sur AC, "
        "et MN est parallèle a BC, alors AM/AB = AN/AC = MN/BC. "
        "Ce theoreme est attribue a Thalès de Milet, philosophe et mathematicien "
        "grec du VIIe-VIe siècle avant J.-C. "
        "Le théorème de Thalès permet de calculer des longueurs inaccessibles, "
        "comme la hauteur d'une pyramide ou la largeur d'une riviere. "
        "La réciproque du théorème de Thalès permet de prouver que deux droites "
        "sont parallèles. "
        "Contrairement au théorème de Thalès qui traite des parallèles, "
        "le théorème de Pythagore est specifique aux triangles rectangles "
        "et relie les longueurs de leurs cotes.\n\n"
        # ── Section 3 ──
        "Chapitre 3 : La trigonométrie dans le triangle rectangle\n\n"
        "La trigonométrie est la branche des mathematiques qui etudie les "
        "relations entre les angles et les cotes des triangles. "
        "Dans un triangle rectangle, on definit trois rapports trigonométriques "
        "fondamentaux. "
        "Le sinus d'un angle aigu est le rapport entre la longueur du cote "
        "oppose a cet angle et la longueur de l'hypoténuse. "
        "Le cosinus d'un angle aigu est le rapport entre la longueur du cote "
        "adjacent a cet angle et la longueur de l'hypoténuse. "
        "La tangente d'un angle aigu est le rapport entre le sinus et le cosinus "
        "de cet angle, ou de facon equivalente le rapport entre le cote oppose "
        "et le cote adjacent. "
        "La formule fondamentale de la trigonométrie est : sin²(θ) + cos²(θ) = 1. "
        "Voici les proprietes principales de la trigonométrie :\n"
        "- Le sinus et le cosinus sont compris entre -1 et 1\n"
        "- La tangente peut prendre n'importe quelle valeur reelle\n"
        "- Les angles sont mesures en degres ou en radians\n"
        "- Le sinus et le cosinus sont des fonctions periodiques de période 2π\n\n"
        "Les applications de la trigonométrie sont nombreuses : navigation, "
        "architecture, astronomie, musique, et bien d'autres domaines."
    )


@pytest.fixture
def physique_text():
    """Cours de physique : énergie cinétique, gravitation."""
    return (
        "Chapitre 1 : L'énergie cinétique\n\n"
        "L'énergie cinétique est l'énergie que possède un corps en mouvement. "
        "Elle dépend de la masse et de la vitesse du corps. "
        "La formule de l'énergie cinétique est : Ec = 1/2 × m × v², "
        "ou m est la masse en kilogrammes et v est la vitesse en mètres par seconde. "
        "L'unité de l'énergie cinétique est le joule (J). "
        "Par exemple, une voiture de 1000 kg roulant a 20 m/s possède une énergie "
        "cinétique de 200 000 joules. "
        "L'énergie cinétique est proportionnelle a la masse et au carre de la vitesse. "
        "Cela signifie que si la vitesse double, l'énergie cinétique est multipliee "
        "par quatre car elle dépend du carre de la vitesse. "
        "L'énergie cinétique est une grandeur scalaire, elle n'a pas de direction. "
        "Dans un systeme isolé, l'énergie cinétique peut etre convertie en "
        "énergie potentielle et vice versa, conformement au principe de "
        "conservation de l'énergie.\n\n"
        "Chapitre 2 : La gravitation universelle\n\n"
        "La gravitation universelle est une loi physique découverte par Isaac Newton "
        "au XVIIe siècle. "
        "La loi de la gravitation universelle stipule que deux corps massifs "
        "s'attirent avec une force proportionnelle au produit de leurs masses "
        "et inversement proportionnelle au carre de la distance qui les separe. "
        "La formule de la gravitation est : F = G × (m₁ × m₂) / d², "
        "ou G est la constante gravitationnelle valant environ 6,67 × 10⁻¹¹ N·m²/kg². "
        "Cette force d'attraction est toujours attractive et s'exerce a distance. "
        "La gravitation est responsable de la chute des corps sur Terre, "
        "du mouvement des planetes autour du Soleil, et de la formation des galaxies. "
        "Newton a formule cette loi après avoir observe la chute d'une pomme. "
        "La théorie de la relativite générale d'Albert Einstein a plus tard "
        "affine notre comprehension de la gravitation.\n\n"
        "Contrairement a l'énergie cinétique qui dépend du mouvement, "
        "l'énergie potentielle dépend de la position d'un corps dans un champ "
        "de force, comme le champ gravitationnel. "
        "L'énergie mécanique totale d'un systeme est la somme de son énergie "
        "cinétique et de son énergie potentielle."
    )


@pytest.fixture
def chimie_text():
    """Cours de chimie : atomes, molécules, liaisons, réactions."""
    return (
        "Chapitre 1 : Les atomes et les molécules\n\n"
        "Un atome est la plus petite unité de matière qui conserve les proprietes "
        "chimiques d'un element. "
        "Un atome est compose d'un noyau contenant des protons et des neutrons, "
        "autour duquel gravitent des électrons. "
        "Le numero atomique est le nombre de protons dans le noyau. "
        "Une molécule est un assemblage de deux ou plusieurs atomes lies entre eux "
        "par des liaisons chimiques. "
        "Par exemple, la molécule d'eau (H₂O) est composee de deux atomes "
        "d'hydrogène et d'un atome d'oxygène. "
        "Le dioxyde de carbone (CO₂) est une molécule composee d'un atome de "
        "carbone et de deux atomes d'oxygène.\n\n"
        "Chapitre 2 : Les liaisons chimiques\n\n"
        "Il existe plusieurs types de liaisons chimiques. "
        "Une liaison covalente est une liaison chimique dans laquelle deux atomes "
        "mettent en commun un ou plusieurs électrons de leur couche externe. "
        "Une liaison ionique est une liaison chimique dans laquelle un atome "
        "donne un ou plusieurs électrons a un autre atome, creant ainsi des ions "
        "de charges opposees qui s'attirent. "
        "La difference entre une liaison covalente et une liaison ionique "
        "reside dans le partage ou le transfert d'électrons. "
        "Les liaisons covalentes sont généralement plus fortes que les liaisons "
        "ioniques. "
        "Les composes covalents sont souvent des gaz ou des liquides a température "
        "ambiante, tandis que les composes ioniques sont généralement des solides "
        "cristallins.\n\n"
        "Chapitre 3 : Les réactions chimiques\n\n"
        "Une réaction chimique est une transformation au cours de laquelle "
        "des substances chimiques (les reactifs) se transformént en de nouvelles "
        "substances (les produits). "
        "Les réactions chimiques sont décrites par des equations chimiques. "
        "Par exemple, la combustion du methane s'écrit : "
        "CH₄ + 2 O₂ → CO₂ + 2 H₂O. "
        "Dans une réaction chimique, la masse totale est conservee : "
        "c'est la loi de conservation de la masse. "
        "Les principaux types de réactions chimiques sont :\n"
        "- Les réactions de synthese (A + B → AB)\n"
        "- Les réactions de decomposition (AB → A + B)\n"
        "- Les réactions de précipitation\n"
        "- Les réactions acide-base\n"
        "- Les réactions d'oxydoréduction\n\n"
        "Les catalyseurs sont des substances qui accélèrent une réaction chimique "
        "sans etre consommées par celle-ci."
    )


@pytest.fixture
def biologie_text():
    """Cours de biologie : photosynthèse, respiration, ADN/ARN."""
    return (
        "Chapitre 1 : La photosynthèse\n\n"
        "La photosynthèse est le processus par lequel les plantes vertes, "
        "les algues et certaines bacteries convertissent l'énergie lumineuse "
        "en énergie chimique. "
        "L'équation chimique de la photosynthèse est : "
        "6 CO₂ + 6 H₂O → C₆H₁₂O₆ + 6 O₂. "
        "Ce processus se déroule dans les chloroplastes des cellules vegetales, "
        "grace a la chlorophylle, un pigment vert qui absorbe la lumiere. "
        "La photosynthèse est essentielle a la vie sur Terre car elle produit "
        "le dioxygène que nous respirons et constitue la base de la chaîne "
        "alimentaire. "
        "La photosynthèse se décompose en deux phases principales : "
        "la phase claire (dépendante de la lumiere) et le cycle de Calvin "
        "(indépendant de la lumiere).\n\n"
        "Chapitre 2 : La respiration cellulaire\n\n"
        "La respiration cellulaire est le processus par lequel les cellules "
        "degradent des molécules organiques pour produire de l'énergie sous "
        "forme d'ATP. "
        "L'équation chimique de la respiration cellulaire est : "
        "C₆H₁₂O₆ + 6 O₂ → 6 CO₂ + 6 H₂O + énergie (ATP). "
        "La respiration cellulaire se déroule dans les mitochondries des cellules. "
        "On peut remarquer que la respiration cellulaire est l'inverse de la "
        "photosynthèse. "
        "La respiration cellulaire comprend trois étapes principales : "
        "la glycolyse, le cycle de Krebs, et la chaîne respiratoire.\n\n"
        "Chapitre 3 : L'ADN et l'ARN\n\n"
        "L'ADN (acide désoxyribonucléique) est une macromolécule qui contient "
        "l'information génétique de tous les etres vivants. "
        "L'ARN (acide ribonucléique) est une macromolécule qui joue un role "
        "cle dans la synthese des protéines. "
        "La difference entre l'ADN et l'ARN est multiple. "
        "L'ADN est une molécule a double brin tandis que l'ARN est "
        "généralement une molécule a simple brin. "
        "Le sucre present dans l'ADN est le désoxyribose, tandis que celui "
        "de l'ARN est le ribose. "
        "Les bases azotees de l'ADN sont l'adenine (A), la thymine (T), "
        "la guanine (G) et la cytosine (C). "
        "Dans l'ARN, la thymine est remplacee par l'uracile (U). "
        "L'ADN est localisé dans le noyau des cellules eucaryotes, tandis que "
        "l'ARN peut se trouver dans le noyau et le cytoplasme. "
        "Ces differences structurelles entre ADN et ARN determinent leurs "
        "fonctions respectives dans la cellule."
    )


@pytest.fixture
def histoire_text():
    """Cours d'histoire : Révolution française (causes, dates, personnages)."""
    return (
        "Chapitre 1 : Les causes de la Révolution française\n\n"
        "La Révolution française est une période majeure de l'histoire de France "
        "qui a debute en 1789 et a profondément transformé la société française. "
        "Les causes de la Révolution française sont multiples et complexes. "
        "Parmi les causes principales, on trouve :\n"
        "- Les inégalités sociales entre les trois ordres (noblesse, clerge, tiers etat)\n"
        "- La crise financière de l'Ancien Regime due aux dépenses excessives "
        "de la monarchie et aux guerres\n"
        "- Les mauvaises recoites et la hausse du prix du pain\n"
        "- L'influence des idees des Lumières portees par des philosophes "
        "comme Voltaire, Rousseau et Montesquieu\n"
        "- Le refus de la noblesse de payer des impots\n\n"
        "Le roi Louis XVI a convoqué les États généraux en mai 1789 pour "
        "tenter de résoudre la crise financière. "
        "Le tiers etat, qui representait 98% de la population, s'est proclamé "
        "Assemblée nationale le 17 juin 1789, marquant le debut de la Révolution. "
        "La Révolution a eu lieu parce que les inégalités sociales étaient "
        "trop fortes et que le peuple souffrait de la crise economique.\n\n"
        "Chapitre 2 : Les événements cles de la Révolution\n\n"
        "Le 14 juillet 1789, les Parisiens prennent la Bastille, symbole de "
        "l'absolutisme royal. "
        "Le 4 aout 1789, l'Assemblée nationale abolit les privilèges "
        "féodaux et le systeme seigneurial. "
        "La Declaration des Droits de l'Homme et du Citoyen est adoptee "
        "le 26 aout 1789. "
        "En octobre 1789, le peuple de Paris marche sur Versailles et "
        "ramene le roi Louis XVI a Paris. "
        "La monarchie constitutionnelle est instaurée en 1791 avec la "
        "Constitution de 1791. "
        "Le 10 aout 1792, la monarchie est renversée et la Première République "
        "est proclamée le 21 septembre 1792. "
        "Le roi Louis XVI est exécuté le 21 janvier 1793.\n\n"
        "Chapitre 3 : Les personnages importants\n\n"
        "Plusieurs personnages ont marque la Révolution française. "
        "Maximilien de Robespierre était le leader des Jacobins et une figure "
        "centrale de la Terreur. "
        "Georges Danton était un avocat et révolutionnaire influent. "
        "Jean-Paul Marat était un journaliste et depute radical. "
        "Olympe de Gouges, femme de lettres, a redige la Declaration des "
        "droits de la femme et de la citoyenne. "
        "Le Marquis de Lafayette était un general et homme politique qui "
        "a participe a la fois a la Révolution americaine et française. "
        "Napoleon Bonaparte a pris le pouvoir par le coup d'Etat du "
        "18 brumaire (9 novembre 1799), mettant fin a la Révolution française."
    )


@pytest.fixture
def all_docs(empty_doc_store, maths_text, physique_text, chimie_text,
             biologie_text, histoire_text):
    """Ajoute les 5 documents dans le store et les analyse."""
    _add_and_analyze(empty_doc_store, maths_text, "maths.pdf")
    _add_and_analyze(empty_doc_store, physique_text, "physique.pdf")
    _add_and_analyze(empty_doc_store, chimie_text, "chimie.pdf")
    _add_and_analyze(empty_doc_store, biologie_text, "biologie.pdf")
    _add_and_analyze(empty_doc_store, histoire_text, "histoire.pdf")
    return empty_doc_store


# ═══════════════════════════════════════════════════════════════════════════════
# A. Questions multi-parties (synthese de plusieurs concepts)
# ═══════════════════════════════════════════════════════════════════════════════

class TestQuestionsMultiParties:
    """Questions qui necessitent la synthese de plusieurs concepts."""

    def test_question_comparaison_pythagore_thalès(self, maths_text, empty_doc_store):
        """Question COMPARISON entre deux theoremes (Pythagore vs Thalès).

        Le texte contient une phrase de comparaison explicite entre les deux.
        """
        _add_and_analyze(empty_doc_store, maths_text, "maths.pdf")
        result = answer_question_non_llm(
            "Différence entre le théorème de Pythagore et le théorème de Thalès"
        )
        assert result["confidence"] > 0.0, (
            f"Confiance obtenue: {result['confidence']}, reponse: {result['answer'][:100]}"
        )
        assert result["question_type"] == "comparison", (
            f"Type attendu 'comparison', obtenu {result['question_type']}"
        )
        answer_lower = result["answer"].lower()
        assert "pythagore" in answer_lower
        assert "thalès" in answer_lower or "thales" in answer_lower

    def test_question_definition_et_exemple(self, maths_text, empty_doc_store):
        """Question melangeant DEFINITION + conceptualisation d'exemple."""
        _add_and_analyze(empty_doc_store, maths_text, "maths.pdf")
        result = answer_question_non_llm(
            "Explique le théorème de Pythagore et donne un exemple de calcul"
        )
        assert result["confidence"] > 0.0
        assert len(result["answer"]) > 0
        assert any(mot in result["answer"].lower()
                   for mot in ["exemple", "calcul", "3", "4", "5"])

    def test_question_formule_énergie(self, physique_text, empty_doc_store):
        """Question de type FORMULE sur l'énergie cinétique."""
        _add_and_analyze(empty_doc_store, physique_text, "physique.pdf")
        result = answer_question_non_llm(
            "Quelle est la formule de l'énergie cinétique ?"
        )
        assert result["confidence"] > 0.0
        assert result["question_type"] == "formula"
        answer_lower = result["answer"].lower()
        assert any(terme in answer_lower
                   for terme in ["1/2", "mv²", "m × v", "masse", "vitesse"])

    def test_question_comparaison_adn_arn(self, biologie_text, empty_doc_store):
        """Question COMPARISON entre ADN et ARN (dans le meme chapitre)."""
        _add_and_analyze(empty_doc_store, biologie_text, "biologie.pdf")
        result = answer_question_non_llm(
            "Différence entre l'ADN et l'ARN"
        )
        assert result["confidence"] > 0.0, (
            f"Confiance obtenue: {result['confidence']}, type={result['question_type']}"
        )
        assert result["question_type"] == "comparison"
        answer_lower = result["answer"].lower()
        assert "adn" in answer_lower
        assert "arn" in answer_lower

    def test_question_resume_et_dates(self, histoire_text, empty_doc_store):
        """Question melangeant SUMMARY + mention de dates."""
        _add_and_analyze(empty_doc_store, histoire_text, "histoire.pdf")
        result = answer_question_non_llm(
            "Résume les causes de la Révolution française et donne les dates clés"
        )
        assert result["confidence"] > 0.0
        assert len(result["answer"]) > 0
        assert any(mot in result["answer"]
                   for mot in ["1789", "causes", "inégalités", "Bastille", "Révolution"])


# ═══════════════════════════════════════════════════════════════════════════════
# B. Questions avec negation
# ═══════════════════════════════════════════════════════════════════════════════

class TestQuestionsAvecNegation:
    """Questions contenant une negation explicite (ne, pas, n'est pas, etc.)."""

    def test_question_negation_definition(self, maths_text, empty_doc_store):
        """Question DEFINITION avec negation."""
        _add_and_analyze(empty_doc_store, maths_text, "maths.pdf")
        result = answer_question_non_llm(
            "Qu'est-ce qui n'est pas un triangle rectangle ?"
        )
        assert "answer" in result
        assert result["confidence"] >= 0.0

    def test_question_booleenne_negation(self, maths_text, empty_doc_store):
        """Question BOOLEAN avec negation integree."""
        _add_and_analyze(empty_doc_store, maths_text, "maths.pdf")
        result = answer_question_non_llm(
            "Le théorème de Pythagore ne s'applique-t-il pas "
            "aux triangles rectangles ?"
        )
        assert result["confidence"] >= 0.0
        assert len(result["answer"]) > 0

    def test_question_liste_negation(self, chimie_text, empty_doc_store):
        """Question LIST avec negation."""
        _add_and_analyze(empty_doc_store, chimie_text, "chimie.pdf")
        result = answer_question_non_llm(
            "Cite un type de liaison chimique qui n'est pas covalente"
        )
        assert result["confidence"] >= 0.0
        assert len(result["answer"]) > 0

    def test_question_fait_negation(self, physique_text, empty_doc_store):
        """Question FACTOID avec negation."""
        _add_and_analyze(empty_doc_store, physique_text, "physique.pdf")
        result = answer_question_non_llm(
            "Qu'est-ce que l'énergie potentielle n'est pas ?"
        )
        assert result["confidence"] >= 0.0
        assert "answer" in result

    def test_question_negation_aucun(self, histoire_text, empty_doc_store):
        """Question avec negation par 'aucun'."""
        _add_and_analyze(empty_doc_store, histoire_text, "histoire.pdf")
        result = answer_question_non_llm(
            "Aucun philosophe n'a influencé la Révolution française ?"
        )
        assert result["confidence"] >= 0.0
        assert "answer" in result


# ═══════════════════════════════════════════════════════════════════════════════
# C. Questions inter-documents
# ═══════════════════════════════════════════════════════════════════════════════

class TestQuestionsInterDocuments:
    """Questions qui necessitent de croiser plusieurs documents differents."""

    def test_question_lien_physique_biologie(self, all_docs):
        """Question sur deux concepts dans deux documents differents.

        Le systeme doit chercher dans tous les documents disponibles.
        """
        result = answer_question_non_llm(
            "Quel est le lien entre l'énergie cinétique en physique "
            "et la photosynthèse en biologie ?"
        )
        assert result["confidence"] >= 0.0
        assert "answer" in result
        assert len(result["answer"]) > 0

    def test_question_comparaison_multi_docs(self, all_docs):
        """Question COMPARISON entre concepts de deux documents distincts."""
        result = answer_question_non_llm(
            "Compare la respiration cellulaire en biologie "
            "avec une réaction chimique en chimie"
        )
        assert result["confidence"] >= 0.0
        assert len(result["answer"]) > 0

    def test_question_recherche_globale(self, all_docs):
        """Question sur un concept present dans plusieurs documents."""
        result = answer_question_non_llm(
            "Quels documents parlent d'énergie ?"
        )
        assert result["confidence"] >= 0.0
        assert len(result["answer"]) > 0

    def test_question_formule_absente_autres_docs(self, all_docs):
        """Question sur une formule absente de tous les documents."""
        result = answer_question_non_llm(
            "Quelle est la formule de la relativité restreinte ?"
        )
        assert "answer" in result


# ═══════════════════════════════════════════════════════════════════════════════
# D. Questions ambigues / mal formulees
# ═══════════════════════════════════════════════════════════════════════════════

class TestQuestionsAmbiguës:
    """Questions vagues, incompletes ou mal formulees."""

    def test_question_explique_seul(self, all_docs):
        """Seul mot 'Explique' sans contexte."""
        result = answer_question_non_llm("Explique")
        assert result["confidence"] == 0.0
        assert result["question_type"] == "unknown"

    def test_question_pronom_vague(self, all_docs):
        """Pronom vague 'ca' sans cible claire."""
        result = answer_question_non_llm("Parle-moi de ca")
        assert result["confidence"] == 0.0
        assert result["question_type"] == "unknown"

    def test_question_sans_sujet(self, all_docs):
        """'C'est quoi ?' sans sujet."""
        result = answer_question_non_llm("C'est quoi ?")
        assert "answer" in result

    def test_question_formule_seule(self, all_docs):
        """Formule seule 'E = mc²'."""
        result = answer_question_non_llm("E = mc²")
        assert "answer" in result

    def test_question_faute_orthographe(self, all_docs):
        """Question avec faute d'orthographe."""
        result = answer_question_non_llm(
            "Qu'est-ce que le théorème de Pithagore ?"
        )
        assert "answer" in result
        assert result["confidence"] >= 0.0

    def test_question_trop_vague_plusieurs_docs(self, all_docs):
        """Terme vague 'Le theoreme' quand plusieurs docs en parlent."""
        result = answer_question_non_llm("Le theoreme")
        assert "answer" in result
        assert result["confidence"] >= 0.0

    def test_question_point_interrogation_seul(self, all_docs):
        """Seul un point d'interrogation."""
        result = answer_question_non_llm("?")
        assert "answer" in result
        assert result["confidence"] == 0.0

    def test_question_tres_courte(self, all_docs):
        """Question tres courte d'un seul mot."""
        result = answer_question_non_llm("Trigonométrie")
        assert "answer" in result
        assert result["confidence"] >= 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# E. Questions tres longues (paragraphe)
# ═══════════════════════════════════════════════════════════════════════════════

class TestQuestionsTresLongues:
    """Questions longues de plusieurs phrases qui melangent plusieurs sujets."""

    def test_question_paragraphe_multi_sujets(self, all_docs):
        """Question d'un paragraphe melangeant plusieurs sujets."""
        question = (
            "J'aimerais comprendre comment fonctionne la photosynthèse chez les "
            "plantes vertes. Est-ce que ce processus a un lien avec l'énergie "
            "lumineuse ? Par ailleurs, quelle est la difference entre la "
            "photosynthèse et la respiration cellulaire ? Et est-ce que "
            "ces processus sont lies aux réactions chimiques dont on parle "
            "en cours de chimie ?"
        )
        result = answer_question_non_llm(question)
        assert "answer" in result
        assert result["confidence"] >= 0.0
        assert len(result["answer"]) > 0

    def test_question_longue_detaillee(self, all_docs):
        """Question tres longue avec beaucoup de details contextuels."""
        question = (
            "Dans le cadre du cours de mathematiques que nous avons etudie, "
            "je voudrais savoir comment on peut utiliser le théorème de Pythagore "
            "pour calculer la longueur de l'hypoténuse d'un triangle rectangle "
            "quand on connait les deux autres cotes. Est-ce que la formule "
            "a² + b² = c² est toujours valable quel que soit le triangle ? "
            "Et comment fait-on si le triangle n'est pas rectangle ? "
            "Peut-on quand meme utiliser une formule approchee ?"
        )
        result = answer_question_non_llm(question)
        assert "answer" in result
        assert result["confidence"] >= 0.0

    def test_question_longue_sans_ponctuation(self, all_docs):
        """Question tres longue sans ponctuation ni majuscules."""
        question = (
            "je voudrais savoir ce qu'est la photosynthèse et comment "
            "elle fonctionne chez les plantes vertes est-ce que c'est "
            "lie a la chlorophylle et est-ce que ca produit de l'oxygène "
            "quelle est la difference avec la respiration cellulaire "
            "merci de me repondre"
        )
        result = answer_question_non_llm(question)
        assert "answer" in result
        assert result["confidence"] >= 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# F. Questions avec nombres / formules
# ═══════════════════════════════════════════════════════════════════════════════

class TestQuestionsNombresFormules:
    """Questions contenant des nombres, des calculs ou des formules."""

    def test_question_nombre_calcul(self, maths_text, empty_doc_store):
        """Question FACTOID avec un calcul (combien font 3² + 4² ?)."""
        _add_and_analyze(empty_doc_store, maths_text, "maths.pdf")
        result = answer_question_non_llm("Combien font 3² + 4² ?")
        assert result["confidence"] >= 0.0
        assert "answer" in result

    def test_question_hypoténuse(self, maths_text, empty_doc_store):
        """Question sur la valeur de l'hypoténuse avec des cotes donnes."""
        _add_and_analyze(empty_doc_store, maths_text, "maths.pdf")
        result = answer_question_non_llm(
            "Quelle est la valeur de l'hypoténuse si les côtés font 3 et 4 ?"
        )
        assert result["confidence"] > 0.0
        assert "answer" in result

    def test_question_formule_énergie_cinétique(self, physique_text, empty_doc_store):
        """Question FORMULA sur la formule de l'énergie cinétique."""
        _add_and_analyze(empty_doc_store, physique_text, "physique.pdf")
        result = answer_question_non_llm(
            "Quelle est la formule de l'énergie cinétique ?"
        )
        assert result["confidence"] > 0.0
        answer_lower = result["answer"].lower()
        assert any(terme in answer_lower
                   for terme in ["1/2", "mv²", "m × v", "masse", "vitesse"])

    def test_question_formule_trigonométrie(self, maths_text, empty_doc_store):
        """Question FORMULA sur la formule fondamentale de trigonométrie."""
        _add_and_analyze(empty_doc_store, maths_text, "maths.pdf")
        result = answer_question_non_llm(
            "Quelle est la formule fondamentale de la trigonométrie ?"
        )
        assert result["confidence"] > 0.0
        answer_lower = result["answer"].lower()
        assert any(terme in answer_lower
                   for terme in ["sin²", "cos²", "sinus", "cosinus"])

    def test_question_nombre_grand(self, physique_text, empty_doc_store):
        """Question FACTOID avec un grand nombre (200 000 joules)."""
        _add_and_analyze(empty_doc_store, physique_text, "physique.pdf")
        result = answer_question_non_llm(
            "Combien de joules possède une voiture de 1000 kg à 20 m/s ?"
        )
        assert result["confidence"] >= 0.0
        assert "answer" in result


# ═══════════════════════════════════════════════════════════════════════════════
# G. Questions de type 'pourquoi' complexe
# ═══════════════════════════════════════════════════════════════════════════════

class TestQuestionsPourquoiComplexe:
    """Questions WHY qui demandent une explication causale."""

    def test_question_pourquoi_pythagore_important(self, maths_text, empty_doc_store):
        """Question WHY sur l'importance du théorème de Pythagore.

        Le texte contient 'car' dans la phrase sur l'importance.
        """
        _add_and_analyze(empty_doc_store, maths_text, "maths.pdf")
        result = answer_question_non_llm(
            "Pourquoi le théorème de Pythagore est-il important "
            "pour la géométrie ?"
        )
        assert result["confidence"] > 0.0, (
            f"Confiance obtenue: {result['confidence']}, reponse: {result['answer'][:100]}"
        )
        assert result["question_type"] in ("why", "definition", "summary")

    def test_question_pourquoi_énergie_vitesse_carre(self, physique_text,
                                                     empty_doc_store):
        """Question WHY sur la dépendance en v² de l'énergie cinétique."""
        _add_and_analyze(empty_doc_store, physique_text, "physique.pdf")
        result = answer_question_non_llm(
            "Pourquoi l'énergie cinétique dépend-elle de la vitesse "
            "au carré ?"
        )
        assert result["confidence"] > 0.0
        answer_lower = result["answer"].lower()
        assert any(terme in answer_lower
                   for terme in ["carre", "vitesse", "cinétique", "proportionnelle"])

    def test_question_pourquoi_photosynthèse_essentielle(self, biologie_text,
                                                         empty_doc_store):
        """Question WHY sur l'importance de la photosynthèse.

        Le texte contient 'car' explicitement.
        """
        _add_and_analyze(empty_doc_store, biologie_text, "biologie.pdf")
        result = answer_question_non_llm(
            "Explique pourquoi la photosynthèse est essentielle "
            "à la vie sur Terre"
        )
        assert result["confidence"] > 0.0
        answer_lower = result["answer"].lower()
        assert any(terme in answer_lower
                   for terme in ["oxygène", "dioxygène", "vie", "essentielle",
                                 "chaîne", "alimentaire"])

    def test_question_pourquoi_révolution(self, histoire_text, empty_doc_store):
        """Question WHY sur les causes de la Révolution française.

        Le texte contient 'parce que' explicitement.
        """
        _add_and_analyze(empty_doc_store, histoire_text, "histoire.pdf")
        result = answer_question_non_llm(
            "Pourquoi la Révolution française a-t-elle eu lieu ?"
        )
        assert result["confidence"] > 0.0, (
            f"Confiance obtenue: {result['confidence']}, reponse: {result['answer'][:100]}"
        )
        answer_lower = result["answer"].lower()
        assert any(terme in answer_lower
                   for terme in ["cause", "inegalite", "crise", "tiers etat",
                                 "impot", "révolution"])

    def test_question_pourquoi_loi_gravitation(self, physique_text,
                                                empty_doc_store):
        """Question WHY sur la gravitation universelle."""
        _add_and_analyze(empty_doc_store, physique_text, "physique.pdf")
        result = answer_question_non_llm(
            "Pourquoi les planètes tournent-elles autour du Soleil ?"
        )
        assert result["confidence"] >= 0.0
        assert "answer" in result


# ═══════════════════════════════════════════════════════════════════════════════
# H. Questions de comparaison multi-points
# ═══════════════════════════════════════════════════════════════════════════════

class TestQuestionsComparaisonMultiPoints:
    """Questions de comparaison detaillees entre deux concepts."""

    def test_question_comparaison_adn_arn_detaillee(self, biologie_text,
                                                     empty_doc_store):
        """Question COMPARISON detaillee ADN vs ARN."""
        _add_and_analyze(empty_doc_store, biologie_text, "biologie.pdf")
        result = answer_question_non_llm(
            "Compare l'ADN et l'ARN : donne leurs rôles, "
            "structures et différences"
        )
        assert result["confidence"] > 0.0
        answer_lower = result["answer"].lower()
        assert "adn" in answer_lower
        assert "arn" in answer_lower

    def test_question_comparaison_liaisons_chimiques(self, chimie_text,
                                                      empty_doc_store):
        """Question COMPARISON entre liaison covalente et ionique."""
        _add_and_analyze(empty_doc_store, chimie_text, "chimie.pdf")
        result = answer_question_non_llm(
            "Quelle est la différence entre une liaison covalente "
            "et une liaison ionique ?"
        )
        assert result["confidence"] > 0.0
        assert result["question_type"] in ("comparison", "definition", "list")
        answer_lower = result["answer"].lower()
        assert any(terme in answer_lower
                   for terme in ["covalente", "ionique", "partage", "transfert",
                                 "electron"])

    def test_question_comparaison_photosynthèse_respiration(self, biologie_text,
                                                            empty_doc_store):
        """Question COMPARISON entre photosynthèse et respiration.

        Les deux processus sont dans le meme document mais des chapitres
        differents. Le systeme peut ne pas les trouver dans la meme phrase.
        """
        _add_and_analyze(empty_doc_store, biologie_text, "biologie.pdf")
        result = answer_question_non_llm(
            "Différence entre la photosynthèse et la respiration cellulaire"
        )
        assert result["confidence"] >= 0.0
        assert "answer" in result
        # Meme si la confiance est basse, le systeme ne doit pas planter

    def test_question_comparaison_pythagore_trigonométrie(self, maths_text,
                                                          empty_doc_store):
        """Question COMPARISON entre deux concepts de maths."""
        _add_and_analyze(empty_doc_store, maths_text, "maths.pdf")
        result = answer_question_non_llm(
            "Quelle est la différence entre le théorème de Pythagore "
            "et la trigonométrie ?"
        )
        assert result["confidence"] >= 0.0
        assert "answer" in result

    def test_question_comparaison_gravitation_énergie(self, physique_text,
                                                      empty_doc_store):
        """Question COMPARISON entre gravitation et énergie cinétique."""
        _add_and_analyze(empty_doc_store, physique_text, "physique.pdf")
        result = answer_question_non_llm(
            "Différence entre l'énergie cinétique et la gravitation"
        )
        assert result["confidence"] >= 0.0
        assert "answer" in result


# ═══════════════════════════════════════════════════════════════════════════════
# I. Questions de resume sur document entier
# ═══════════════════════════════════════════════════════════════════════════════

class TestQuestionsResume:
    """Questions qui demandent un resume ou une synthese."""

    def test_question_resume_maths(self, maths_text, empty_doc_store):
        """Question SUMMARY sur le cours de mathematiques."""
        _add_and_analyze(empty_doc_store, maths_text, "maths.pdf")
        result = answer_question_non_llm(
            "Résume ce cours de mathématiques en 3 points"
        )
        assert result["confidence"] > 0.0
        assert result["question_type"] == "summary"
        assert len(result["answer"]) > 50
        answer_lower = result["answer"].lower()
        assert any(terme in answer_lower
                   for terme in ["pythagore", "thales", "trigonométrie",
                                 "géométrie", "théorème"])

    def test_question_resume_physique(self, physique_text, empty_doc_store):
        """Question SUMMARY sur les concepts cles de physique."""
        _add_and_analyze(empty_doc_store, physique_text, "physique.pdf")
        result = answer_question_non_llm(
            "Résume le cours de physique"
        )
        assert result["confidence"] > 0.0
        assert len(result["answer"]) > 50
        answer_lower = result["answer"].lower()
        assert any(terme in answer_lower
                   for terme in ["énergie", "cinétique", "gravitation",
                                 "newton", "physique"])

    def test_question_resume_chimie(self, chimie_text, empty_doc_store):
        """Question SUMMARY sur le cours de chimie."""
        _add_and_analyze(empty_doc_store, chimie_text, "chimie.pdf")
        result = answer_question_non_llm(
            "Résume le cours de chimie sur les liaisons chimiques"
        )
        assert result["confidence"] > 0.0
        assert len(result["answer"]) > 30

    def test_question_resume_histoire(self, histoire_text, empty_doc_store):
        """Question SUMMARY sur la Révolution française."""
        _add_and_analyze(empty_doc_store, histoire_text, "histoire.pdf")
        result = answer_question_non_llm(
            "Résume les événements de la Révolution française"
        )
        assert result["confidence"] > 0.0
        answer_lower = result["answer"].lower()
        assert any(terme in answer_lower
                   for terme in ["1789", "bastille", "révolution", "louis"])

    def test_question_resume_biologie(self, biologie_text, empty_doc_store):
        """Question SUMMARY sur le cours de biologie."""
        _add_and_analyze(empty_doc_store, biologie_text, "biologie.pdf")
        result = answer_question_non_llm(
            "Résume le cours de biologie sur les processus cellulaires"
        )
        assert result["confidence"] > 0.0
        assert len(result["answer"]) > 30


# ═══════════════════════════════════════════════════════════════════════════════
# J. Test de l'echelle de confiance
# ═══════════════════════════════════════════════════════════════════════════════

class TestEchelleConfiance:
    """Validation de l'echelle de confiance des reponses."""

    def test_confiance_question_couverte(self, maths_text, empty_doc_store):
        """Question parfaitement couverte par le document."""
        _add_and_analyze(empty_doc_store, maths_text, "maths.pdf")
        result = answer_question_non_llm(
            "Qu'est-ce que le théorème de Pythagore ?"
        )
        assert 0.0 <= result["confidence"] <= 1.0

    def test_confiance_question_partielle(self, all_docs):
        """Question partiellement couverte."""
        result = answer_question_non_llm(
            "Parle-moi de la conservation de l'énergie"
        )
        assert 0.0 <= result["confidence"] <= 1.0
        assert "answer" in result

    def test_confiance_question_hors_sujet(self, all_docs):
        """Question hors-sujet."""
        result = answer_question_non_llm(
            "Quelle est la recette de la tarte aux pommes ?"
        )
        assert 0.0 <= result["confidence"] <= 1.0

    def test_confiance_jamais_negative(self, all_docs):
        """La confiance n'est jamais negative."""
        questions = [
            "Qu'est-ce que l'ADN ?",
            "Comment calculer une distance ?",
            "Pourquoi le ciel est bleu ?",
            "",
            "   ",
            "Blablabla123",
            "Différence entre X et Y",
        ]
        for q in questions:
            result = answer_question_non_llm(q)
            assert result["confidence"] >= 0.0, (
                f"Confiance negative ({result['confidence']}) pour: '{q}'"
            )
            assert result["confidence"] <= 1.0, (
                f"Confiance > 1.0 ({result['confidence']}) pour: '{q}'"
            )

    def test_confiance_jamais_nan(self, all_docs):
        """La confiance n'est jamais NaN ou infinie."""
        import math
        questions = [
            "Qu'est-ce que l'énergie ?",
            "Résume la Révolution française",
            "Compare ADN et ARN",
        ]
        for q in questions:
            result = answer_question_non_llm(q)
            assert not math.isnan(result["confidence"]), f"NaN pour: '{q}'"
            assert not math.isinf(result["confidence"]), f"Infini pour: '{q}'"


# ═══════════════════════════════════════════════════════════════════════════════
# K. Questions avec filtre document_name
# ═══════════════════════════════════════════════════════════════════════════════

class TestQuestionsFiltreDocument:
    """Questions filtrees sur un document specifique."""

    def test_question_filtre_doc_correct(self, all_docs):
        """Filtre sur le bon document."""
        result = answer_question_non_llm(
            "Qu'est-ce que l'énergie cinétique ?",
            document_name="physique.pdf"
        )
        assert result["confidence"] > 0.0
        assert "énergie" in result["answer"].lower() or \
               "énergie" in result["answer"]

    def test_question_filtre_mauvais_doc(self, all_docs):
        """Filtre sur le mauvais document."""
        result = answer_question_non_llm(
            "Qu'est-ce que l'énergie cinétique ?",
            document_name="biologie.pdf"
        )
        assert result["confidence"] == 0.0

    def test_question_filtre_sur_pythagore(self, all_docs):
        """Filtre sur maths.pdf."""
        result = answer_question_non_llm(
            "Qu'est-ce que le théorème de Pythagore ?",
            document_name="maths.pdf"
        )
        assert result["confidence"] > 0.0
        assert "Pythagore" in result["answer"]

    def test_question_filtre_nom_inexistant(self, all_docs):
        """Filtre sur un nom de document inexistant."""
        result = answer_question_non_llm(
            "Qu'est-ce que la photosynthèse ?",
            document_name="fichier_inexistant.pdf"
        )
        assert result["confidence"] == 0.0
        assert "aucun document" in result["answer"].lower()

    def test_question_sans_filtre_trouve_partout(self, all_docs):
        """Sans filtre, le systeme cherche dans tous les documents."""
        result = answer_question_non_llm(
            "Qu'est-ce que l'énergie cinétique ?"
        )
        assert result["confidence"] > 0.0
        assert len(result["sources"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# L. Tests de robustesse et de bordure
# ═══════════════════════════════════════════════════════════════════════════════

class TestRobustesse:
    """Tests de robustesse sur des cas limites."""

    def test_question_sans_document(self):
        """Question posee sans aucun document charge."""
        result = answer_question_non_llm(
            "Qu'est-ce que le théorème de Pythagore ?"
        )
        assert result["confidence"] == 0.0
        assert "aucun document" in result["answer"].lower()

    def test_question_répétée(self, all_docs):
        """Meme question posee deux fois de suite."""
        q = "Qu'est-ce que l'énergie cinétique ?"
        r1 = answer_question_non_llm(q)
        r2 = answer_question_non_llm(q)
        assert r1["confidence"] == r2["confidence"]
        assert r1["question_type"] == r2["question_type"]

    def test_question_multiple_documents_meme_sujet(self, empty_doc_store,
                                                     maths_text, physique_text):
        """Deux documents differents avec le mot 'triangle'."""
        _add_and_analyze(empty_doc_store, maths_text, "maths.pdf")
        _add_and_analyze(empty_doc_store, physique_text, "physique.pdf")

        result = answer_question_non_llm(
            "Qu'est-ce qu'un triangle rectangle ?"
        )
        assert result["confidence"] >= 0.0
        # Le systeme doit trouver une reponse avec au moins des mots de géométrie
        assert len(result["answer"]) > 0

    def test_question_caracteres_speciaux(self, all_docs):
        """Question avec des caracteres speciaux."""
        result = answer_question_non_llm(
            "Énergie cinétique : formule Ec = 1/2 × m × v² ???"
        )
        assert "answer" in result
        assert result["confidence"] >= 0.0

    def test_question_tres_longue_seulement_chiffres(self, all_docs):
        """Question constituee uniquement de chiffres et symboles."""
        result = answer_question_non_llm("12345 67890 1/2 mv² 3²+4²=25")
        assert "answer" in result
        assert result["confidence"] >= 0.0

    def test_question_unicode_emojis(self, all_docs):
        """Question avec des emojis."""
        result = answer_question_non_llm(
            "Qu'est-ce qu'une liaison covalente ?"
        )
        assert "answer" in result
        assert result["confidence"] >= 0.0
        assert "liaison" in result["answer"].lower() or \
               "covalente" in result["answer"].lower()

    def test_question_tous_documents_via_all_docs(self, all_docs):
        """Verifie que les 5 documents sont bien charges via all_docs.

        Pose une question sur chaque document et verifie qu'une reponse
        est obtenue.
        """
        questions = [
            ("Qu'est-ce que le théorème de Pythagore ?", "maths.pdf"),
            ("Définis l'énergie cinétique", "physique.pdf"),
            ("Qu'est-ce qu'une liaison covalente ?", "chimie.pdf"),
            ("Explique la photosynthèse", "biologie.pdf"),
            ("Quand a débuté la Révolution française ?", "histoire.pdf"),
        ]
        for question, _doc_attendu in questions:
            result = answer_question_non_llm(question)
            assert result["confidence"] >= 0.0, (
                f"Pas de reponse pour: '{question}'"
            )
            assert len(result["answer"]) > 0, (
                f"Reponse vide pour: '{question}'"
            )
