"""🧠 Stratégies de réponse spécialisées pour le Q&A sans LLM.

Chaque stratégie implémente une méthode de réponse adaptée à un type
de question spécifique (définition, fait, comment, pourquoi, etc.).
Elles exploitent les analyses pré-calculées des documents (phrases-clés,
définitions, entités, listes, sections) pour construire des réponses
précises sans aucun appel LLM.

Architecture
------------
- ``BaseStrategy``   : classe abstraite définissant l'interface commune
- ``*Strategy``      : 9 implémentations concrètes (1 par type de question)
- ``get_strategies()``  : retourne le mapping type → stratégie
- ``execute_strategy()``: dispatche vers la bonne stratégie

Chaque stratégie retourne un dict normalisé ::

    {
        "answer": str,
        "sources": list[str],
        "confidence": float,  # 0.0 – 1.0
    }
"""

import re
from typing import Optional

from .question_analyzer import QuestionType, QuestionAnalysis
from .retrieval import search_documents, batch_retrieve_paragraphs


# ═══════════════════════════════════════════════════════════════════════════
# ── Constantes ────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

# Mots de définition (pour la détection dans les phrases-clés)
_DEFINITION_VERBS = {
    "est", "sont", "désigne", "représente", "appelle",
    "défini", "définit", "signifie", "constitue",
}

# Connecteurs causaux (pour WHY)
_CAUSAL_CONNECTORS = {
    "car", "parce que", "en effet", "donc",
    "par conséquent", "c'est pourquoi", "ainsi",
    "grâce à", "en raison de", "à cause de",
    "étant donné que", "puisque", "du fait que",
}

# Mots de comparaison
_COMPARISON_WORDS = {
    "différence", "différent", "contraire", "cependant",
    "mais", "tandis que", "alors que", "en revanche",
    "d'un côté", "d'autre part", "d'un autre côté",
    "opposé", "similitude", "ressemblance", "commun",
    "analogie", "distinction", "à la différence de",
}

# Mots de séquence / procédure (pour HOW)
_SEQUENCE_WORDS = {
    "d'abord", "ensuite", "enfin", "premièrement",
    "deuxièmement", "troisièmement", "premier", "deuxième",
    "troisième", "étape", "phase", "avant", "après",
    "pour commencer", "pour terminer", "finalement",
    "1.", "2.", "3.", "première étape",
}

# Marqueurs d'exemple
_EXAMPLE_MARKERS = {
    "exemple", "par exemple", "illustration", "cas concret",
    "notamment", "tel que", "telle que", "tels que",
    "telles que", "comme", "à titre d'exemple",
    "exemple concret", "exemple illustratif",
    "pour illustrer", "ceci inclut", "y compris",
    "prenons", "prenons l'exemple", "ainsi",
}

# Mots de localisation (pour FACTOID ‒ where)
_LOCATION_WORDS = {
    "à", "dans", "situé", "trouve", "localisé", "se situe",
    "se trouve", "au", "aux", "sur", "sous", "entre",
    "à côté de", "près de", "loin de",
}

# Nombres ordinaux pour l'extraction d'étapes
_ORDINAL_WORDS = {
    "premièrement", "deuxièmement", "troisièmement",
    "premier", "deuxième", "troisième",
    "1)", "2)", "3)", "a)", "b)", "c)",
    "première étape", "deuxième étape", "troisième étape",
}

# Types de QuestionType acceptant une requête documentaire large
_BROAD_SEARCH_TYPES = {
    QuestionType.SUMMARY,
    QuestionType.HOW,
    QuestionType.WHY,
}


# ═══════════════════════════════════════════════════════════════════════════
# ── Fonctions utilitaires ─────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

def _word_overlap_score(text1: str, text2: str) -> float:
    """Calcule le score de similarité par mots communs (Jaccard).

    Compare les ensembles de mots (tokenisés, minuscules) de deux textes.

    Args:
        text1: Premier texte.
        text2: Second texte.

    Returns:
        Score entre 0.0 (aucun mot commun) et 1.0 (mots identiques).
    """
    words1 = set(_tokenize(text1))
    words2 = set(_tokenize(text2))
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / max(len(union), 1)


def _tokenize(text: str) -> list[str]:
    """Tokenise un texte en mots (minuscules, sans ponctuation).

    Gère les caractères accentués du français.

    Args:
        text: Texte à tokeniser.

    Returns:
        Liste de mots en minuscules.
    """
    return re.findall(
        r"[a-zA-ZéèêëàâîïôûùçÉÈÊËÀÂÎÏÔÛÙÇœŒæÆ0-9]+",
        text.lower(),
    )


def _keyword_match_score(text: str, keywords: set) -> float:
    """Calcule la proportion de mots-clés présents dans le texte.

    Args:
        text: Texte à évaluer.
        keywords: Mots-clés recherchés.

    Returns:
        Score entre 0.0 et 1.0.
    """
    if not keywords:
        return 0.0
    text_lower = text.lower()
    matches = sum(1 for kw in keywords if kw.lower() in text_lower)
    return matches / max(len(keywords), 1)


def _contextual_match_score(
    sentence: str,
    target_term: str,
    keywords: set,
    connector_words: set = None,
) -> float:
    """Score combiné d'une phrase par rapport à une question.

    Prend en compte :
    - Présence du terme cible
    - Présence des mots-clés
    - Bonus pour les mots de liaison / connecteurs

    Args:
        sentence: Phrase à scorer.
        target_term: Terme cible de la question.
        keywords: Mots-clés de la question.
        connector_words: Ensemble optionnel de mots bonus.

    Returns:
        Score composite.
    """
    sent_lower = sentence.lower()
    score = 0.0

    # Présence du terme cible
    if target_term and target_term.lower() in sent_lower:
        score += 0.5
        # Bonus si le terme cible apparaît tôt dans la phrase
        target_pos = sent_lower.index(target_term.lower())
        if target_pos < len(sent_lower) * 0.3:
            score += 0.1

    # Mots-clés additionnels
    if keywords:
        kw_score = _keyword_match_score(sentence, keywords)
        score += kw_score * 0.3

    # Connecteurs / mots de liaison
    if connector_words:
        sent_words = set(sent_lower.split())
        has_connector = any(
            conn in sent_lower for conn in connector_words
        )
        if has_connector:
            score += 0.2

    return score


def _extract_sentences(text: str) -> list[str]:
    """Découpe un texte en phrases (robuste pour le français).

    Gère les abréviations courantes et la ponctuation.

    Args:
        text: Texte à découper.

    Returns:
        Liste de phrases nettoyées.
    """
    if not text:
        return []

    # Protéger les abréviations courantes
    text = re.sub(
        r'\b(M|Mme|Mlles|Dr|Pr|St|Ste|M\.|ex|fig|cf)\.',
        r'\1<ABBR>',
        text,
    )
    # Protéger les nombres décimaux
    text = re.sub(r'(\d+)\.(\d+)', r'\1<DEC>\2', text)

    raw = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"\'«(])', text)

    result = []
    for s in raw:
        s = s.replace('<ABBR>', '.')
        s = s.replace('<DEC>', '.')
        s = s.strip()
        if s and len(s) > 5:
            result.append(s)

    return result


def _find_sentences_with_keywords(
    text: str,
    keywords: set,
    min_score: float = 0.0,
) -> list[tuple[float, str]]:
    """Trouve les phrases contenant le plus de mots-clés.

    Args:
        text: Texte dans lequel chercher.
        keywords: Mots-clés à rechercher.
        min_score: Score minimum pour retenir une phrase.

    Returns:
        Liste de tuples (score, phrase) triée par score décroissant.
    """
    if not text or not keywords:
        return []
    sentences = _extract_sentences(text)
    scored = []
    for sent in sentences:
        score = _keyword_match_score(sent, keywords)
        if score >= min_score:
            scored.append((score, sent))
    scored.sort(key=lambda x: -x[0])
    return scored


def _get_doc_text(doc: dict) -> str:
    """Extrait le texte d'un document depuis le champ approprié.

    Essaie plusieurs noms de champ courants.

    Args:
        doc: Document.

    Returns:
        Texte du document (chaîne vide si aucun champ trouvé).
    """
    for key in ("text", "content", "page_content", "chunk"):
        value = doc.get(key)
        if value and isinstance(value, str):
            return value
    return ""


def _find_in_docs(
    docs: list[dict],
    keywords: set,
    min_score: float = 0.0,
) -> list[tuple[float, str, str]]:
    """Recherche des phrases pertinentes dans tous les documents.

    Args:
        docs: Liste de documents.
        keywords: Mots-clés à rechercher.
        min_score: Score minimum.

    Returns:
        Liste de tuples (score, phrase, source) triée par score décroissant.
    """
    results: list[tuple[float, str, str]] = []
    for doc in docs:
        text = _get_doc_text(doc)
        source = (
            doc.get("filename")
            or doc.get("source")
            or doc.get("id")
            or doc.get("title")
            or ""
        )
        for score, sent in _find_sentences_with_keywords(text, keywords, min_score):
            results.append((score, sent, source))
    results.sort(key=lambda x: -x[0])
    return results


def _get_definition_text(def_item: dict) -> str:
    """Extrait le texte de définition d'un item de définition.

    Args:
        def_item: Item de définition (dict avec 'definition', 'def', ou 'text').

    Returns:
        Texte de la définition.
    """
    return (
        def_item.get("definition")
        or def_item.get("def")
        or def_item.get("text")
        or ""
    )


def _normalize_term(term: str) -> str:
    """Normalise un terme pour la recherche (singulier, minuscules).

    Applique une règle de singulier simple pour le français :
    - Supprime le 's' final (pluriel)
    - 'aux' → 'al'

    Args:
        term: Terme à normaliser.

    Returns:
        Terme normalisé.
    """
    term = term.lower().strip()
    if term.endswith("aux") and len(term) > 4:
        term = term[:-2] + "al"
    elif term.endswith("s") and not term.endswith("ss") and len(term) > 3:
        term = term[:-1]
    return term


def _contains_enumeration(sentence: str) -> bool:
    """Vérifie si une phrase contient une énumération.

    Détecte :
    - Puces (-, *, •)
    - Numérotation (1., 2., etc.)
    - Lettres (a), b), etc.)
    - Mots ordinaux (premièrement, ensuite, enfin)

    Args:
        sentence: Phrase à analyser.

    Returns:
        True si la phrase semble être une énumération.
    """
    # Puces et numéros en début de ligne/paragraphe
    if re.match(r'^\s*[-*•]\s', sentence):
        return True
    if re.match(r'^\s*\d+[.)]\s', sentence):
        return True
    if re.match(r'^\s*[a-z][)]\s', sentence):
        return True
    # Mots de séquence
    sent_lower = sentence.lower().strip()
    for word in _ORDINAL_WORDS:
        if sent_lower.startswith(word):
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
# ── Classe de base ────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

class BaseStrategy:
    """Classe de base pour toutes les stratégies de réponse.

    Chaque stratégie spécialisée hérite de cette classe et implémente
    la méthode ``answer()`` qui produit une réponse structurée à partir
    de l'analyse du document et de la question.

    Attributes:
        name: Identifiant lisible de la stratégie.
        question_type: Type(s) de question géré(s) par cette stratégie.
    """

    name: str = ""
    question_type: QuestionType | list[QuestionType] = []

    def answer(
        self,
        question: QuestionAnalysis,
        analysis: dict,
        docs: list[dict],
    ) -> dict:
        """Produit une réponse à la question posée.

        Args:
            question: Analyse structurée de la question.
            analysis: Analyse pré-calculée du document principal
                      (cf. ``document_analyzer.analyze_document_text``).
            docs: Liste de documents bruts (texte + métadonnées).

        Returns:
            Dictionnaire normalisé avec les clés :
            - ``answer``     : texte de la réponse.
            - ``sources``    : liste des sources / citations utilisées.
            - ``confidence`` : score de confiance entre 0.0 et 1.0.
        """
        raise NotImplementedError(
            f"La stratégie '{self.name}' n'a pas implémenté answer()"
        )

    def _build_response(
        self,
        answer: str,
        sources: list[str],
        confidence: float,
    ) -> dict:
        """Construit une réponse normalisée avec tous les champs requis.

        Args:
            answer: Texte de la réponse.
            sources: Citations ou références ayant servi à la réponse.
            confidence: Score de confiance (0.0 – 1.0).

        Returns:
            Dict de réponse formaté.
        """
        return {
            "answer": answer,
            "sources": sources,
            "confidence": max(0.0, min(1.0, confidence)),
        }

    def _empty_response(self, message: str) -> dict:
        """Génère une réponse négative (aucune information trouvée).

        Args:
            message: Message d'absence de résultat.

        Returns:
            Dict de réponse avec confiance à 0.0.
        """
        return self._build_response(message, [], 0.0)


# ═══════════════════════════════════════════════════════════════════════════
# ── 1. Définition ─────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

class DefinitionStrategy(BaseStrategy):
    """Répond aux questions de définition (*Qu'est-ce que X ?*).

    Stratégie :
    1. Parcourt ``analysis['definitions']`` et calcule un score de
       similarité textuelle entre le ``target_term`` et chaque terme.
    2. Si aucun match satisfaisant, cherche dans les ``key_sentences``
       des phrases contenant des verbes définitionnels (*est*, *désigne*…).
    3. Fallback : retourne la phrase-clé la mieux scorée contenant le
       ``target_term``, puis cherche dans les documents bruts.
    """

    name = "definition"
    question_type = QuestionType.DEFINITION

    def answer(
        self,
        question: QuestionAnalysis,
        analysis: dict,
        docs: list[dict],
    ) -> dict:
        target = question.target_term
        keywords = question.keywords

        if not target:
            return self._empty_response(
                "Je n'ai pas compris ce que vous voulez définir. "
                "Pouvez-vous reformuler ?"
            )

        # ── Étape 1 : Chercher dans les définitions structurées ──────
        best_def = self._find_best_definition(
            analysis.get("definitions", []), target, keywords
        )

        if best_def:
            answer_text = _get_definition_text(best_def)
            return self._build_response(answer_text, [answer_text], 0.85)

        # ── Étape 2 : Chercher dans les key_sentences avec patrons de déf. ──
        def_sent = self._find_definition_sentence(
            analysis.get("key_sentences", []), target
        )

        if def_sent:
            return self._build_response(def_sent, [def_sent], 0.65)

        # ── Étape 3 : Fallback — key_sentences contenant le target ──
        for score, sent in analysis.get("key_sentences", []):
            if target.lower() in sent.lower():
                confidence = max(0.3, min(score * 0.6, 0.6))
                return self._build_response(sent, [sent], confidence)

        # ── Étape 4 : Chercher dans les documents bruts ─────────────
        doc_match = self._search_in_docs(docs, target)
        if doc_match:
            return self._build_response(doc_match, [doc_match], 0.25)

        return self._empty_response(
            f"Je n'ai pas trouvé de définition de « {target} » "
            f"dans les documents disponibles."
        )

    def _find_best_definition(
        self,
        definitions: list[dict],
        target: str,
        keywords: set,
    ) -> Optional[dict]:
        """Cherche la meilleure définition pour le terme cible.

        Score basé sur :
        - Similarité textuelle entre le terme de la définition et le target
        - Bonus si target est contenu dans le terme de définition
        - Bonus si la définition contient des mots-clés de la question

        Args:
            definitions: Liste des définitions extraites.
            target: Terme cible de la question.
            keywords: Mots-clés de la question.

        Returns:
            Meilleure définition trouvée, ou None.
        """
        best_def = None
        best_score = 0.0
        target_norm = _normalize_term(target)

        for def_item in definitions:
            term = def_item.get("term", "")
            if not term:
                continue

            term_norm = _normalize_term(term)
            score = _word_overlap_score(term_norm, target_norm)

            # Bonus si le target est une sous-chaîne du terme ou vice versa
            if target_norm in term_norm or term_norm in target_norm:
                score += 0.3

            # Bonus si la définition contient des mots-clés
            def_text = _get_definition_text(def_item)
            if keywords and def_text:
                score += _keyword_match_score(def_text, keywords) * 0.2

            if score > best_score:
                best_score = score
                best_def = def_item

        # Seuil minimal pour considérer la définition comme valide
        if best_score >= 0.25:
            return best_def
        return None

    def _find_definition_sentence(
        self,
        key_sentences: list[tuple[float, str]],
        target: str,
    ) -> Optional[str]:
        """Cherche une phrase à caractère définitionnel.

        Parcourt les phrases-clés et repère celles qui :
        1. Contiennent le terme cible
        2. Contiennent un verbe définitionnel (*est un*, *désigne*…)

        Args:
            key_sentences: Liste de tuples (score, phrase).
            target: Terme cible.

        Returns:
            La meilleure phrase définitionnelle, ou None.
        """
        candidates: list[tuple[float, str]] = []

        for score, sent in key_sentences:
            sent_lower = sent.lower()

            if target.lower() not in sent_lower:
                continue

            # Vérifier la présence d'un verbe définitionnel
            has_def_verb = any(
                re.search(rf"\b{re.escape(v)}\b", sent_lower)
                for v in _DEFINITION_VERBS
            )
            # Vérifier les patterns "X est un/une/le/la"
            has_pattern = bool(
                re.search(
                    rf"\b{re.escape(target.lower())}\s+est\s+(un|une|le|la|les)",
                    sent_lower,
                )
            )

            if has_pattern:
                candidates.append((score + 0.4, sent))
            elif has_def_verb:
                candidates.append((score + 0.2, sent))

        if not candidates:
            return None

        candidates.sort(key=lambda x: -x[0])
        return candidates[0][1]

    def _search_in_docs(self, docs: list[dict], target: str) -> Optional[str]:
        """Recherche une phrase pertinente dans les documents bruts.

        Args:
            docs: Liste des documents.
            target: Terme cible.

        Returns:
            La meilleure phrase trouvée, ou None.
        """
        if not target:
            return None

        for doc in docs:
            text = _get_doc_text(doc)
            if target.lower() in text.lower():
                sentences = _extract_sentences(text)
                for sent in sentences:
                    if target.lower() in sent.lower():
                        return sent
        return None


# ═══════════════════════════════════════════════════════════════════════════
# ── 2. Factoid ────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

class FactoidStrategy(BaseStrategy):
    """Répond aux questions factuelles (*Qui ?*, *Quand ?*, *Où ?*, *Combien ?*).

    Stratégie basée sur le sous-type (``sub_type``) :
    - **who**     : cherche dans ``entities['proper_nouns']`` + contexte
    - **when**    : cherche dans ``entities['dates']``
    - **where**   : cherche les phrases contenant des mots de localisation
    - **how_many**: cherche dans ``entities['numbers']`` + contexte

    Pour chaque sous-type, retourne la phrase la plus pertinente
    contenant à la fois l'entité extraite et les mots-clés de la question.
    """

    name = "factoid"
    question_type = QuestionType.FACTOID

    def answer(
        self,
        question: QuestionAnalysis,
        analysis: dict,
        docs: list[dict],
    ) -> dict:
        target = question.target_term
        keywords = question.keywords
        sub_type = question.sub_type
        entities = analysis.get("entities", {})

        dispatcher = {
            "who": self._answer_who,
            "by_whom": self._answer_who,
            "when": self._answer_when,
            "when_year": self._answer_when,
            "where": self._answer_where,
            "how_many": self._answer_how_many,
        }

        handler = dispatcher.get(sub_type)
        if handler is None:
            # Fallback générique pour les sous-types non reconnus
            handler = self._answer_generic_factoid

        return handler(question, analysis, docs, entities, target, keywords)

    def _answer_who(
        self,
        question: QuestionAnalysis,
        analysis: dict,
        docs: list[dict],
        entities: dict,
        target: str,
        keywords: set,
    ) -> dict:
        """Répond aux questions *Qui… ?*."""
        proper_nouns = entities.get("proper_nouns", [])

        if not proper_nouns:
            # Chercher dans les docs
            return self._search_factoid_in_docs(
                docs, keywords, "personnes ou entités nommées"
            )

        # Chercher une phrase-clé qui contient un nom propre + mots-clés
        best = self._find_entity_sentence(
            analysis.get("key_sentences", []),
            proper_nouns,
            keywords,
            target,
        )
        if best:
            return self._build_response(best, [best], 0.7)

        # Fallback : retourner le nom propre trouvé avec la meilleure phrase
        for score, sent in analysis.get("key_sentences", []):
            for noun in proper_nouns[:5]:
                if noun.lower() in sent.lower():
                    return self._build_response(
                        sent, [sent], 0.45
                    )

        # Dernier recours : lister les noms propres trouvés
        if proper_nouns:
            answer = (
                f"Voici les entités nommées pertinentes trouvées : "
                f"{', '.join(proper_nouns[:5])}."
            )
            return self._build_response(answer, proper_nouns[:3], 0.3)

        return self._empty_response(
            "Je n'ai pas trouvé de personne ou entité correspondante "
            "dans les documents."
        )

    def _answer_when(
        self,
        question: QuestionAnalysis,
        analysis: dict,
        docs: list[dict],
        entities: dict,
        target: str,
        keywords: set,
    ) -> dict:
        """Répond aux questions *Quand… ?*."""
        dates = entities.get("dates", [])

        if not dates:
            return self._search_factoid_in_docs(
                docs, keywords, "dates ou périodes"
            )

        best = self._find_entity_sentence(
            analysis.get("key_sentences", []),
            dates,
            keywords,
            target,
        )
        if best:
            return self._build_response(best, [best], 0.75)

        for score, sent in analysis.get("key_sentences", []):
            for date in dates[:5]:
                if date.lower() in sent.lower():
                    return self._build_response(sent, [sent], 0.5)

        if dates:
            answer = (
                f"Voici les dates pertinentes trouvées : "
                f"{', '.join(dates[:5])}."
            )
            return self._build_response(answer, dates[:3], 0.3)

        return self._empty_response(
            "Je n'ai pas trouvé de date correspondante dans les documents."
        )

    def _answer_where(
        self,
        question: QuestionAnalysis,
        analysis: dict,
        docs: list[dict],
        entities: dict,
        target: str,
        keywords: set,
    ) -> dict:
        """Répond aux questions *Où… ?*."""
        candidates: list[tuple[float, str]] = []

        # Chercher dans les key_sentences des phrases avec localisation
        for score, sent in analysis.get("key_sentences", []):
            sent_lower = sent.lower()
            has_location = any(
                loc in sent_lower for loc in _LOCATION_WORDS
            )
            if not has_location:
                continue

            bonus = 0.0
            if target and target.lower() in sent_lower:
                bonus += 0.3
            if keywords:
                bonus += _keyword_match_score(sent, keywords) * 0.3

            if bonus > 0:
                candidates.append((score + bonus, sent))

        if candidates:
            candidates.sort(key=lambda x: -x[0])
            best = candidates[0][1]
            return self._build_response(best, [best], 0.7)

        # Chercher dans les docs
        for doc in docs:
            text = _get_doc_text(doc)
            if not text:
                continue
            sentences = _extract_sentences(text)
            for sent in sentences:
                sent_lower = sent.lower()
                has_location = any(
                    loc in sent_lower for loc in _LOCATION_WORDS
                )
                if has_location and keywords:
                    kw_score = _keyword_match_score(sent, keywords)
                    if kw_score > 0.2:
                        return self._build_response(
                            sent, [sent], 0.5
                        )

        return self._empty_response(
            "Je n'ai pas trouvé d'information de localisation "
            "correspondant à votre question."
        )

    def _answer_how_many(
        self,
        question: QuestionAnalysis,
        analysis: dict,
        docs: list[dict],
        entities: dict,
        target: str,
        keywords: set,
    ) -> dict:
        """Répond aux questions *Combien… ?*."""
        numbers = entities.get("numbers", [])

        if not numbers:
            return self._search_factoid_in_docs(
                docs, keywords, "données numériques"
            )

        best = self._find_entity_sentence(
            analysis.get("key_sentences", []),
            numbers,
            keywords,
            target,
        )
        if best:
            return self._build_response(best, [best], 0.7)

        for score, sent in analysis.get("key_sentences", []):
            for num in numbers[:5]:
                if num.lower() in sent.lower():
                    return self._build_response(sent, [sent], 0.5)

        if numbers:
            answer = (
                f"Voici les données numériques trouvées : "
                f"{', '.join(numbers[:5])}."
            )
            return self._build_response(answer, numbers[:3], 0.3)

        return self._empty_response(
            "Je n'ai pas trouvé de donnée numérique correspondante "
            "dans les documents."
        )

    def _answer_generic_factoid(
        self,
        question: QuestionAnalysis,
        analysis: dict,
        docs: list[dict],
        entities: dict,
        target: str,
        keywords: set,
    ) -> dict:
        """Réponse générique pour les faits non couverts par un sous-type."""
        # Chercher une phrase-clé qui contient le maximum de mots-clés
        best = self._find_entity_sentence(
            analysis.get("key_sentences", []),
            [],
            keywords,
            target,
        )
        if best:
            return self._build_response(best, [best], 0.5)

        if keywords:
            for doc in docs:
                text = _get_doc_text(doc)
                matches = _find_sentences_with_keywords(text, keywords, 0.3)
                if matches:
                    return self._build_response(
                        matches[0][1], [matches[0][1]], 0.35
                    )

        return self._empty_response(
            "Je n'ai pas trouvé l'information factuelle demandée."
        )

    def _find_entity_sentence(
        self,
        key_sentences: list[tuple[float, str]],
        entities_list: list[str],
        keywords: set,
        target: str,
    ) -> Optional[str]:
        """Trouve la meilleure phrase contenant une entité + mots-clés.

        Args:
            key_sentences: Liste de tuples (score, phrase).
            entities_list: Liste d'entités (noms, dates, nombres).
            keywords: Mots-clés de la question.
            target: Terme cible.

        Returns:
            La meilleure phrase trouvée, ou None.
        """
        if not entities_list and not target:
            return None

        entity_set = {e.lower() for e in entities_list}

        candidates: list[tuple[float, str]] = []
        for score, sent in key_sentences:
            sent_lower = sent.lower()
            bonus = 0.0

            # Bonus si une entité est dans la phrase
            for entity in entity_set:
                if entity in sent_lower:
                    bonus += 0.2
                    break

            # Bonus si le target est dans la phrase
            if target and target.lower() in sent_lower:
                bonus += 0.25

            # Bonus pour les mots-clés
            if keywords:
                bonus += _keyword_match_score(sent, keywords) * 0.2

            if bonus > 0.1:
                candidates.append((score + bonus, sent))

        if not candidates:
            return None

        candidates.sort(key=lambda x: -x[0])
        return candidates[0][1]

    def _search_factoid_in_docs(
        self,
        docs: list[dict],
        keywords: set,
        info_type: str,
    ) -> dict:
        """Recherche une information factuelle dans les documents bruts.

        Args:
            docs: Liste des documents.
            keywords: Mots-clés à chercher.
            info_type: Type d'information recherchée (pour le message).

        Returns:
            Réponse trouvée ou message d'absence.
        """
        if not keywords:
            return self._empty_response(
                f"Je n'ai pas trouvé de {info_type} dans les documents."
            )

        for doc in docs:
            text = _get_doc_text(doc)
            matches = _find_sentences_with_keywords(text, keywords, 0.15)
            if matches:
                return self._build_response(
                    matches[0][1], [matches[0][1]], 0.4
                )

        return self._empty_response(
            f"Je n'ai pas trouvé de {info_type} correspondant "
            f"à votre question dans les documents."
        )


# ═══════════════════════════════════════════════════════════════════════════
# ── 3. How (Comment) ──────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

class HowStrategy(BaseStrategy):
    """Répond aux questions de procédure (*Comment… ?*).

    Stratégie :
    1. Cherche dans ``analysis['lists']`` des items correspondant au sujet.
    2. Cherche dans les ``key_sentences`` des phrases contenant des mots
       de séquence (*d'abord*, *ensuite*, *étape*, etc.).
    3. Extrait les phrases numérotées ou avec mots de procédure.
    4. Construit une réponse structurée en étapes.

    Si le sous-type est **how_steps**, privilégie l'extraction d'étapes
    numérotées depuis la structure du document.
    """

    name = "how"
    question_type = QuestionType.HOW

    def answer(
        self,
        question: QuestionAnalysis,
        analysis: dict,
        docs: list[dict],
    ) -> dict:
        target = question.target_term
        keywords = question.keywords
        sub_type = question.sub_type

        # ── Étape 1 : Chercher dans les listes structurées ───────────
        list_result = self._extract_from_lists(analysis.get("lists", []), target)
        if list_result:
            return self._build_response(list_result, [list_result], 0.75)

        # ── Étape 2 : Chercher des phrases de procédure ─────────────
        proc_sentences = self._find_procedural_sentences(
            analysis.get("key_sentences", []), target, keywords
        )

        if proc_sentences:
            answer = self._format_procedural_answer(proc_sentences, sub_type)
            return self._build_response(answer, proc_sentences, 0.65)

        # ── Étape 3 : Chercher dans les documents bruts ─────────────
        for doc in docs:
            text = _get_doc_text(doc)
            if not text:
                continue

            # Chercher des listes dans le texte complet
            all_sentences = _extract_sentences(text)
            seq_sentences = self._find_sequence_sentences(
                all_sentences, target, keywords
            )
            if seq_sentences:
                answer = self._format_procedural_answer(
                    seq_sentences, sub_type
                )
                return self._build_response(answer, seq_sentences, 0.5)

        return self._empty_response(
            "Je n'ai pas trouvé de procédure ou d'explication "
            "correspondant à votre question."
        )

    def _extract_from_lists(
        self,
        lists: list[dict],
        target: str,
    ) -> Optional[str]:
        """Extrait une réponse depuis les listes structurées.

        Cherche une liste dont l'en-tête correspond au sujet, ou dont
        les items contiennent le terme cible.

        Args:
            lists: Listes structurées du document.
            target: Terme cible.

        Returns:
            Réponse formatée, ou None.
        """
        if not lists:
            return None

        best_list = None
        best_score = 0.0

        for lst in lists:
            header = lst.get("header", "")
            items = lst.get("items", [])

            if not items:
                continue

            # Score : mots communs entre header et target
            header_score = (
                _word_overlap_score(header, target) if target else 0.5
            )

            # Bonus si target apparaît dans les items
            item_bonus = 0.0
            if target:
                for item in items:
                    if target.lower() in item.lower():
                        item_bonus = 0.2
                        break

            total = header_score + item_bonus
            if total > best_score:
                best_score = total
                best_list = lst

        if best_list and best_score >= 0.2:
            items = best_list["items"]
            formatted = self._format_list_as_steps(items)
            return formatted

        return None

    def _find_procedural_sentences(
        self,
        key_sentences: list[tuple[float, str]],
        target: str,
        keywords: set,
    ) -> list[str]:
        """Trouve les phrases à caractère procédural.

        Args:
            key_sentences: Phrases-clés scorées.
            target: Terme cible.
            keywords: Mots-clés de la question.

        Returns:
            Liste de phrases procédurales triées par pertinence.
        """
        candidates: list[tuple[float, str]] = []

        for score, sent in key_sentences:
            sent_lower = sent.lower()
            bonus = 0.0

            # Mots de séquence
            has_sequence = any(
                seq in sent_lower for seq in _SEQUENCE_WORDS
            )
            if has_sequence:
                bonus += 0.3

            # Mots de procédure / action
            has_procedure = any(
                word in sent_lower
                for word in {"pour", "il faut", "doit", "nécessaire",
                             "étapes", "procédure", "méthode", "afin de"}
            )
            if has_procedure:
                bonus += 0.2

            # Mots-clés
            if target and target.lower() in sent_lower:
                bonus += 0.3
            if keywords:
                bonus += _keyword_match_score(sent, keywords) * 0.2

            if bonus > 0:
                candidates.append((score + bonus, sent))

        candidates.sort(key=lambda x: -x[0])

        # Retourner les meilleures phrases (max 5)
        return [sent for _, sent in candidates[:5]]

    def _find_sequence_sentences(
        self,
        sentences: list[str],
        target: str,
        keywords: set,
    ) -> list[str]:
        """Trouve des phrases de séquence dans une liste brute.

        Args:
            sentences: Liste de phrases.
            target: Terme cible.
            keywords: Mots-clés.

        Returns:
            Phrases de séquence.
        """
        candidates: list[tuple[float, str]] = []

        for sent in sentences:
            sent_lower = sent.lower()
            bonus = 0.0

            # Énumération détectée
            if _contains_enumeration(sent):
                bonus += 0.4

            # Mots de séquence
            if any(seq in sent_lower for seq in _SEQUENCE_WORDS):
                bonus += 0.3

            if target and target.lower() in sent_lower:
                bonus += 0.3
            if keywords:
                bonus += _keyword_match_score(sent, keywords) * 0.2

            if bonus > 0.2:
                candidates.append((bonus, sent))

        candidates.sort(key=lambda x: -x[0])
        return [sent for _, sent in candidates[:5]]

    def _format_procedural_answer(
        self,
        sentences: list[str],
        sub_type: str,
    ) -> str:
        """Formate les phrases procédurales en une réponse structurée.

        Args:
            sentences: Phrases à formater.
            sub_type: Sous-type de question (how_steps, how_to, etc.).

        Returns:
            Texte formaté.
        """
        if not sentences:
            return ""

        if sub_type == "how_steps" or self._has_enumeration(sentences):
            # Réponse en étapes numérotées
            parts = ["Voici les étapes :"]
            for i, sent in enumerate(sentences, 1):
                # Nettoyer les numéros existants
                clean = re.sub(r'^\s*\d+[.)]\s*', '', sent)
                parts.append(f"{i}. {clean}")
            return "\n".join(parts)

        # Réponse en paragraphe continu
        return " ".join(sentences)

    def _has_enumeration(self, sentences: list[str]) -> bool:
        """Vérifie si un ensemble de phrases contient des énumérations."""
        if not sentences:
            return False
        enum_count = sum(1 for s in sentences if _contains_enumeration(s))
        return enum_count >= 2

    def _format_list_as_steps(self, items: list[str]) -> str:
        """Formate une liste d'items en étapes numérotées.

        Args:
            items: Liste d'items.

        Returns:
        Texte formaté en étapes.
        """
        parts = []
        for i, item in enumerate(items, 1):
            clean = item.strip().rstrip(".,;")
            parts.append(f"{i}. {clean}")
        return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# ── 4. Why (Pourquoi) ─────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

class WhyStrategy(BaseStrategy):
    """Répond aux questions causales (*Pourquoi… ?*).

    Stratégie :
    1. Cherche dans les ``key_sentences`` des phrases contenant à la fois
       le ``target_term`` et un connecteur causal (*car*, *parce que*…).
    2. Priorise les phrases ayant le score combiné le plus élevé.
    3. Si insuffisant, recherche dans les documents bruts.
    """

    name = "why"
    question_type = QuestionType.WHY

    def answer(
        self,
        question: QuestionAnalysis,
        analysis: dict,
        docs: list[dict],
    ) -> dict:
        target = question.target_term
        keywords = question.keywords

        if not target and not keywords:
            return self._empty_response(
                "Je n'ai pas compris la cause que vous voulez expliquer. "
                "Pouvez-vous reformuler ?"
            )

        # ── Étape 1 : Chercher dans les key_sentences ────────────────
        causal_sentences = self._find_causal_sentences(
            analysis.get("key_sentences", []), target, keywords
        )

        if causal_sentences:
            answer = self._format_causal_answer(causal_sentences)
            return self._build_response(answer, causal_sentences, 0.7)

        # ── Étape 2 : Chercher dans les key_sentences sans cible exacte ──
        # Peut-être que la question ne mentionne pas le target exact
        for score, sent in analysis.get("key_sentences", []):
            sent_lower = sent.lower()
            has_causal = any(
                conn in sent_lower for conn in _CAUSAL_CONNECTORS
            )
            if has_causal and keywords:
                kw_score = _keyword_match_score(sent, keywords)
                if kw_score >= 0.2:
                    return self._build_response(
                        sent, [sent], 0.5
                    )

        # ── Étape 3 : Chercher dans les documents bruts ──────────────
        all_keywords = keywords | {target} if target else keywords
        if all_keywords:
            doc_result = self._search_causal_in_docs(docs, all_keywords)
            if doc_result:
                return self._build_response(
                    doc_result, [doc_result], 0.4
                )

        return self._empty_response(
            "Je n'ai pas trouvé d'explication causale correspondant "
            "à votre question dans les documents."
        )

    def _find_causal_sentences(
        self,
        key_sentences: list[tuple[float, str]],
        target: str,
        keywords: set,
    ) -> list[str]:
        """Trouve les phrases avec connecteurs causaux.

        Args:
            key_sentences: Phrases-clés scorées.
            target: Terme cible.
            keywords: Mots-clés de la question.

        Returns:
            Liste de phrases causales triées par pertinence.
        """
        candidates: list[tuple[float, str]] = []

        for score, sent in key_sentences:
            sent_lower = sent.lower()
            causal_score = 0.0

            # Vérifier les connecteurs causaux
            has_causal = False
            for conn in _CAUSAL_CONNECTORS:
                if conn in sent_lower:
                    has_causal = True
                    # Bonus supplémentaire si le connecteur est proche du target
                    if target and target.lower() in sent_lower:
                        target_pos = sent_lower.index(target.lower())
                        conn_pos = sent_lower.index(conn)
                        distance = abs(target_pos - conn_pos)
                        if distance < 50:
                            causal_score += 0.15
                    break

            if not has_causal:
                continue

            # Score combiné
            if target and target.lower() in sent_lower:
                causal_score += 0.4
            if keywords:
                causal_score += _keyword_match_score(sent, keywords) * 0.3

            if causal_score > 0.1:
                candidates.append((score + causal_score, sent))

        candidates.sort(key=lambda x: -x[0])
        return [sent for _, sent in candidates[:3]]

    def _search_causal_in_docs(
        self,
        docs: list[dict],
        keywords: set,
    ) -> Optional[str]:
        """Recherche des phrases causales dans les documents bruts.

        Args:
            docs: Liste des documents.
            keywords: Mots-clés élargis.

        Returns:
            Meilleure phrase causale trouvée, ou None.
        """
        for doc in docs:
            text = _get_doc_text(doc)
            if not text:
                continue

            sentences = _extract_sentences(text)
            for sent in sentences:
                sent_lower = sent.lower()
                has_causal = any(
                    conn in sent_lower for conn in _CAUSAL_CONNECTORS
                )
                if has_causal:
                    kw_score = _keyword_match_score(sent, keywords)
                    if kw_score >= 0.2:
                        return sent
        return None

    def _format_causal_answer(self, sentences: list[str]) -> str:
        """Formate les phrases causales en une réponse cohérente.

        Args:
            sentences: Phrases causales.

        Returns:
            Texte formaté.
        """
        if not sentences:
            return ""
        if len(sentences) == 1:
            return sentences[0]
        return " ".join(sentences)


# ═══════════════════════════════════════════════════════════════════════════
# ── 5. List (Liste / Énumération) ─────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

class ListStrategy(BaseStrategy):
    """Répond aux demandes de liste (*Cite les types de X*).

    Stratégie :
    1. Cherche dans ``analysis['lists']`` les items correspondant au sujet.
    2. Si pas de liste structurée, cherche dans les ``key_sentences``
       des énumérations via la détection de motifs (puces, numéros).
    3. Sinon, parcourt les documents bruts à la recherche d'énumérations.
    4. Construit une réponse avec chaque item sur une ligne.
    """

    name = "list"
    question_type = QuestionType.LIST

    def answer(
        self,
        question: QuestionAnalysis,
        analysis: dict,
        docs: list[dict],
    ) -> dict:
        target = question.target_term
        keywords = question.keywords

        # ── Étape 1 : Chercher dans les listes structurées ───────────
        list_result = self._extract_from_structured_lists(
            analysis.get("lists", []), target, keywords
        )
        if list_result:
            return self._build_response(list_result, [list_result], 0.8)

        # ── Étape 2 : Chercher des énumérations dans key_sentences ────
        enum_result = self._extract_enumerations(
            analysis.get("key_sentences", []), target, keywords
        )
        if enum_result:
            return self._build_response(enum_result, [enum_result], 0.6)

        # ── Étape 3 : Chercher dans les documents bruts ──────────────
        doc_result = self._search_list_in_docs(docs, target, keywords)
        if doc_result:
            return self._build_response(doc_result, [doc_result], 0.5)

        return self._empty_response(
            "Je n'ai pas trouvé de liste ou d'énumération "
            "correspondant à votre question."
        )

    def _extract_from_structured_lists(
        self,
        lists: list[dict],
        target: str,
        keywords: set,
    ) -> Optional[str]:
        """Extrait une réponse depuis les listes structurées.

        Args:
            lists: Listes structurées du document.
            target: Terme cible.
            keywords: Mots-clés.

        Returns:
            Réponse formatée, ou None.
        """
        if not lists:
            return None

        best_list = None
        best_score = 0.0

        for lst in lists:
            header = lst.get("header", "")
            items = lst.get("items", [])
            if not items:
                continue

            # Score basé sur la similarité header/target
            score = _word_overlap_score(header, target) if target else 0.3
            # Bonus si target est dans le header ou les items
            if target:
                if target.lower() in header.lower():
                    score += 0.3
                for item in items:
                    if target.lower() in item.lower():
                        score += 0.2
                        break
            # Bonus si des mots-clés sont dans le header
            if keywords:
                score += _keyword_match_score(header, keywords) * 0.2

            if score > best_score:
                best_score = score
                best_list = lst

        if best_list and best_score >= 0.2:
            items = best_list["items"]
            header = best_list["header"]
            return self._format_list_answer(items, header)

        return None

    def _extract_enumerations(
        self,
        key_sentences: list[tuple[float, str]],
        target: str,
        keywords: set,
    ) -> Optional[str]:
        """Extrait des énumérations depuis les phrases-clés.

        Args:
            key_sentences: Phrases-clés.
            target: Terme cible.
            keywords: Mots-clés.

        Returns:
            Réponse formatée, ou None.
        """
        candidates: list[tuple[float, str]] = []

        for score, sent in key_sentences:
            sent_lower = sent.lower()

            if not _contains_enumeration(sent):
                continue

            bonus = 0.0
            if target and target.lower() in sent_lower:
                bonus += 0.4
            if keywords:
                bonus += _keyword_match_score(sent, keywords) * 0.3

            if bonus > 0:
                candidates.append((score + bonus, sent))

        if not candidates:
            return None

        candidates.sort(key=lambda x: -x[0])
        items = [sent for _, sent in candidates[:8]]

        if len(items) == 1:
            return items[0]

        return self._format_items_as_list(items)

    def _search_list_in_docs(
        self,
        docs: list[dict],
        target: str,
        keywords: set,
    ) -> Optional[str]:
        """Recherche des énumérations dans les documents bruts.

        Args:
            docs: Liste des documents.
            target: Terme cible.
            keywords: Mots-clés.

        Returns:
            Réponse formatée, ou None.
        """
        enumerations: list[str] = []

        for doc in docs:
            text = _get_doc_text(doc)
            if not text:
                continue

            lines = text.split("\n")
            for line in lines:
                line_stripped = line.strip()
                # Détecter les items de liste
                if re.match(r'^\s*[-*•]\s+', line_stripped):
                    item = re.sub(r'^\s*[-*•]\s+', '', line_stripped)
                    enumerations.append(item)
                elif re.match(r'^\s*\d+[.)]\s+', line_stripped):
                    item = re.sub(r'^\s*\d+[.)]\s+', '', line_stripped)
                    enumerations.append(item)

        if enumerations:
            # Filtrer par pertinence
            if target:
                filtered = [
                    item for item in enumerations
                    if target.lower() in item.lower()
                ]
                if filtered:
                    enumerations = filtered

            if keywords:
                scored = [
                    (_keyword_match_score(item, keywords), item)
                    for item in enumerations
                ]
                scored.sort(key=lambda x: -x[0])
                enumerations = [item for _, item in scored]

            return self._format_items_as_list(enumerations[:10])

        return None

    def _format_list_answer(
        self,
        items: list[str],
        header: str = "",
    ) -> str:
        """Formate une liste structurée en réponse lisible."""
        parts = []
        if header:
            parts.append(f"{header.rstrip(':')} :")
        else:
            parts.append("Voici les éléments trouvés :")

        for i, item in enumerate(items, 1):
            clean = item.strip().rstrip(".,;")
            parts.append(f"{i}. {clean}")

        return "\n".join(parts)

    def _format_items_as_list(self, items: list[str]) -> str:
        """Formate une liste d'items simple."""
        if not items:
            return ""
        parts = ["Voici les éléments trouvés :"]
        for i, item in enumerate(items, 1):
            clean = item.strip().rstrip(".,;")
            parts.append(f"{i}. {clean}")
        return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# ── 6. Comparison (Comparaison) ───────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

class ComparisonStrategy(BaseStrategy):
    """Répond aux questions de comparaison (*Différence entre X et Y ?*).

    Stratégie :
    1. Cherche des phrases contenant les DEUX termes (``target_term``
       et ``secondary_term``).
    2. Priorise les phrases avec mots de comparaison.
    3. Structure la réponse en listant les points de différence trouvés.
    """

    name = "comparison"
    question_type = QuestionType.COMPARISON

    def answer(
        self,
        question: QuestionAnalysis,
        analysis: dict,
        docs: list[dict],
    ) -> dict:
        term1 = question.target_term
        term2 = question.secondary_term
        keywords = question.keywords

        if not term1 or not term2:
            return self._empty_response(
                "Je n'ai pas identifié les deux éléments à comparer. "
                "Pouvez-vous préciser ?"
            )

        # ── Étape 1 : Chercher dans les key_sentences ────────────────
        comparison_sentences = self._find_comparison_sentences(
            analysis.get("key_sentences", []), term1, term2, keywords
        )

        if comparison_sentences:
            answer = self._format_comparison_answer(
                comparison_sentences, term1, term2
            )
            return self._build_response(answer, comparison_sentences, 0.75)

        # ── Étape 2 : Chercher dans les key_sentences avec chaque terme ──
        # Phrases avec un seul terme mais un mot de comparaison
        partials = self._find_partial_comparison(
            analysis.get("key_sentences", []), term1, term2, keywords
        )
        if partials:
            answer = self._format_comparison_answer(partials, term1, term2)
            return self._build_response(answer, partials, 0.55)

        # ── Étape 3 : Chercher dans les documents bruts ──────────────
        doc_result = self._search_comparison_in_docs(docs, term1, term2, keywords)
        if doc_result:
            return self._build_response(doc_result, [doc_result], 0.45)

        return self._empty_response(
            f"Je n'ai pas trouvé d'information comparative entre "
            f"« {term1} » et « {term2} » dans les documents."
        )

    def _find_comparison_sentences(
        self,
        key_sentences: list[tuple[float, str]],
        term1: str,
        term2: str,
        keywords: set,
    ) -> list[str]:
        """Trouve des phrases contenant les deux termes de la comparaison.

        Args:
            key_sentences: Phrases-clés.
            term1: Premier terme.
            term2: Second terme.
            keywords: Mots-clés.

        Returns:
            Phrases de comparaison triées par pertinence.
        """
        candidates: list[tuple[float, str]] = []

        for score, sent in key_sentences:
            sent_lower = sent.lower()
            t1_present = term1.lower() in sent_lower
            t2_present = term2.lower() in sent_lower

            if not (t1_present or t2_present):
                continue

            comp_score = 0.0
            both_present = t1_present and t2_present

            if both_present:
                comp_score += 0.5

            # Mots de comparaison
            has_comp_word = any(
                cw in sent_lower for cw in _COMPARISON_WORDS
            )
            if has_comp_word:
                comp_score += 0.3

            # Mots-clés additionnels
            if keywords:
                comp_score += _keyword_match_score(sent, keywords) * 0.2

            if comp_score > 0.1:
                candidates.append((score + comp_score, sent))

        candidates.sort(key=lambda x: -x[0])
        return [sent for _, sent in candidates[:5]]

    def _find_partial_comparison(
        self,
        key_sentences: list[tuple[float, str]],
        term1: str,
        term2: str,
        keywords: set,
    ) -> list[str]:
        """Trouve des phrases contenant un terme + mot de comparaison.

        Args:
            key_sentences: Phrases-clés.
            term1: Premier terme.
            term2: Second terme.
            keywords: Mots-clés.

        Returns:
            Phrases de comparaison partielle.
        """
        candidates: list[tuple[float, str]] = []

        for score, sent in key_sentences:
            sent_lower = sent.lower()
            t1_present = term1.lower() in sent_lower
            t2_present = term2.lower() in sent_lower

            if not (t1_present or t2_present):
                continue

            has_comp_word = any(
                cw in sent_lower for cw in _COMPARISON_WORDS
            )
            if not has_comp_word:
                continue

            comp_score = 0.3  # Mot de comparaison présent
            if t1_present and t2_present:
                comp_score += 0.5
            elif t1_present or t2_present:
                comp_score += 0.2

            if keywords:
                comp_score += _keyword_match_score(sent, keywords) * 0.2

            candidates.append((score + comp_score, sent))

        candidates.sort(key=lambda x: -x[0])
        return [sent for _, sent in candidates[:5]]

    def _search_comparison_in_docs(
        self,
        docs: list[dict],
        term1: str,
        term2: str,
        keywords: set,
    ) -> Optional[str]:
        """Recherche une comparaison dans les documents bruts.

        Args:
            docs: Liste des documents.
            term1: Premier terme.
            term2: Second terme.
            keywords: Mots-clés.

        Returns:
            Meilleure phrase trouvée, ou None.
        """
        for doc in docs:
            text = _get_doc_text(doc)
            if not text:
                continue

            sentences = _extract_sentences(text)
            for sent in sentences:
                sent_lower = sent.lower()
                t1 = term1.lower() in sent_lower
                t2 = term2.lower() in sent_lower

                if not (t1 or t2):
                    continue

                has_comp = any(
                    cw in sent_lower for cw in _COMPARISON_WORDS
                )
                if has_comp and (t1 or t2):
                    return sent

        return None

    def _format_comparison_answer(
        self,
        sentences: list[str],
        term1: str,
        term2: str,
    ) -> str:
        """Formate les phrases de comparaison en une réponse structurée.

        Args:
            sentences: Phrases de comparaison.
            term1: Premier terme.
            term2: Second terme.

        Returns:
            Texte formaté.
        """
        if not sentences:
            return ""

        header = (
            f"Comparaison entre « {term1} » et « {term2} » :"
        )
        parts = [header]

        for i, sent in enumerate(sentences, 1):
            parts.append(f"\n{i}. {sent}")

        return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# ── 7. Boolean (Oui / Non) ────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

class BooleanStrategy(BaseStrategy):
    """Répond aux questions fermées (*Est-ce que X ?*).

    Stratégie :
    1. Cherche le ``target_term`` dans les ``definitions`` ou
       ``key_sentences``.
    2. Si trouvé → « Oui » suivi de la preuve.
    3. Sinon → « Non » avec le contexte le plus proche.
    4. Calcule un score de confiance basé sur la qualité de la preuve.

    Gère la négation : si ``question.has_negation`` est vrai, la réponse
    est inversée logiquement.
    """

    name = "boolean"
    question_type = QuestionType.BOOLEAN

    def answer(
        self,
        question: QuestionAnalysis,
        analysis: dict,
        docs: list[dict],
    ) -> dict:
        target = question.target_term
        keywords = question.keywords
        has_negation = question.has_negation

        if not target and not keywords:
            return self._build_response(
                "Je n'ai pas compris la proposition à vérifier. "
                "Pouvez-vous reformuler ?",
                [],
                0.1,
            )

        # ── Chercher des preuves dans les sources ────────────────────
        evidence, confidence = self._find_evidence(
            analysis, target, keywords, docs
        )

        # ── Appliquer la négation si nécessaire ──────────────────────
        if has_negation:
            evidence_exists = bool(evidence)
            if evidence_exists:
                # La question contient une négation mais la preuve existe
                answer = (
                    f"Non, {self._extract_assertion(target, keywords)} "
                    f"est incorrect. "
                    f"Voici ce que disent les documents : {evidence}"
                )
                confidence = max(confidence, 0.5)
            else:
                # Négation confirmée par l'absence de preuve
                answer = (
                    f"Oui, c'est exact : "
                    f"{self._extract_assertion(target, keywords)} "
                    f"n'apparaît pas dans les documents."
                )
                confidence = 0.4
        else:
            if evidence:
                answer = (
                    f"Oui. "
                    f"{evidence}"
                )
                confidence = min(confidence + 0.15, 0.95)
            else:
                answer = (
                    f"Non, je n'ai pas trouvé d'information confirmant "
                    f"{self._extract_assertion(target, keywords)} "
                    f"dans les documents disponibles."
                )
                confidence = max(confidence, 0.2)

        return self._build_response(answer, [evidence] if evidence else [], confidence)

    def _find_evidence(
        self,
        analysis: dict,
        target: str,
        keywords: set,
        docs: list[dict],
    ) -> tuple[Optional[str], float]:
        """Cherche une preuve pour la proposition.

        Returns:
            Tuple (preuve, confiance).
        """
        # 1. Chercher dans les définitions
        for def_item in analysis.get("definitions", []):
            term = def_item.get("term", "")
            if target and (
                target.lower() == term.lower()
                or target.lower() in term.lower()
            ):
                def_text = _get_definition_text(def_item)
                return def_text, 0.85

        # 2. Chercher dans les key_sentences
        for score, sent in analysis.get("key_sentences", []):
            sent_lower = sent.lower()
            if target and target.lower() in sent_lower:
                confidence = min(0.3 + score * 0.5, 0.8)
                return sent, confidence

        # 3. Chercher avec les mots-clés
        if keywords:
            for score, sent in analysis.get("key_sentences", []):
                kw_score = _keyword_match_score(sent, keywords)
                if kw_score >= 0.3:
                    confidence = min(0.2 + kw_score * 0.5, 0.6)
                    return sent, confidence

        # 4. Chercher dans les documents bruts
        if target:
            for doc in docs:
                text = _get_doc_text(doc)
                if target.lower() in text.lower():
                    matches = _find_sentences_with_keywords(text, {target})
                    if matches:
                        return matches[0][1], 0.35

        return None, 0.0

    def _extract_assertion(self, target: str, keywords: set) -> str:
        """Extrait l'assertion de la question."""
        if target:
            return f"« {target} »"
        if keywords:
            return f"« {', '.join(list(keywords)[:3])} »"
        return "cette information"


# ═══════════════════════════════════════════════════════════════════════════
# ── 8. Summary (Résumé) ───────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

class SummaryStrategy(BaseStrategy):
    """Produit un résumé structuré (*Résume X*).

    Stratégie :
    1. Prend les 5 à 8 meilleures ``key_sentences`` de l'analyse.
    2. Ajoute les définitions trouvées comme points clés.
    3. Présente le tout comme un résumé structuré avec sections
       si le document a une structure de sections.
    """

    name = "summary"
    question_type = QuestionType.SUMMARY

    # Nombre de phrases-clés à inclure dans le résumé
    _MAX_SENTENCES = 8
    _MIN_SENTENCES = 5

    def answer(
        self,
        question: QuestionAnalysis,
        analysis: dict,
        docs: list[dict],
    ) -> dict:
        target = question.target_term
        key_sentences = analysis.get("key_sentences", [])
        definitions = analysis.get("definitions", [])
        sections = analysis.get("sections", [])

        if not key_sentences and not definitions:
            # Chercher dans les documents bruts
            doc_summary = self._summarize_docs(docs, target)
            if doc_summary:
                return self._build_response(doc_summary, [doc_summary], 0.4)
            return self._empty_response(
                "Je n'ai pas assez de contenu pour produire un résumé."
            )

        # ── Construire le résumé ─────────────────────────────────────
        parts: list[str] = []
        sources: list[str] = []

        # 1. Titre
        if target:
            parts.append(f"Résumé de « {target} » :")
        else:
            parts.append("Résumé du document :")

        # 2. Définitions comme points clés
        if definitions:
            parts.append("\nDéfinitions clés :")
            # Filtrer les définitions pertinentes
            filtered_defs = self._filter_relevant_definitions(
                definitions, target
            )
            for def_item in filtered_defs[:4]:
                term = def_item.get("term", "")
                def_text = _get_definition_text(def_item)
                line = f"• {term} : {def_text}"
                parts.append(line)
                sources.append(def_text)

        # 3. Phrases-clés principales
        best_sentences = self._extract_best_sentences(
            key_sentences, target
        )

        if best_sentences:
            parts.append("\nPoints principaux :")
            for i, sent in enumerate(best_sentences, 1):
                clean = sent.strip()
                parts.append(f"\n{i}. {clean}")
                sources.append(clean)

        # 4. Structure par sections (si disponible)
        if sections and len(sections) > 1:
            section_summary = self._summarize_sections(
                sections, target, key_sentences, self._MAX_SENTENCES
            )
            if section_summary:
                parts.append("\n\nAperçu par sections :")
                parts.append(section_summary)

        answer = "\n".join(parts)

        # Confiance : basée sur la couverture du target et la richesse
        confidence = self._compute_confidence(
            best_sentences, definitions, target
        )

        return self._build_response(answer, sources[:5], confidence)

    def _filter_relevant_definitions(
        self,
        definitions: list[dict],
        target: str,
    ) -> list[dict]:
        """Filtre les définitions pertinentes pour la cible.

        Args:
            definitions: Liste des définitions.
            target: Terme cible.

        Returns:
            Définitions pertinentes.
        """
        if not target:
            return definitions

        # Prioriser les définitions liées au target
        relevant = []
        other = []
        for def_item in definitions:
            term = def_item.get("term", "")
            if target.lower() in term.lower() or term.lower() in target.lower():
                relevant.append(def_item)
            else:
                other.append(def_item)

        return relevant + other

    def _extract_best_sentences(
        self,
        key_sentences: list[tuple[float, str]],
        target: str,
    ) -> list[str]:
        """Extrait les meilleures phrases pour le résumé.

        Favorise les phrases contenant le terme cible.

        Args:
            key_sentences: Phrases-clés scorées.
            target: Terme cible.

        Returns:
            Meilleures phrases (limité à _MAX_SENTENCES).
        """
        if not key_sentences:
            return []

        # Boost des phrases contenant le target
        boosted = []
        for score, sent in key_sentences:
            if target and target.lower() in sent.lower():
                score *= 1.3
            boosted.append((score, sent))

        boosted.sort(key=lambda x: -x[0])

        # Prendre les meilleures
        selected = []
        seen_texts = set()
        for _, sent in boosted:
            # Éviter les doublons proches
            sent_normalized = sent.strip().lower()[:100]
            if sent_normalized not in seen_texts:
                selected.append(sent)
                seen_texts.add(sent_normalized)
            if len(selected) >= self._MAX_SENTENCES:
                break

        return selected[:self._MAX_SENTENCES]

    def _summarize_sections(
        self,
        sections: list[dict],
        target: str,
        key_sentences: list[tuple[float, str]],
        max_sentences: int,
    ) -> Optional[str]:
        """Produit un résumé structuré par sections.

        Args:
            sections: Structure du document en sections.
            target: Terme cible.
            key_sentences: Phrases-clés.
            max_sentences: Nombre maximum de phrases.

        Returns:
            Résumé par sections, ou None.
        """
        if not sections:
            return None

        # Index des phrases-clés déjà utilisées
        used_keys = {
            s.strip().lower()[:80]
            for _, s in key_sentences[:max_sentences]
        }

        section_parts = []
        section_count = 0

        for section in sections:
            if section_count >= 4:  # Max 4 sections
                break

            title = section.get("title", "")
            section_sents = section.get("sentences", [])

            if not title or not section_sents:
                continue

            # Chercher si la section est pertinente (target présent)
            if target:
                title_relevant = target.lower() in title.lower()
                content_relevant = any(
                    target.lower() in s.lower()
                    for s in section_sents[:5]
                )
                if not (title_relevant or content_relevant):
                    continue

            # Prendre la première phrase de la section (si pas déjà utilisée)
            first_sent = section_sents[0].strip()
            if first_sent.lower()[:80] in used_keys:
                # Prendre la seconde
                if len(section_sents) > 1:
                    first_sent = section_sents[1].strip()

            section_parts.append(f"• {title.strip(':')} : {first_sent}")
            section_count += 1

        if not section_parts:
            return None

        return "\n".join(section_parts)

    def _compute_confidence(
        self,
        sentences: list[str],
        definitions: list[dict],
        target: str,
    ) -> float:
        """Calcule la confiance du résumé.

        Args:
            sentences: Phrases sélectionnées.
            definitions: Définitions trouvées.
            target: Terme cible.

        Returns:
            Score de confiance.
        """
        if not sentences:
            return 0.0

        base = 0.5

        # Plus de phrases = plus de confiance (jusqu'à un certain point)
        sent_count = len(sentences)
        if sent_count >= 5:
            base += 0.2
        elif sent_count >= 3:
            base += 0.1

        # Bonus si des définitions sont incluses
        if definitions:
            base += 0.15

        # Bonus si le target est couvert
        if target:
            target_covered = sum(
                1 for s in sentences if target.lower() in s.lower()
            )
            if target_covered >= 2:
                base += 0.1

        return min(base, 0.95)

    def _summarize_docs(
        self,
        docs: list[dict],
        target: str,
    ) -> Optional[str]:
        """Produit un résumé depuis les documents bruts.

        Args:
            docs: Liste des documents.
            target: Terme cible.

        Returns:
            Résumé, ou None.
        """
        all_sentences: list[str] = []

        for doc in docs:
            text = _get_doc_text(doc)
            if text:
                sents = _extract_sentences(text)
                all_sentences.extend(sents)

        if not all_sentences:
            return None

        # Si target, filtrer
        if target:
            target_sents = [
                s for s in all_sentences
                if target.lower() in s.lower()
            ]
            if target_sents:
                all_sentences = target_sents

        # Prendre les premières phrases (introduction)
        selected = all_sentences[:self._MIN_SENTENCES]

        parts = ["Résumé :"]
        for i, sent in enumerate(selected, 1):
            parts.append(f"{i}. {sent.strip()}")

        return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# ── 9. Example (Exemple) ──────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

class ExampleStrategy(BaseStrategy):
    """Répond aux demandes d'exemple (*Donne un exemple de X*).

    Stratégie :
    1. Cherche des phrases contenant des marqueurs d'exemple
       (*exemple*, *par exemple*, *illustration*, *cas concret*).
    2. Si trouvé, retourne la phrase la plus pertinente.
    3. Fallback : retourne une phrase-clé contenant *notamment* ou
       *tel que* qui introduit souvent des exemples.
    4. Si vraiment aucun exemple, retourne un message clair indiquant
       l'absence d'exemple dans le texte.
    """

    name = "example"
    question_type = QuestionType.EXAMPLE

    def answer(
        self,
        question: QuestionAnalysis,
        analysis: dict,
        docs: list[dict],
    ) -> dict:
        target = question.target_term
        keywords = question.keywords

        # ── Étape 1 : Chercher des phrases avec marqueurs d'exemple ──
        example_sentences = self._find_example_sentences(
            analysis.get("key_sentences", []), target, keywords
        )

        if example_sentences:
            best = example_sentences[0]
            return self._build_response(best, [best], 0.8)

        # ── Étape 2 : Fallback — phrases avec "notamment" ou "tel que" ──
        secondary = self._find_secondary_examples(
            analysis.get("key_sentences", []), target, keywords
        )

        if secondary:
            return self._build_response(secondary, [secondary], 0.55)

        # ── Étape 3 : Chercher dans les documents bruts ──────────────
        for doc in docs:
            text = _get_doc_text(doc)
            if not text:
                continue
            sentences = _extract_sentences(text)
            for sent in sentences:
                sent_lower = sent.lower()
                is_example = any(
                    marker in sent_lower for marker in _EXAMPLE_MARKERS
                )
                if is_example:
                    if target and target.lower() in sent_lower:
                        return self._build_response(sent, [sent], 0.6)
                    if keywords:
                        kw_score = _keyword_match_score(sent, keywords)
                        if kw_score >= 0.2:
                            return self._build_response(sent, [sent], 0.5)

        # ── Étape 4 : Aucun exemple trouvé ───────────────────────────
        if target:
            return self._empty_response(
                f"Je n'ai pas trouvé d'exemple concret de « {target} » "
                f"dans les documents disponibles. Les documents décrivent "
                f"le concept mais ne fournissent pas d'illustration "
                f"spécifique."
            )
        return self._empty_response(
            "Je n'ai pas trouvé d'exemple correspondant "
            "dans les documents disponibles."
        )

    def _find_example_sentences(
        self,
        key_sentences: list[tuple[float, str]],
        target: str,
        keywords: set,
    ) -> list[str]:
        """Trouve les phrases contenant des marqueurs d'exemple explicites.

        Args:
            key_sentences: Phrases-clés scorées.
            target: Terme cible.
            keywords: Mots-clés de la question.

        Returns:
            Phrases d'exemple triées par pertinence.
        """
        candidates: list[tuple[float, str]] = []

        for score, sent in key_sentences:
            sent_lower = sent.lower()

            # Vérifier la présence d'un marqueur d'exemple
            has_example_marker = any(
                marker in sent_lower for marker in _EXAMPLE_MARKERS
            )
            if not has_example_marker:
                continue

            bonus = 0.0
            if target and target.lower() in sent_lower:
                bonus += 0.4
            if keywords:
                bonus += _keyword_match_score(sent, keywords) * 0.3

            candidates.append((score + bonus, sent))

        candidates.sort(key=lambda x: -x[0])
        return [sent for _, sent in candidates[:3]]

    def _find_secondary_examples(
        self,
        key_sentences: list[tuple[float, str]],
        target: str,
        keywords: set,
    ) -> Optional[str]:
        """Cherche des phrases avec des introducteurs d'exemple secondaires.

        Marqueurs secondaires : *notamment*, *tel que*, *y compris*,
        *comme*, *inclut*.

        Args:
            key_sentences: Phrases-clés scorées.
            target: Terme cible.
            keywords: Mots-clés.

        Returns:
            Meilleure phrase, ou None.
        """
        secondary_markers = {
            "notamment", "tel que", "telle que", "tels que", "telles que",
            "y compris", "comme", "inclut", "incluent", "entre autres",
            "particulièrement",
        }

        candidates: list[tuple[float, str]] = []

        for score, sent in key_sentences:
            sent_lower = sent.lower()

            has_marker = any(marker in sent_lower for marker in secondary_markers)
            if not has_marker:
                continue

            bonus = 0.0
            if target and target.lower() in sent_lower:
                bonus += 0.4
            if keywords:
                bonus += _keyword_match_score(sent, keywords) * 0.2

            candidates.append((score + bonus, sent))

        if not candidates:
            return None

        candidates.sort(key=lambda x: -x[0])
        return candidates[0][1]


# ═══════════════════════════════════════════════════════════════════════════
# ── Mapping et dispatch ───────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

# Dictionnaire associant chaque type de question à son implémentation
_STRATEGIES: dict[QuestionType, BaseStrategy] = {
    QuestionType.DEFINITION: DefinitionStrategy(),
    QuestionType.FACTOID: FactoidStrategy(),
    QuestionType.HOW: HowStrategy(),
    QuestionType.WHY: WhyStrategy(),
    QuestionType.LIST: ListStrategy(),
    QuestionType.COMPARISON: ComparisonStrategy(),
    QuestionType.BOOLEAN: BooleanStrategy(),
    QuestionType.SUMMARY: SummaryStrategy(),
    QuestionType.EXAMPLE: ExampleStrategy(),
}


def get_strategies() -> dict[QuestionType, BaseStrategy]:
    """Retourne le mapping complet des types de question → stratégie.

    Permet à l'orchestrateur (``engine``) de récupérer toutes les
    stratégies disponibles.

    Returns:
        Dictionnaire ``{QuestionType: BaseStrategy}``.
    """
    return dict(_STRATEGIES)


def execute_strategy(
    qtype: QuestionType,
    question: QuestionAnalysis,
    analysis: dict,
    docs: list[dict],
) -> dict:
    """Exécute la stratégie appropriée pour le type de question donné.

    Dispatche vers la bonne stratégie et retourne une réponse structurée.
    Si aucune stratégie n'est disponible pour le type, retourne une
    réponse indiquant que la question n'est pas prise en charge.

    Args:
        qtype: Type de question à traiter.
        question: Analyse structurée de la question.
        analysis: Analyse pré-calculée du document principal.
        docs: Liste de documents bruts (texte + métadonnées).

    Returns:
        Dictionnaire de réponse normalisé :
        ``{"answer": str, "sources": list[str], "confidence": float}``.
    """
    strategy = _STRATEGIES.get(qtype)

    if strategy is None:
        # Type non supporté (FORMULA, UNKNOWN, etc.)
        return {
            "answer": (
                f"Je ne peux pas répondre à ce type de question "
                f"(type: {qtype.value}). "
                f"Essayez de reformuler votre demande."
            ),
            "sources": [],
            "confidence": 0.0,
        }

    return strategy.answer(question, analysis, docs)
