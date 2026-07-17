"""❓ Analyse et classification des questions pour le Q&A sans LLM.

Ce module analyse une question en langage naturel pour déterminer :

1. **Type de question** : définition, fait, comment, pourquoi, liste,
   comparaison, booléenne, résumé, formule
2. **Mots-clés et phrases-clés** : termes importants pour la recherche
3. **Terme cible** : le sujet principal de la question
4. **Attentes de réponse** : ce que l'utilisateur veut obtenir
5. **Négation** : présence de négation qui inverse le sens
6. **Question scope** : large (résumé) vs spécifique (fait)
"""

import re
from enum import Enum
from typing import Optional


class QuestionType(str, Enum):
    """Types de questions que le système peut traiter."""
    DEFINITION = "definition"       # "Qu'est-ce que X?", "Définis X"
    FACTOID = "factoid"             # "Qui a inventé X?", "Quand a eu lieu X?"
    HOW = "how"                     # "Comment fonctionne X?", "Comment calculer X?"
    WHY = "why"                     # "Pourquoi X?", "Quelle est la cause de X?"
    LIST = "list"                   # "Cite les types de X", "Quels sont les X?"
    COMPARISON = "comparison"       # "Différence entre X et Y?"
    BOOLEAN = "boolean"             # "Est-ce que X?", "X est-il vrai?"
    SUMMARY = "summary"             # "Résume X", "Quels sont les points clés?"
    FORMULA = "formula"             # "Quelle est la formule de X?"
    EXAMPLE = "example"             # "Donne un exemple de X"
    UNKNOWN = "unknown"             # Question non classifiée


class QuestionAnalysis:
    """Analyse complète d'une question.

    Attributes:
        original: Texte original de la question.
        question_type: Type classifié de la question.
        keywords: Mots-clés significatifs (minuscules, sans stopwords).
        target_term: Terme central de la question (si applicable).
        secondary_term: Second terme (comparaison, relation).
        has_negation: True si la question contient une négation.
        answer_expectation: Description de ce qui est attendu.
        confidence: Score de confiance de l'analyse (0-1).
        sub_type: Sous-type plus précis (ex: "who", "what", "when").
    """

    def __init__(
        self,
        original: str,
        question_type: QuestionType = QuestionType.UNKNOWN,
        keywords: set = None,
        target_term: str = "",
        secondary_term: str = "",
        has_negation: bool = False,
        answer_expectation: str = "",
        confidence: float = 0.0,
        sub_type: str = "",
    ):
        self.original = original
        self.question_type = question_type
        self.keywords = keywords or set()
        self.target_term = target_term
        self.secondary_term = secondary_term
        self.has_negation = has_negation
        self.answer_expectation = answer_expectation
        self.confidence = confidence
        self.sub_type = sub_type

    def __repr__(self) -> str:
        return (
            f"QuestionAnalysis(type={self.question_type.value}, "
            f"target='{self.target_term}', "
            f"conf={self.confidence:.2f})"
        )


# ── Stopwords ─────────────────────────────────────────────────────────────

_STOPWORDS = {
    "le", "la", "les", "des", "une", "dans", "avec", "pour", "sur",
    "dont", "donc", "ainsi", "mais", "alors", "bien", "très",
    "fait", "être", "peut", "sont", "leur", "nous", "vous", "elles",
    "ils", "elle", "quel", "quels", "quelle", "quelles", "parce",
    "comme", "chez", "sans", "aussi", "ni", "car", "où",
    "depuis", "pendant", "quand", "après", "avant", "entre",
    "avoir", "faire", "tout", "plus", "cette",
    "est", "sont", "était", "étaient", "été",
    "vers", "par", "sous", "au", "aux", "du", "de", "que",
    "qui", "quoi", "comment", "pourquoi",
    "ne", "pas", "plus", "moins", "jamais", "rien",
}


# ── Patrons de classification ─────────────────────────────────────────────

# Chaque type de question a des motifs de reconnaissance
# Format : (pattern_regex, sous_type, poids)

_DEFINITION_PATTERNS = [
    (r"(?:qu'est-ce\s+que|qu'est-ce\s+qu')(?:\s+c'est que\s+)?\s*(.+)", "what_is", 1.0),
    (r"définis?\s+(?:le|la|l'|les)?\s*(.+)", "define", 1.0),
    (r"définition\s+(?:de\s+)?(.+)", "definition_of", 1.0),
    (r"(?:que\s+signifie|que\s+veut\s+dire)\s+(.+)", "meaning", 1.0),
    (r"c'est\s+quoi\s+(.+)", "what_is_informal", 0.9),
    (r"explique?\s+(?:moi\s+)?(?:ce\s+qu'est\s+ce\s+que|ce\s+que)\s+(.+)", "explain_what", 0.9),
    (r"(?:donne|donner)\s+(?:moi\s+)?(?:la\s+)?définition\s+(?:de\s+)?(.+)", "give_definition", 1.0),
]

_FACTOID_PATTERNS = [
    (r"qui\s+(?:a|est|sont|ont|était|étaient|fut)\s+(.+)", "who", 1.0),
    (r"(?:par\s+)?qui\s+(?:a\s+)?(?:été\s+)?(.+)", "by_whom", 0.9),
    (r" quand\s+(?:a|est-ce\s+que|ont|était|ont\s+été)\s+(.+)", "when", 1.0),
    (r" à\s+quelle\s+(?:date|époque|année|moment)\s+(.+)", "when", 0.9),
    (r" en\s+quelle\s+année\s+(.+)", "when_year", 0.9),
    (r" où\s+(?:a|est|se\s+trouve|se\s+situe|ont|étaient)\s+(.+)", "where", 1.0),
    (r" (?:dans\s+)?quel\s+(?:lieu|endroit|pays|ville|région)\s+(.+)", "where", 0.9),
    (r"combien\s+(?:de|d')\s*(.+)", "how_many", 1.0),
    (r"quel\s+(?:est\s+)?(?:le\s+)?nombre\s+(?:de\s+)?(.+)", "how_many", 0.9),
]

_HOW_PATTERNS = [
    (r"comment\s+(?:faire|calculer|mesurer|trouver|obtenir|résoudre)\s+(.+)", "how_to", 1.0),
    (r"comment\s+(?:fonctionne|marcher|fonctionnait)\s+(.+)", "how_works", 1.0),
    (r"(?:de\s+)?quelle\s+(?:manière|façon|manière|façon)\s+(.+)", "how_manner", 0.8),
    (r"comment\s+(?:expliquer|décrire)\s+(.+)", "how_explain", 0.7),
    (r" quelle\s+est\s+la\s+(?:méthode|procédure|technique|marche\s+à\s+suivre)\s+(?:pour\s+)?(.+)", "how_method", 0.9),
    (r"comment\s+(?:se\s+)?(?:déroule|passe)\s+(.+)", "how_process", 0.8),
    (r"quelles\s+sont\s+les\s+(?:étapes|phases)\s+(?:de\s+)?(.+)", "how_steps", 0.9),
]

_WHY_PATTERNS = [
    (r" pourquoi\s+(.+)", "why", 1.0),
    (r" quelle\s+est\s+la\s+(?:raison|cause|explication|origine)\s+(?:de\s+|pour\s+)?(.+)", "why_reason", 1.0),
    (r" pour\s+quelle\s+(?:raison|cause|motif)\s+(.+)", "why_reason", 0.9),
    (r"comment\s+se\s+fait-il\s+que\s+(.+)", "why_explain", 0.7),
    (r"d'où\s+vient\s+(?:que\s+)?(.+)", "why_origin", 0.8),
]

_LIST_PATTERNS = [
    (r"(?:cite|citez|citer|énumère|énumérez|liste|listez)\s+(?:moi\s+)?(?:les|des)\s+(.+)", "list", 1.0),
    (r"quels\s+sont\s+(?:les|des)\s+(.+)", "list_what", 1.0),
    (r"quelles\s+sont\s+(?:les|des)\s+(.+)", "list_what_f", 1.0),
    (r"(?:donne|donner|donnez)\s+(?:moi\s+)?(?:la\s+)?liste\s+(?:des|de)\s+(.+)", "give_list", 1.0),
    (r"(?:quels|quelles)\s+(?:sont\s+)?(?:les\s+)?différents?\s+(?:types|sortes|catégories|formes|espèces)\s+(?:de\s+)?(.+)", "list_types", 1.0),
    (r"nomme\s+(?:moi\s+)?(?:les|des)\s+(.+)", "list_name", 0.9),
]

_COMPARISON_PATTERNS = [
    (r"(?:différence|différences)\s+(?:entre|de)\s+(.+?)(?:\s+et\s+|\s+vs\s+|\s+ou\s+)(.+)", "difference", 1.0),
    (r"(?:comparer|compare|comparaison)\s+(?:entre\s+)?(.+?)(?:\s+et\s+|\s+vs\s+|\s+ou\s+)(.+)", "compare", 1.0),
    (r"(?:point[s]?\s+commun[s]?|ressemblance[s]?)\s+(?:entre|de)\s+(.+?)(?:\s+et\s+|\s+vs\s+|\s+ou\s+)(.+)", "similarity", 1.0),
    (r"qu[ea]l\s+est\s+le\s+(?:meilleur|pire|plus\s+\w+)\s+(?:entre|de)\s+(.+?)(?:\s+et\s+|\s+vs\s+|\s+ou\s+)(.+)", "which_better", 0.8),
    (r"qu[ea]l\s+(?:est\s+)?la\s+différence\s+(.+)", "difference_what", 0.7),
]

_BOOLEAN_PATTERNS = [
    (r"est-ce\s+que\s+(.+)", "yes_no", 1.0),
    (r"est-il\s+(vrai|exact|juste|possible)\s+(?:que\s+)?(.+)", "is_it_true", 0.9),
    (r"(?:existe-t-il|existe-t-elle)\s+(.+)", "does_exist", 0.9),
    (r"(?:(.+?)\s+)?est\s+(?:elle\s+)?vraie?\s*(?:\?|\.)?$", "is_true", 0.8),
    (r"(?:peut-on|peut-il|peut-elle)\s+(.+)", "can_one", 0.8),
    (r"y\s+a-t-il\s+(.+)", "is_there", 0.9),
    (r"(?:est-ce\s+)?vrai\s+(?:que\s+)?(.+)", "true_that", 0.8),
]

_SUMMARY_PATTERNS = [
    (r"(?:résume|résumez|résumer|synthétise|synthétiser)\s+(?:moi\s+)?(.+)", "summarize", 1.0),
    (r"quels\s+sont\s+les\s+(?:points\s+)?(?:clés|essentiels|importants|principaux)\s+(?:de|dans)\s+(.+)", "key_points", 1.0),
    (r"quel\s+est\s+le\s+(?:résumé|but|sujet|contenu)\s+(?:de|du)\s+(.+)", "summary_of", 0.9),
    (r"peux-tu\s+(?:me\s+)?(?:résumer|synthétiser|expliquer)\s+(.+)", "can_summarize", 0.8),
    (r"(?:l'essentiel|les\s+points\s+importants)\s+(?:sur|de|dans)\s+(.+)", "essential", 0.7),
]

_FORMULA_PATTERNS = [
    (r"quelle\s+est\s+la\s+formule\s+(?:de|du|d'|pour)\s+(.+)", "formula_of", 1.0),
    (r"(?:donne|donner|donnez)\s+(?:moi\s+)?la\s+formule\s+(?:de\s+)?(.+)", "give_formula", 1.0),
    (r"comment\s+(?:calculer|calcule)\s+(?:-t-on\s+)?(.+)", "how_calculate", 1.0),
    (r"(?:quelle\s+)?formule\s+(?:mathématique|chimique|physique)\s+(?:de\s+)?(.+)", "math_formula", 0.9),
    (r"quelle\s+est\s+l'équation\s+(?:de|du|d')\s+(.+)", "equation_of", 1.0),
]

_EXAMPLE_PATTERNS = [
    (r"(?:donne|donner|donnez)\s+(?:moi\s+)?(?:un\s+)?exemple\s+(?:de|d'|concret\s+)?(.+)", "give_example", 1.0),
    (r"(?:cite|citer|citez)\s+(?:un\s+)?exemple\s+(?:de\s+)?(.+)", "cite_example", 1.0),
    (r"illustre?\s+(?:par\s+)?(?:un\s+)?exemple\s+(.+)", "illustrate", 0.9),
    (r"(?:pourrais-tu|peux-tu)\s+(?:me\s+)?donner\s+(?:un\s+)?exemple\s+(?:de\s+)?(.+)", "example_please", 0.9),
]

# Tous les patterns groupés par type
_ALL_PATTERNS = [
    (QuestionType.DEFINITION, _DEFINITION_PATTERNS),
    (QuestionType.FACTOID, _FACTOID_PATTERNS),
    (QuestionType.HOW, _HOW_PATTERNS),
    (QuestionType.WHY, _WHY_PATTERNS),
    (QuestionType.LIST, _LIST_PATTERNS),
    (QuestionType.COMPARISON, _COMPARISON_PATTERNS),
    (QuestionType.BOOLEAN, _BOOLEAN_PATTERNS),
    (QuestionType.SUMMARY, _SUMMARY_PATTERNS),
    (QuestionType.FORMULA, _FORMULA_PATTERNS),
    (QuestionType.EXAMPLE, _EXAMPLE_PATTERNS),
]

# Mots de négation
_NEGATION_WORDS = {
    "ne", "pas", "plus", "jamais", "rien", "personne", "aucun",
    "aucune", "ni", "nul", "nulle", "sans", "guère",
}


# ── Analyseurs ────────────────────────────────────────────────────────────

def analyze_question(question: str) -> QuestionAnalysis:
    """Analyse complète d'une question posée par l'utilisateur.

    Détermine le type, les mots-clés, le terme cible, et la confiance.

    Args:
        question: Question en langage naturel.

    Returns:
        QuestionAnalysis structurée.
    """
    original = question.strip()
    question_lower = original.lower()

    # Extraction des mots-clés
    keywords = _extract_keywords(question_lower)

    # Détection de négation
    has_negation = any(word in question_lower.split() for word in _NEGATION_WORDS)

    # Classification du type de question
    best_type = QuestionType.UNKNOWN
    best_subtype = ""
    best_confidence = 0.0
    best_target = ""
    best_secondary = ""
    best_expectation = ""

    # Essayer chaque type de pattern
    for qtype, patterns in _ALL_PATTERNS:
        for pattern, subtype, weight in patterns:
            m = re.search(pattern, question_lower)
            if m:
                target = m.group(1).strip() if m.lastindex and m.group(1) else ""
                groups = m.groups()

                # Pour les comparaisons, extraire les deux termes
                secondary = ""
                if qtype == QuestionType.COMPARISON and len(groups) >= 2:
                    target = groups[0].strip()
                    secondary = groups[1].strip()

                confidence = weight * _estimate_pattern_reliability(
                    question, pattern, qtype
                )

                if confidence > best_confidence:
                    best_type = qtype
                    best_subtype = subtype
                    best_confidence = confidence
                    best_target = target
                    best_secondary = secondary
                    best_expectation = _get_expectation(qtype, subtype, target)

    # Si aucun pattern n'a matché, essayer la détection par mot interrogatif
    if best_confidence < 0.3:
        best_type, best_subtype, best_confidence, best_target = \
            _detect_by_interrogative(question_lower, keywords)

    # Nettoyer le terme cible
    best_target = _clean_target(best_target)

    return QuestionAnalysis(
        original=original,
        question_type=best_type,
        keywords=keywords,
        target_term=best_target,
        secondary_term=best_secondary,
        has_negation=has_negation,
        answer_expectation=best_expectation,
        confidence=best_confidence,
        sub_type=best_subtype,
    )


def _extract_keywords(text: str) -> set:
    """Extrait les mots-clés significatifs d'un texte.

    Garde les mots de 3+ caractères hors stopwords.
    Inclut les bigrammes significatifs.

    Args:
        text: Texte (en minuscules).

    Returns:
        Set de mots-clés et bigrammes.
    """
    words = re.findall(r"[a-zA-ZéèêëàâîïôûùçÉÈÊËÀÂÎÏÔÛÙÇ0-9]+", text.lower())
    keywords = {w for w in words if w not in _STOPWORDS and len(w) >= 3}

    # Ajouter les bigrammes significatifs
    for i in range(len(words) - 1):
        if (words[i] not in _STOPWORDS or words[i + 1] not in _STOPWORDS):
            bigram = f"{words[i]} {words[i + 1]}"
            # Garder les bigrammes avec au moins un mot significatif
            non_stop = sum(1 for w in bigram.split() if w not in _STOPWORDS)
            if non_stop >= 1:
                keywords.add(bigram)

    return keywords


def _estimate_pattern_reliability(
    question: str, pattern: str, qtype: QuestionType
) -> float:
    """Estime la fiabilité d'un match de pattern.

    Pénalise les faux positifs (ex: "Quels sont les..." pour une question
    qui est en fait une définition).

    Args:
        question: Question complète.
        pattern: Pattern regex qui a matché.
        qtype: Type de question associé.

    Returns:
        Score de fiabilité entre 0 et 1.
    """
    q_lower = question.lower()

    # Facteurs de pénalisation
    penalties = 0.0

    # Une question courte avec un pattern long est suspecte
    if len(question) < 15 and len(pattern) > 30:
        penalties += 0.2

    # Mélange de motifs interrogatifs
    interrogative_count = sum(
        1 for w in ["qui", "quoi", "quand", "où", "comment", "pourquoi", "quel", "quelle", "quels", "quelles"]
        if w in q_lower
    )
    if interrogative_count > 1:
        penalties += 0.1

    # Si le type est FACTOID mais que la question utilise "qu'est-ce que"
    if qtype == QuestionType.FACTOID and ("qu'est-ce" in q_lower or "c'est quoi" in q_lower):
        penalties += 0.3  # Plus probablement une définition

    return max(1.0 - penalties, 0.3)


def _detect_by_interrogative(
    question: str, keywords: set
) -> tuple:
    """Détection par mot interrogatif quand les patterns échouent.

    Returns:
        (type, sub_type, confidence, target)
    """
    q = question.strip().lower()

    # Mots interrogatifs initiaux
    if q.startswith("qui") and not q.startswith("quitt"):
        return (QuestionType.FACTOID, "who", 0.6, q[3:].strip().lstrip(" ,est"))
    if q.startswith("que ") or q.startswith("qu'est-ce que"):
        return (QuestionType.DEFINITION, "what_is", 0.6, q.split("que", 1)[-1].strip())
    if q.startswith("quand"):
        return (QuestionType.FACTOID, "when", 0.6, q[5:].strip().lstrip(" ,est"))
    if q.startswith("où"):
        return (QuestionType.FACTOID, "where", 0.6, q[1:].strip().lstrip(" ,se"))
    if q.startswith("comment"):
        return (QuestionType.HOW, "how_general", 0.5, q[7:].strip().lstrip(" ,est"))
    if q.startswith("pourquoi"):
        return (QuestionType.WHY, "why_general", 0.5, q[8:].strip().lstrip(" ,est"))
    if q.startswith("combien"):
        return (QuestionType.FACTOID, "how_many", 0.6, q[7:].strip().lstrip(" ,de"))
    if q.startswith("quel") or q.startswith("quelle"):
        return (QuestionType.LIST, "list_what", 0.5, q.split(" ", 1)[-1].strip())
    if q.startswith("est-ce"):
        return (QuestionType.BOOLEAN, "yes_no_general", 0.5, q[6:].strip())

    # Fallback : type inconnu
    return (QuestionType.UNKNOWN, "", 0.0, "")


def _get_expectation(qtype: QuestionType, subtype: str, target: str) -> str:
    """Génère une description lisible de ce qui est attendu.

    Args:
        qtype: Type de question.
        subtype: Sous-type.
        target: Terme cible.

    Returns:
        Description textuelle.
    """
    expectations = {
        QuestionType.DEFINITION: f"La définition de «{target}»",
        QuestionType.FACTOID: "Un fait spécifique",
        QuestionType.HOW: f"La méthode ou procédure pour {target}" if target else "Une explication de processus",
        QuestionType.WHY: f"La raison ou cause de {target}",
        QuestionType.LIST: f"La liste des éléments de {target}",
        QuestionType.COMPARISON: f"La comparaison entre {target}",
        QuestionType.BOOLEAN: f"Confirmation ou infirmation de la proposition",
        QuestionType.SUMMARY: f"Le résumé de {target}",
        QuestionType.FORMULA: f"La formule de {target}",
        QuestionType.EXAMPLE: f"Un exemple de {target}",
        QuestionType.UNKNOWN: "Réponse générale",
    }
    return expectations.get(qtype, "Réponse générale")


def _clean_target(target: str) -> str:
    """Nettoie le terme cible extrait.

    Enlève les mots de liaison résiduels, la ponctuation.

    Args:
        target: Terme cible brut.

    Returns:
        Terme cible nettoyé.
    """
    if not target:
        return ""

    # Enlever les mots de liaison initiaux
    target = re.sub(
        r'^(?:(?:c\'est\s+)?(?:que\s+)?(?:le\s+|la\s+|l\'|les\s+|des\s+|un\s+|une\s+))+',
        '', target
    )

    # Enlever la ponctuation finale
    target = target.strip().rstrip('?,!;:.«»"\'')

    # Limiter la longueur
    words = target.split()
    if len(words) > 8:
        target = ' '.join(words[:8])

    return target.strip()


def get_search_terms(analysis: QuestionAnalysis) -> list[str]:
    """Convertit une analyse en termes de recherche prioritaires.

    Ordonne les termes par importance pour la recherche documentaire.

    Args:
        analysis: Analyse de la question.

    Returns:
        Liste de termes priorisés.
    """
    terms = []

    # 1. Terme cible (priorité maximale)
    if analysis.target_term:
        terms.append(analysis.target_term)

    # 2. Bigrammes des mots-clés
    bigrams = [k for k in analysis.keywords if ' ' in k]
    terms.extend(bigrams)

    # 3. Mots-clés simples
    single_words = [k for k in analysis.keywords if ' ' not in k]
    terms.extend(single_words)

    # 4. Pour les questions de type FORMULA, ajouter un indicateur
    if analysis.question_type == QuestionType.FORMULA:
        terms.extend(["formule", "formula", analysis.target_term])

    # 5. Pour les questions de type DEFINITION, ajouter des indices
    if analysis.question_type == QuestionType.DEFINITION:
        terms.append("est")
        if analysis.target_term:
            terms.append(f"{analysis.target_term} est")

    return terms
