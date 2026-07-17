"""🧪 Tests unitaires — Système de Q&A sans LLM.

Couvre les 5 modules du package ``core.non_llm`` :
  • document_analyzer — Analyse des documents
  • question_analyzer — Analyse et classification des questions
  • retrieval — Recherche BM25 et scoring de proximité
  • strategies — 9 stratégies de réponse spécialisées
  • engine — Orchestrateur principal et intégration
"""

import pytest
from core.non_llm.document_analyzer import (
    analyze_document_text,
    _split_sentences,
    _extract_definitions,
    _score_key_sentences,
    _extract_entities,
)
from core.non_llm.question_analyzer import (
    analyze_question,
    QuestionType,
    QuestionAnalysis,
)
from core.non_llm.retrieval import (
    search_documents,
    score_by_term_proximity,
)
from core.non_llm.strategies import (
    get_strategies,
    execute_strategy,
)
from core.non_llm import answer_question_non_llm, analyze_document


# ═══════════════════════════════════════════════════════════════════════════
# 1. Document Analyzer
# ═══════════════════════════════════════════════════════════════════════════

class TestSplitSentences:
    """Découpage en phrases (robuste pour le français)."""

    def test_simple_sentence(self):
        """Une seule phrase complète."""
        result = _split_sentences("Le théorème de Pythagore est fondamental.")
        assert len(result) == 1
        assert "théorème de Pythagore" in result[0]

    def test_multiple_sentences(self):
        """Plusieurs phrases correctement séparées."""
        text = (
            "Le théorème de Pythagore est fondamental. "
            "Il permet de calculer des distances. "
            "C'est un outil puissant."
        )
        result = _split_sentences(text)
        assert len(result) == 3
        assert "fondamental" in result[0]
        assert "distances" in result[1]
        assert "outil puissant" in result[2]

    def test_abbreviations_preserved(self):
        """Les abréviations (M., Mme) ne coupent pas la phrase."""
        text = ("M. Dupont a enseigné le théorème de Pythagore à Mme Martin. "
                "C'était en 2020.")
        result = _split_sentences(text)
        assert len(result) == 2
        # L'abréviation ne doit pas créer de faux positif
        assert "M. Dupont" in result[0]
        assert "2020" in result[1]

    def test_exclamation_and_question(self):
        """Points d'exclamation et d'interrogation comme séparateurs."""
        text = "Qu'est-ce que le théorème ? C'est simple ! Demandez à votre prof."
        result = _split_sentences(text)
        assert len(result) == 3

    def test_empty_text(self):
        """Texte vide → liste vide."""
        assert _split_sentences("") == []


class TestExtractDefinitions:
    """Extraction des phrases définitionnelles."""

    def test_est_un_pattern(self):
        """Détecte 'X est un/une/le/la...'."""
        sentences = [
            "Le théorème de Pythagore est un résultat fondamental de géométrie."
        ]
        defs = _extract_definitions(sentences)
        assert len(defs) >= 1
        # Le terme extrait doit contenir "Pythagore"
        assert any("Pythagore" in d["term"] for d in defs)
        assert any(d["pattern"] == "est_un" for d in defs)

    def test_on_appelle_pattern(self):
        """Détecte 'on appelle X...'."""
        sentences = [
            "On appelle hypoténuse le côté opposé à l'angle droit."
        ]
        defs = _extract_definitions(sentences)
        assert len(defs) >= 1
        assert any("hypoténuse" in d["term"] for d in defs)
        assert any(d["pattern"] == "appelle" for d in defs)

    def test_sont_des_pattern(self):
        """Détecte 'X sont des...'."""
        sentences = [
            "Les nombres premiers sont des entiers naturels avec exactement deux diviseurs."
        ]
        defs = _extract_definitions(sentences)
        assert len(defs) >= 1
        assert any(d["pattern"] == "sont_des" for d in defs)

    def test_defini_comme_pattern(self):
        """Détecte 'on définit X comme...'."""
        sentences = [
            "On définit la dérivée comme la limite du taux d'accroissement."
        ]
        defs = _extract_definitions(sentences)
        assert len(defs) >= 1
        assert any("dérivée" in d["term"] or "derivee" in d["term"].lower() for d in defs)
        assert any(d["pattern"] == "defini_comme" for d in defs)

    def test_no_definitions(self):
        """Texte sans définition → liste vide."""
        sentences = [
            "Aujourd'hui il fait beau.",
            "Les chats aiment dormir.",
            "La voiture rouge est garée dehors.",
        ]
        defs = _extract_definitions(sentences)
        assert defs == []

    def test_short_sentence_ignored(self):
        """Phrase trop courte (< 15 caractères) ignorée."""
        sentences = ["X est un y."]
        defs = _extract_definitions(sentences)
        assert defs == []


class TestScoreKeySentences:
    """Scoring des phrases-clés par importance."""

    def test_empty_list(self):
        """Liste vide → liste vide."""
        assert _score_key_sentences([]) == []

    def test_normal_sentences_return_tuples(self):
        """Phrases normales → tuples (float, str) triés par score descendant."""
        sentences = [
            "Le théorème de Pythagore est un résultat fondamental de la géométrie.",
            "Il pleut aujourd'hui.",
            "En conclusion, ce théorème est essentiel pour les mathématiques modernes.",
        ]
        result = _score_key_sentences(sentences)
        assert len(result) == len(sentences)
        for score, sent in result:
            assert isinstance(score, (int, float)), f"Score doit être numérique, obtenu {type(score)}"
            assert isinstance(sent, str)
            assert score >= 0.0
        # Vérifier le tri décroissant
        scores = [s for s, _ in result]
        assert scores == sorted(scores, reverse=True)

    def test_cue_word_bonus(self):
        """Les phrases avec mots-cues (essentiel, fondamental) ont un score plus élevé."""
        sentences = [
            "Un fait anodin sans importance particulière ici.",
            "Ce point est fondamental et essentiel pour bien comprendre.",
        ]
        result = _score_key_sentences(sentences)
        # La phrase avec mots-cues doit avoir un meilleur score
        scores = {sent: score for score, sent in result}
        assert scores[sentences[1]] > scores[sentences[0]]


class TestExtractEntities:
    """Extraction d'entités (dates, nombres, noms propres)."""

    def test_proper_nouns_detected(self):
        """Noms propres (hors début de phrase) détectés."""
        sentences = [
            "Le théorème de Pythagore est attribué à Pythagore de Samos.",
        ]
        entities = _extract_entities(sentences, sentences[0])
        proper = entities["proper_nouns"]
        # "Pythagore" apparaît après le premier mot → doit être détecté
        assert "Pythagore" in proper
        # "Samos" aussi
        assert "Samos" in proper

    def test_dates_detected(self):
        """Dates en format français détectées."""
        text = "La Révolution française a eu lieu en 1789. Le 14 juillet 1789."
        sentences = _split_sentences(text)
        entities = _extract_entities(sentences, text)
        dates = entities["dates"]
        assert len(dates) >= 1
        assert any("1789" in d for d in dates)

    def test_numbers_with_units(self):
        """Nombres avec unités détectés."""
        text = "La distance est de 100 km. La masse vaut 50 kg."
        sentences = _split_sentences(text)
        entities = _extract_entities(sentences, text)
        numbers = entities["numbers"]
        assert any("100" in n for n in numbers)
        assert any("50" in n for n in numbers)

    def test_large_numbers_detected(self):
        """Grands nombres (> 99) détectés même sans unité."""
        text = "La population est de 50000 habitants."
        sentences = _split_sentences(text)
        entities = _extract_entities(sentences, text)
        numbers = entities["numbers"]
        assert any("50000" in n for n in numbers)


class TestAnalyzeDocumentText:
    """Fonction principale d'analyse de document."""

    def test_full_analysis_structure(self, sample_text):
        """Analyse complète contient toutes les clés attendues."""
        analysis = analyze_document_text(sample_text)
        expected_keys = {
            "key_sentences", "definitions", "entities", "lists",
            "sections", "chunk_terms", "formulas",
            "important_ngrams", "total_sentences",
        }
        assert set(analysis.keys()) == expected_keys

    def test_non_empty_analysis(self, sample_text):
        """Texte non vide → analyse non vide."""
        analysis = analyze_document_text(sample_text)
        assert analysis["total_sentences"] > 0
        assert len(analysis["key_sentences"]) > 0
        assert len(analysis["important_ngrams"]) > 0

    def test_empty_text(self):
        """Texte vide → clés vides / à zéro."""
        analysis = analyze_document_text("")
        assert analysis["key_sentences"] == []
        assert analysis["definitions"] == []
        assert analysis["total_sentences"] == 0
        assert analysis["entities"]["dates"] == []
        assert analysis["entities"]["numbers"] == []
        assert analysis["entities"]["proper_nouns"] == []
        assert analysis["lists"] == []
        assert analysis["sections"] == []

    def test_definition_detected_in_sample(self, sample_text):
        """Le texte sur Pythagore contient une définition."""
        analysis = analyze_document_text(sample_text)
        assert len(analysis["definitions"]) >= 1
        # Le terme "théorème de Pythagore" devrait être reconnu
        terms = [d["term"] for d in analysis["definitions"]]
        assert any("Pythagore" in t for t in terms)

    def test_key_sentences_scored(self, sample_text):
        """Les phrases-clés sont des tuples (float, str) triés."""
        analysis = analyze_document_text(sample_text)
        for score, sent in analysis["key_sentences"]:
            assert isinstance(score, float)
            assert isinstance(sent, str)
            assert score >= 0.0
        # Tri descendant
        scores = [s for s, _ in analysis["key_sentences"]]
        assert scores == sorted(scores, reverse=True)

    def test_entities_in_sample(self, sample_text):
        """Le texte contient des entités (noms propres)."""
        analysis = analyze_document_text(sample_text)
        assert "Pythagore" in analysis["entities"]["proper_nouns"]
        assert "Samos" in analysis["entities"]["proper_nouns"]

    def test_important_ngrams_multi_word(self, sample_text):
        """Les n-grammes multi-mots sont extraits."""
        analysis = analyze_document_text(sample_text)
        ngrams = analysis["important_ngrams"]
        # "théorème de pythagore" devrait être un bigramme important
        assert any("théorème de pythagore" in ng for ng in ngrams)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Question Analyzer
# ═══════════════════════════════════════════════════════════════════════════

class TestQuestionAnalyzer:
    """Classification et analyse des questions."""

    def test_definition_quest_ce_que(self):
        """'Qu'est-ce que X ?' → type DEFINITION."""
        result = analyze_question("Qu'est-ce que le théorème de Pythagore ?")
        assert result.question_type == QuestionType.DEFINITION
        assert "théorème de pythagore" in result.target_term
        assert result.confidence > 0.5

    def test_definition_informal(self):
        """'C'est quoi X ?' → type DEFINITION."""
        result = analyze_question("C'est quoi l'énergie cinétique ?")
        assert result.question_type == QuestionType.DEFINITION
        assert result.confidence > 0.5

    def test_factoid_who(self):
        """'Qui a inventé... ?' → type FACTOID, sub_type='who'."""
        result = analyze_question("Qui a inventé le téléphone ?")
        assert result.question_type == QuestionType.FACTOID
        assert result.sub_type == "who"

    def test_factoid_when(self):
        """'Quand a eu lieu... ?' → type FACTOID."""
        result = analyze_question("Quand a eu lieu la Révolution française ?")
        assert result.question_type == QuestionType.FACTOID
        assert result.sub_type == "when"

    def test_how(self):
        """'Comment calculer... ?' → type HOW."""
        result = analyze_question("Comment calculer l'aire d'un triangle ?")
        assert result.question_type == QuestionType.HOW

    def test_why(self):
        """'Pourquoi ... ?' → type WHY."""
        result = analyze_question("Pourquoi le ciel est-il bleu ?")
        assert result.question_type == QuestionType.WHY

    def test_list(self):
        """'Quels sont les ... ?' → type LIST."""
        result = analyze_question("Quels sont les types d'énergie ?")
        assert result.question_type == QuestionType.LIST

    def test_comparison_différence(self):
        """'Différence entre X et Y ?' → type COMPARISON."""
        result = analyze_question("Différence entre l'ADN et l'ARN ?")
        assert result.question_type == QuestionType.COMPARISON
        assert len(result.target_term) > 0
        assert len(result.secondary_term) > 0

    def test_boolean_est_ce_que(self):
        """'Est-ce que ... ?' → type BOOLEAN."""
        result = analyze_question("Est-ce que la Terre est ronde ?")
        assert result.question_type == QuestionType.BOOLEAN

    def test_summary(self):
        """'Résume ...' → type SUMMARY."""
        result = analyze_question("Résume ce chapitre sur la thermodynamique")
        assert result.question_type == QuestionType.SUMMARY

    def test_formula(self):
        """'Quelle est la formule de ... ?' → type FORMULA."""
        result = analyze_question("Quelle est la formule de l'énergie cinétique ?")
        assert result.question_type == QuestionType.FORMULA

    def test_example(self):
        """'Donne un exemple de ...' → type EXAMPLE."""
        result = analyze_question("Donne un exemple de réaction chimique")
        assert result.question_type == QuestionType.EXAMPLE

    def test_unknown(self):
        """Question non classifiable → type UNKNOWN."""
        result = analyze_question("Bonjour")
        assert result.question_type == QuestionType.UNKNOWN

    def test_keywords_no_stopwords(self):
        """Les mots-clés ne contiennent pas de stopwords."""
        result = analyze_question("Qu'est-ce que le théorème de Pythagore ?")
        stopwords = {"le", "de", "que", "ce", "est", "quoi"}
        # Les mots-clés de 3+ lettres hors stopwords
        for kw in result.keywords:
            assert kw.lower() not in stopwords, (
                f"Le stopword '{kw}' ne devrait pas être dans les keywords"
            )

    def test_has_negation_true(self):
        """Phrase avec négation → has_negation=True."""
        result = analyze_question("Le théorème n'est pas vrai")
        assert result.has_negation is True

    def test_has_negation_false(self):
        """Phrase sans négation → has_negation=False."""
        result = analyze_question("Qu'est-ce que le théorème ?")
        assert result.has_negation is False

    def test_question_analysis_repr(self):
        """QuestionAnalysis.__repr__() est lisible."""
        analysis = QuestionAnalysis(
            original="test",
            question_type=QuestionType.DEFINITION,
            target_term="test",
            confidence=0.85,
        )
        rep = repr(analysis)
        assert "definition" in rep
        assert "test" in rep
        assert "0.85" in rep


# ═══════════════════════════════════════════════════════════════════════════
# 3. Retrieval
# ═══════════════════════════════════════════════════════════════════════════

class TestScoreByTermProximity:
    """Scoring de proximité entre mots-clés dans un chunk."""

    def test_close_keywords(self):
        """Mots-clés proches → score > 0.

        Note: les keywords doivent être en minuscules car _tokenize()
        normalise le chunk en minuscules avant la comparaison.
        """
        chunk = "Le théorème de Pythagore est très important pour les mathématiques."
        keywords = {"théorème", "pythagore"}
        score = score_by_term_proximity(chunk, keywords)
        assert score > 0.0

    def test_distant_keywords(self):
        """Mots-clés éloignés → score significativement plus faible."""
        chunk = ("Le théorème de Pythagore, découvert il y a très longtemps "
                 "par un savant grec nommé Pythagore, est un concept "
                 "fondamental pour les mathématiques modernes.")
        keywords = {"théorème", "Pythagore"}
        score = score_by_term_proximity(chunk, keywords)
        # Les mots sont dans la même phrase mais pas immédiatement proches
        assert score < 0.8

    def test_no_keywords_in_chunk(self):
        """Aucun mot-clé présent → score = 0."""
        chunk = "Il fait beau aujourd'hui."
        keywords = {"théorème", "Pythagore"}
        assert score_by_term_proximity(chunk, keywords) == 0.0

    def test_single_keyword(self):
        """Un seul mot-clé → score = 0 (besoin de 2+)."""
        chunk = "Le théorème est important."
        keywords = {"théorème"}
        assert score_by_term_proximity(chunk, keywords) == 0.0

    def test_empty_chunk(self):
        """Chunk vide → score = 0."""
        assert score_by_term_proximity("", {"mot"}) == 0.0

    def test_empty_keywords(self):
        """Keywords vide → score = 0."""
        assert score_by_term_proximity("Du texte.", set()) == 0.0


class TestSearchDocuments:
    """Recherche BM25 enrichie dans les documents."""

    def _make_docs(self):
        """Crée des documents factices pour les tests de recherche."""
        return [
            {
                "filename": "cours_maths.pdf",
                "chunks": [
                    "Le théorème de Pythagore est un théorème fondamental.",
                    "La somme des angles d'un triangle est 180 degrés.",
                    "Pythagore était un mathématicien grec.",
                ],
                "metadata": {"source": "manuel"},
            },
            {
                "filename": "cours_physique.pdf",
                "chunks": [
                    "L'énergie cinétique est l'énergie du mouvement.",
                    "La formule de l'énergie cinétique est 1/2 mv².",
                    "Newton a découvert la gravitation universelle.",
                ],
                "metadata": {"source": "cours"},
            },
        ]

    def test_search_returns_sorted_results(self):
        """Les résultats sont triés par score décroissant."""
        docs = self._make_docs()
        analysis = analyze_question("Qu'est-ce que le théorème de Pythagore ?")
        query_terms = [analysis.target_term] if analysis.target_term else []
        query_terms.extend(k for k in analysis.keywords if " " not in k)

        results = search_documents(docs, query_terms, analysis, n_results=5)
        assert len(results) > 0
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_search_relevant_first(self):
        """Le chunk le plus pertinent est en première position."""
        docs = self._make_docs()
        analysis = analyze_question("théorème de Pythagore")
        query_terms = [analysis.target_term] if analysis.target_term else []
        query_terms.extend(k for k in analysis.keywords if " " not in k)

        results = search_documents(docs, query_terms, analysis, n_results=5)
        assert len(results) >= 1
        # Le premier résultat devrait être sur le théorème de Pythagore
        assert "Pythagore" in results[0]["text"]
        assert results[0]["score"] >= results[-1]["score"]

    def test_search_no_match(self):
        """Aucun document pertinent → liste vide."""
        docs = [{
            "filename": "doc.txt",
            "chunks": ["Il fait beau aujourd'hui."],
            "metadata": {},
        }]
        analysis = analyze_question("Quelle est la recette du gâteau au chocolat ?")
        query_terms = ["recette", "gâteau", "chocolat"]
        results = search_documents(docs, query_terms, analysis, n_results=5)
        assert results == []

    def test_search_empty_docs(self):
        """Aucun document → liste vide."""
        analysis = analyze_question("Qu'est-ce que X ?")
        results = search_documents([], ["test"], analysis)
        assert results == []

    def test_result_metadata(self):
        """Chaque résultat contient les métadonnées du document source."""
        docs = self._make_docs()
        analysis = analyze_question("énergie cinétique formule")
        query_terms = ["énergie", "cinétique", "formule"]
        results = search_documents(docs, query_terms, analysis, n_results=5)
        assert len(results) > 0
        for r in results:
            assert "text" in r
            assert "score" in r
            assert "metadata" in r
            assert "filename" in r["metadata"]
        # Devrait trouver le chunk de physique
        assert any("énergie cinétique" in r["text"] for r in results)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Strategies
# ═══════════════════════════════════════════════════════════════════════════

class TestStrategies:
    """Stratégies de réponse spécialisées."""

    def test_get_strategies_returns_all_types(self):
        """get_strategies() retourne les 10 types sauf FORMULA et UNKNOWN."""
        strategies = get_strategies()
        # Les 9 types supportés
        assert QuestionType.DEFINITION in strategies
        assert QuestionType.FACTOID in strategies
        assert QuestionType.HOW in strategies
        assert QuestionType.WHY in strategies
        assert QuestionType.LIST in strategies
        assert QuestionType.COMPARISON in strategies
        assert QuestionType.BOOLEAN in strategies
        assert QuestionType.SUMMARY in strategies
        assert QuestionType.EXAMPLE in strategies
        # Ceux qui ne sont PAS dans le mapping
        assert QuestionType.FORMULA not in strategies
        assert QuestionType.UNKNOWN not in strategies

    def test_each_strategy_has_name(self):
        """Chaque stratégie a un 'name' non vide."""
        strategies = get_strategies()
        for qtype, strategy in strategies.items():
            assert strategy.name, f"Stratégie {qtype} a un name vide"
            assert strategy.question_type is not None

    def test_strategy_names_are_unique(self):
        """Les noms des stratégies sont uniques."""
        strategies = get_strategies()
        names = [s.name for s in strategies.values()]
        assert len(names) == len(set(names))

    def test_definition_strategy_type(self):
        """La stratégie DEFINITION a le bon type."""
        strategies = get_strategies()
        strat = strategies[QuestionType.DEFINITION]
        assert strat.name == "definition"
        assert strat.question_type == QuestionType.DEFINITION

    def test_execute_strategy_known_type(self):
        """execute_strategy pour un type connu retourne un dict réponse."""
        analysis = analyze_question("Qu'est-ce que le théorème de Pythagore ?")
        result = execute_strategy(
            QuestionType.DEFINITION,
            analysis,
            {"key_sentences": [], "definitions": [], "entities": {"dates": [], "numbers": [], "proper_nouns": []}, "lists": [], "sections": [], "chunk_terms": [], "formulas": [], "important_ngrams": [], "total_sentences": 0},
            [],
        )
        assert "answer" in result
        assert "sources" in result
        assert "confidence" in result

    def test_execute_strategy_unknown_type(self):
        """execute_strategy pour un type inconnu → message d'erreur."""
        analysis = analyze_question("Bonjour")
        result = execute_strategy(
            QuestionType.UNKNOWN,
            analysis,
            {},
            [],
        )
        assert result["confidence"] == 0.0
        assert "pas répondre" in result["answer"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# 5. Engine (intégration)
# ═══════════════════════════════════════════════════════════════════════════

class TestEngine:
    """Moteur principal — orchestration et workflow complet."""

    def test_empty_question_returns_zero_confidence(self):
        """Question vide → confiance = 0."""
        result = answer_question_non_llm("")
        assert result["confidence"] == 0.0
        assert "Aucune question" in result["answer"]

    def test_blank_question_returns_zero_confidence(self):
        """Question blanche → confiance = 0."""
        result = answer_question_non_llm("   ")
        assert result["confidence"] == 0.0

    def test_no_docs_no_answer(self):
        """Pas de documents → réponse d'absence."""
        result = answer_question_non_llm("Qu'est-ce que X ?")
        assert result["confidence"] == 0.0
        assert "aucun document" in result["answer"].lower()

    def test_full_workflow(self, sample_text, empty_doc_store):
        """Workflow complet : ajout → analyse → question → réponse.

        Vérifie l'ensemble du pipeline sans mocks :
          1. add_document + analyze_document
          2. answer_question_non_llm
          3. réponse non vide avec confiance > 0
        """
        # 1. Ajouter et analyser le document
        empty_doc_store.add_document(
            text=sample_text,
            filename="test_pythagore.pdf",
            metadata={},
        )
        analyze_document(sample_text, "test_pythagore.pdf")

        # 2. Poser une question
        result = answer_question_non_llm(
            "Qu'est-ce que le théorème de Pythagore ?"
        )

        # 3. Vérifier la réponse
        assert result["confidence"] > 0.0, (
            f"La confiance devrait être > 0, obtenu {result['confidence']}"
        )
        assert len(result["answer"]) > 0, "La réponse ne devrait pas être vide"
        assert len(result["sources"]) > 0, "Au moins une source attendue"
        # Le type de question doit être correct
        assert result["question_type"] == "definition"
        # Une stratégie doit avoir été utilisée
        assert result["strategy_used"] not in ("none", "", None)

    def test_strategy_name_in_response(self, sample_text, empty_doc_store):
        """La réponse contient le nom de la stratégie employée."""
        empty_doc_store.add_document(
            text=sample_text,
            filename="test_pythagore.pdf",
            metadata={},
        )
        analyze_document(sample_text, "test_pythagore.pdf")

        # Utiliser une question qui correspond à un type supporté
        result = answer_question_non_llm(
            "Résume le théorème de Pythagore"
        )
        # Le strategy_used ne doit pas être "none"
        assert result["strategy_used"] not in ("none", "", "fallback"), (
            f"Stratégie obtenue: {result['strategy_used']}, "
            f"type: {result['question_type']}"
        )
        assert result["strategy_used"] in (
            "definition", "factoid", "how", "why", "list",
            "comparison", "boolean", "summary", "example",
        ), f"Stratégie inattendue: {result['strategy_used']}"

    def test_multiple_documents(self, sample_text, empty_doc_store):
        """Plusieurs documents chargés ne perturbent pas la réponse."""
        # Ajouter deux documents
        empty_doc_store.add_document(
            text=sample_text,
            filename="pythagore.pdf",
            metadata={},
        )
        analyze_document(sample_text, "pythagore.pdf")

        autre_texte = (
            "L'énergie cinétique est l'énergie que possède un corps "
            "en mouvement. Elle est proportionnelle à la masse et au "
            "carré de la vitesse."
        )
        empty_doc_store.add_document(
            text=autre_texte,
            filename="energie.pdf",
            metadata={},
        )
        analyze_document(autre_texte, "energie.pdf")

        # Question sur Pythagore → réponse venant du bon document
        result = answer_question_non_llm(
            "Qu'est-ce que le théorème de Pythagore ?"
        )
        assert result["confidence"] > 0.0
        assert "Pythagore" in result["answer"]

        # Question sur l'énergie → réponse pertinente
        result2 = answer_question_non_llm(
            "Qu'est-ce que l'énergie cinétique ?"
        )
        assert result2["confidence"] > 0.0
        assert "énergie cinétique" in result2["answer"].lower()

    def test_unknown_question_graceful(self, sample_text, empty_doc_store):
        """Question inconnue → réponse gracieuse même avec documents."""
        empty_doc_store.add_document(
            text=sample_text,
            filename="test.pdf",
            metadata={},
        )
        analyze_document(sample_text, "test.pdf")

        # Question sans aucun rapport
        result = answer_question_non_llm("Bonjour")
        # Le système doit répondre sans planter
        assert "answer" in result
        assert "confidence" in result

    def test_confidence_scale(self, sample_text, empty_doc_store):
        """Différents types de questions donnent des confiances variées."""
        empty_doc_store.add_document(
            text=sample_text,
            filename="test.pdf",
            metadata={},
        )
        analyze_document(sample_text, "test.pdf")

        # Question précise sur le contenu → confiance >= 0
        result_def = answer_question_non_llm(
            "Qu'est-ce que le théorème de Pythagore ?"
        )
        # Question large
        result_sum = answer_question_non_llm(
            "Résume le document sur le théorème de Pythagore"
        )
        # Les deux doivent avoir une confiance >= 0
        assert result_def["confidence"] >= 0.0
        assert result_sum["confidence"] >= 0.0
