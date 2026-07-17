"""📖 Analyse hors ligne des documents pour le Q&A sans LLM.

À l'indexation de chaque document, ce module pré-calcule des
métadonnées riches qui permettront au moteur de Q&A de répondre
sans appel LLM :

- **Phrases-clés** : les phrases les plus représentatives du document
  (score selon position, longueur, mots-cues, couverture lexicale)
- **Définitions** : phrases contenant des motifs définitionnels
  ("X est un/une", "on appelle X", "X désigne", etc.)
- **Entités** : dates, nombres, noms propres détectés par patrons
- **Listes et énumérations** : éléments structurés
- **Structure** : titres de sections, hiérarchie
- **TF/IDF** : termes importants par chunk
- **Formules** : expressions mathématiques détectées

Stockage
--------
L'analyse est stockée dans un dictionnaire rattaché au document.
Elle suit le format ::

    {
        "key_sentences": [(score, sentence), ...],
        "definitions": [(term, definition_sentence), ...],
        "entities": {"dates": [...], "numbers": [...], "proper_nouns": [...]},
        "lists": [{"header": str, "items": [str, ...]}, ...],
        "sections": [{"title": str, "level": int, "sentences": [str, ...]}, ...],
        "chunk_terms": [{"chunk_index": int, "terms": {str: float}, ...}, ...],
        "formulas": [str, ...],
        "important_ngrams": [str, ...],
        "total_sentences": int,
    }
"""

import math
import re
from collections import Counter, defaultdict
from typing import Optional

# ── Constantes ─────────────────────────────────────────────────────────────

# Mots-cues qui indiquent qu'une phrase est importante
_CUE_WORDS = {
    "important", "essentiel", "fondamental", "notamment", "principal",
    "majeur", "crucial", "significatif", "remarquable", "clé",
    "en résumé", "en conclusion", "pour conclure", "ainsi", "donc",
    "par conséquent", "en effet", "c'est pourquoi",
    "à retenir", "important:", "attention:", "note:",
}

# Mots-cues pour détecter les définitions
_DEFINITION_PATTERNS = [
    (r"(?:[Mm]ot\s+)?(?:[Dd]éfinition|défini)\s*(?::|de|\.)\s*(.+?)(?:\.|:)", "definition_heading"),
    (r"(\w+(?:\s+\w+){0,5})\s+est\s+(?:un|une|le|la|les)\s+(.+)", "est_un"),
    (r"(\w+(?:\s+\w+){0,5})\s+sont\s+(?:des|les)\s+(.+)", "sont_des"),
    (r"(\w+(?:\s+\w+){0,5})\s+désigne\s+(.+)", "designe"),
    (r"(\w+(?:\s+\w+){0,5})\s+représente\s+(.+)", "represente"),
    (r"(?:[Oo]n\s+)?appelle\s+(\w+(?:\s+\w+){0,5})\s+(.+)", "appelle"),
    (r"(?:[Pp]ar\s+)?(\w+(?:\s+\w+){0,5})\s+s'entend\s+(.+)", "entend"),
    (r"(?:[Oo]n\s+)?[Dd]éfini[t]{0,2}\s+(\w+(?:\s+\w+){0,5})\s+comme\s+(.+)", "defini_comme"),
    (r"(\w+(?:\s+\w+){0,5})\s+est\s+appel[ée]\s+(.+)", "est_appele"),
    (r"(?:[Ii]l\s+)?[Ss]'agit\s+d'un[ea]?\s+(.+)", "il_s_agit"),
    (r"(?:[Cc]'est|ce\s+sont)\s+(.+?)(?:qui|dont|où|\.)", "c_est"),
    (r"(\w+(?:\s+\w+){0,5})\s+est\s+égal[ée]\s+à\s+(.+)", "est_egal"),
    (r"(?:[Ll]a\s+)?formule\s+(?:de\s+)?(\w+(?:\s+\w+){0,5})\s+est\s+(.+)", "formule_est"),
]

# Patrons pour les formules mathématiques
_FORMULA_PATTERNS = [
    r"[A-Za-z]+\s*[=≈≠]\s*.+",           # a = b
    r"\d+\s*[+\-*/^]\s*\d+\s*[=≈≠]\s*\d+",  # 3 + 4 = 7
    r"[A-Za-z]+\^\{?\d+\}?",               # x², a^2
    r"\\[alpha-beta-gamma-delta].+",       # LaTeX-like
    r"[A-Za-z]+\s*[×x]\s*[A-Za-z]+",       # a × b
    r"\d+%\s+(?:de|d')",                   # 50% de
    r"(?:somme|produit|intégrale|limite|dérivée)\s+(?:de|d')\s+.+",
]

# Stopwords étendus (français)
_STOPWORDS = {
    "le", "la", "les", "des", "une", "dans", "avec", "pour", "sur",
    "dont", "donc", "ainsi", "mais", "donc", "alors", "bien", "très",
    "fait", "être", "peut", "sont", "leur", "nous", "vous", "elles",
    "ils", "elle", "quel", "quels", "quelle", "quelles", "parce",
    "comme", "chez", "sans", "aussi", "ni", "car", "où", "dont",
    "depuis", "pendant", "quand", "après", "avant", "entre",
    "avoir", "faire", "tout", "plus", "cette",
    "c'est", "il", "elle", "on", "ce", "cet", "cette", "ces",
    "aux", "ses", "sa", "son", "leurs", "notre", "votre",
    "est", "sont", "était", "étaient", "été",
    "vers", "par", "sous", "au", "aux", "du", "de", "que",
    "qui", "quoi", "dont", "où", "comment", "pourquoi",
    "ne", "pas", "plus", "moins", "jamais", "rien",
    "si", "lui", "eux", "moi", "toi", "nous", "vous",
    "ça", "cela", "ceci", "celle", "celui", "ceux",
}

# Mots de liaison pour les listes
_LIST_HEADER_WORDS = {
    "premièrement", "deuxièmement", "troisièmement",
    "d'abord", "ensuite", "enfin", "premier", "deuxième",
    "troisième", "1)", "2)", "3)", "a)", "b)", "c)",
    "première", "seconde", "troisième",
    "d'une part", "d'autre part",
}


# ── Analyse principale ─────────────────────────────────────────────────────

def analyze_document_text(text: str, filename: str = "") -> dict:
    """Analyse un document pour en extraire toutes les connaissances utiles.

    Cette fonction est appelée une fois à l'indexation. Elle pré-calcule
    tout ce qui sera nécessaire pour répondre aux questions sans LLM.

    Args:
        text: Texte complet du document.
        filename: Nom du fichier (pour le logging).

    Returns:
        Dict structuré contenant l'analyse complète.
    """
    # Découper en phrases
    sentences = _split_sentences(text)
    if not sentences:
        return _empty_analysis()

    # Découper en sections (par titres)
    sections = _detect_sections(sentences)

    # Extraire les différents types d'information
    definitions = _extract_definitions(sentences)
    key_sentences = _score_key_sentences(sentences)
    entities = _extract_entities(sentences, text)
    lists = _extract_lists(text)
    formulas = _extract_formulas(text)
    important_ngrams = _extract_important_ngrams(text)

    # Analyse par chunk (pour le scoring BM25 enrichi)
    chunk_terms = _analyze_chunks(text)

    return {
        "key_sentences": key_sentences[:20],  # Top 20
        "definitions": definitions,
        "entities": entities,
        "lists": lists,
        "sections": sections,
        "chunk_terms": chunk_terms,
        "formulas": formulas,
        "important_ngrams": important_ngrams[:30],
        "total_sentences": len(sentences),
    }


def _empty_analysis() -> dict:
    """Retourne une analyse vide."""
    return {
        "key_sentences": [],
        "definitions": [],
        "entities": {"dates": [], "numbers": [], "proper_nouns": []},
        "lists": [],
        "sections": [],
        "chunk_terms": [],
        "formulas": [],
        "important_ngrams": [],
        "total_sentences": 0,
    }


# ── Découpage en phrases ──────────────────────────────────────────────────

def _split_sentences(text: str) -> list[str]:
    """Découpe un texte en phrases (robuste pour le français).

    Gère les abréviations courantes (M., Mme, etc.), les points
    de suspension, les points d'exclamation et d'interrogation.

    Args:
        text: Texte à découper.

    Returns:
        Liste de phrases (nettoyées).
    """
    # Protéger les abréviations
    text = re.sub(r'(M|Mme|Mlles|Dr|Pr|St|Ste|ex|fig|cf|e\.g|i\.e)\.', r'\1<ABBR>', text)

    # Protéger les nombres décimaux
    text = re.sub(r'(\d+)\.(\d+)', r'\1<DEC>\2', text)

    # Découper
    raw = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"«(])', text)

    # Restaurer
    result = []
    for s in raw:
        s = s.replace('<ABBR>', '.')
        s = s.replace('<DEC>', '.')
        s = s.strip()
        if s and len(s) > 5:  # Ignorer les très courtes "phrases"
            result.append(s)

    return result


# ── Détection de sections ─────────────────────────────────────────────────

def _detect_sections(sentences: list[str]) -> list[dict]:
    """Détecte la structure hiérarchique du document.

    Une section commence par une ligne qui ressemble à un titre :
    - Texte court (< 80 car.)
    - Pas de ponctuation forte à la fin
    - Commence par un chiffre romain, un nombre, ou un mot-clé

    Args:
        sentences: Liste des phrases.

    Returns:
        Liste de sections avec titre, niveau et contenu.
    """
    sections = []
    current_section = {"title": "Introduction", "level": 1, "sentences": []}

    # Titres probables : motifs de titres de section
    section_pattern = re.compile(
        r'^(?:(?:CHAPITRE|Chapitre|chapitre|SECTION|Section|section|'
        r'PARTIE|Partie|partie|TITRE|Titre|titre|ANNEXE|Annexe|annexe|'
        r'I[VX]?|IV|V|VI{0,3}|[1-9]\d*(?:\.[1-9]\d*)*)\s*[.:]\s*|'
        r'^(?:\d+[.)]\s+[A-Z]))',
        re.IGNORECASE
    )

    for sent in sentences:
        is_title = False

        # Vérifier si c'est un titre
        if len(sent) < 100 and not sent.rstrip().endswith('.'):
            if section_pattern.match(sent) or sent.isupper() or (
                len(sent) < 60 and sent[0].isupper() and sent.count(' ') < 12
            ):
                is_title = True

        # Détecter le niveau (basé sur la numérotation)
        level = 1
        if is_title:
            level = _detect_section_level(sent)

        if is_title:
            sections.append(current_section)
            current_section = {"title": sent, "level": level, "sentences": []}
        else:
            current_section["sentences"].append(sent)

    sections.append(current_section)
    return sections


def _detect_section_level(title: str) -> int:
    """Estime le niveau hiérarchique d'un titre."""
    if re.match(r'^(CHAPITRE|Chapitre|chapitre)', title):
        return 1
    elif re.match(r'^(SECTION|Section|section)', title):
        return 2
    elif re.match(r'^(PARTIE|Partie|partie)', title):
        return 1
    elif re.match(r'^(ANNEXE|Annexe|annexe)', title):
        return 3
    elif re.match(r'^IV|V|VI{0,3}\b', title):
        return 2
    elif re.match(r'^\d+\.[\d.]+\s', title):  # 1.1, 1.2.1
        dots = title.count('.')
        return min(dots + 1, 5)
    elif re.match(r'^\d+[.)]\s', title):
        return 2
    return 3  # Titres non numérotés = sous-section


# ── Extraction de définitions ─────────────────────────────────────────────

def _extract_definitions(sentences: list[str]) -> list[dict]:
    """Extrait les définitions des phrases du document.

    Utilise des patrons linguistiques pour identifier les phrases
    qui définissent un terme.

    Args:
        sentences: Liste des phrases.

    Returns:
        Liste de dicts : {"term": str, "definition": str, "pattern": str}.
    """
    definitions = []
    seen_terms = set()

    for sent in sentences:
        sent_clean = sent.strip()
        if len(sent_clean) < 15:
            continue

        for pattern, pattern_name in _DEFINITION_PATTERNS:
            matches = re.finditer(pattern, sent_clean, re.IGNORECASE)
            for m in matches:
                if pattern_name == "definition_heading":
                    term = m.group(1).split(':')[0].strip() if ':' in m.group(1) else m.group(1).strip()
                    def_text = m.group(1)
                elif pattern_name in ("c_est",):
                    term = m.group(1).split()[0] if m.group(1).split() else m.group(1)
                    def_text = sent_clean
                elif pattern_name == "formule_est":
                    term = m.group(1)
                    def_text = sent_clean
                else:
                    term = m.group(1).strip()
                    def_text = sent_clean

                # Nettoyer le terme
                term_lower = term.lower().strip()
                if (term_lower not in seen_terms
                        and len(term) > 2
                        and not any(c in term for c in "?!=<>")):
                    seen_terms.add(term_lower)
                    definitions.append({
                        "term": term,
                        "definition": def_text.replace("  ", " ").strip(),
                        "pattern": pattern_name,
                    })
                    break  # Une seule définition par phrase

    return definitions


# ── Score des phrases-clés ────────────────────────────────────────────────

def _score_key_sentences(sentences: list[str]) -> list[tuple]:
    """Score chaque phrase selon son importance dans le document.

    Critères de scoring :
    1. Position : les premières et dernières phrases sont plus importantes
    2. Longueur : phrases de taille moyenne (20-60 mots) idéale
    3. Mots-cues : présence de mots indicateurs d'importance
    4. Couverture lexicale : densité de mots rares/d'arrêt
    5. Titre : phrase courte ressemblant à un titre

    Returns:
        Liste de tuples (score, phrase) triée par score décroissant.
    """
    n = len(sentences)
    if n == 0:
        return []

    # Fréquence des mots dans tout le document (pour le scoring TF inverse)
    word_freq = Counter()
    for sent in sentences:
        words = _tokenize(sent)
        word_freq.update(words)

    scored = []
    for i, sent in enumerate(sentences):
        score = 0.0
        words = _tokenize(sent)

        if not words:
            continue

        # 1. Score de position (pics au début et à la fin)
        position_ratio = i / n if n > 1 else 0.5
        if position_ratio < 0.15:       # Parmi les 15% premières
            score += 0.25 * (1 - position_ratio / 0.15)
        elif position_ratio > 0.85:     # Parmi les 15% dernières
            score += 0.15 * ((position_ratio - 0.85) / 0.15)
        elif 0.3 <= position_ratio <= 0.7:
            score += 0.05

        # 2. Score de longueur (20-60 mots = idéal)
        n_words = len(words)
        if 20 <= n_words <= 60:
            score += 0.20
        elif 10 <= n_words < 20:
            score += 0.10
        elif 60 < n_words <= 80:
            score += 0.10

        # 3. Mots-cues
        sent_lower = sent.lower()
        cue_matches = sum(1 for cue in _CUE_WORDS if cue in sent_lower)
        score += min(cue_matches * 0.15, 0.45)

        # 4. Couverture lexicale : mots rares ont plus de poids
        #    Mesure : proportion de mots hors stopwords
        non_stop = [w for w in words if w.lower() not in _STOPWORDS]
        if non_stop:
            rare_ratio = len(non_stop) / len(words)
            score += rare_ratio * 0.10

        # 5. Termes importants (TF-IDF simplifié)
        #    Bonus si la phrase contient plusieurs termes fréquents mais spécifiques
        total_words = sum(word_freq.values())
        if total_words > 0:
            specific_score = 0
            for w in set(words):
                if w in word_freq and word_freq[w] <= max(3, n * 0.1):
                    # Mot rare dans le document → spécifique
                    specific_score += 0.02
            score += min(specific_score, 0.20)

        # 6. Pénalité pour les phrases trop courtes ou trop longues
        if n_words < 5:
            score -= 0.3
        if n_words > 100:
            score -= 0.2

        scored.append((max(score, 0), sent))

    # Trier par score décroissant
    scored.sort(key=lambda x: -x[0])
    return scored


# ── Extraction d'entités ──────────────────────────────────────────────────

def _extract_entities(sentences: list[str], text: str) -> dict:
    """Extrait les entités du document (dates, nombres, noms propres).

    Args:
        sentences: Liste des phrases.
        text: Texte complet.

    Returns:
        Dict avec "dates", "numbers", "proper_nouns".
    """
    dates = set()
    numbers = set()
    proper_nouns = set()

    # ── Dates ──────────────────────────────────────────────────────────
    # Formats français courants
    date_patterns = [
        r'\d{1,2}\s*(?:janvier|février|mars|avril|mai|juin|juillet|août|'
        r'septembre|octobre|novembre|décembre)\s*\d{4}',
        r'\d{1,2}/\d{1,2}/\d{4}',
        r'\d{4}-\d{2}-\d{2}',
        r'(?:en|au)\s+\d{4}',
        r'(?:XXe|XIXe|XVIIIe|XVIe|XVe|XIVe|XIIIe|XIIe|XIe|Xe|IXe|VIIIe|VIIe|VIe|Ve|IVe|IIIe|IIe|Ier)\s+siècle',
    ]
    for pat in date_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            dates.add(m.group().strip())

    # ── Nombres ────────────────────────────────────────────────────────
    # Nombres entiers et décimaux significatifs
    for m in re.finditer(r'\b\d+(?:[.,]\d+)?\s*(?:%|€|°C|km|m|cm|mm|kg|g|h|min)\b', text):
        numbers.add(m.group().strip())
    # Grands nombres (> 99)
    for m in re.finditer(r'\b(?:1\d{2,}|[2-9]\d{2,})\b', text):
        numbers.add(m.group().strip())

    # ── Noms propres (mots avec majuscule qui ne sont pas en début de phrase) ──
    # Approche simple : mots avec majuscule hors début de phrase
    for sent in sentences:
        words = sent.split()
        for w in words[1:]:  # Ignorer le premier mot (début de phrase)
            w_clean = w.strip('"\'"(),;:!?.-')
            if (w_clean
                    and w_clean[0].isupper()
                    and not w_clean.isupper()
                    and w_clean.lower() not in _STOPWORDS
                    and len(w_clean) > 2):
                proper_nouns.add(w_clean)

    return {
        "dates": sorted(dates),
        "numbers": sorted(numbers),
        "proper_nouns": sorted(proper_nouns),
    }


# ── Détection de listes ───────────────────────────────────────────────────

def _extract_lists(text: str) -> list[dict]:
    """Détecte les énumérations et listes structurées dans le texte.

    Détecte :
    - Listes à puces (items commençant par -, *, •)
    - Listes numérotées (1., 2., etc.)
    - Listes introduites par deux-points + items séparés par des points-virgules

    Args:
        text: Texte complet.

    Returns:
        Liste de dicts {"header": str, "items": [str, ...]}.
    """
    lists = []
    lines = text.split('\n')

    # Liste à puces
    bullet_items = []
    header = ""
    in_bullet = False

    for line in lines:
        line_stripped = line.strip()

        # Détecter un item de liste à puce
        if re.match(r'^[\s]*[-*•]\s+', line):
            item = re.sub(r'^[\s]*[-*•]\s+', '', line_stripped)
            if not in_bullet and bullet_items:
                # Sauvegarder la liste précédente
                lists.append({"header": header, "items": bullet_items})
                bullet_items = []
                header = ""
            in_bullet = True
            bullet_items.append(item)
        elif re.match(r'^\s*\d+[.)]\s+', line):
            item = re.sub(r'^\s*\d+[.)]\s+', '', line_stripped)
            if not in_bullet and bullet_items:
                lists.append({"header": header, "items": bullet_items})
                bullet_items = []
                header = ""
            in_bullet = True
            bullet_items.append(item)
        elif in_bullet and line_stripped and not re.match(r'^[\s]*[-*•]', line):
            # Nouvelle section : sauvegarder la liste et recommencer
            if bullet_items:
                lists.append({"header": header, "items": bullet_items})
                bullet_items = []
                header = ""
            in_bullet = False
        elif not in_bullet and line_stripped and not re.match(r'^[\s]*[-*•]', line):
            # Ligne normale : potentiel header pour la prochaine liste
            if not bullet_items:
                header = line_stripped

    # Dernière liste
    if bullet_items:
        lists.append({"header": header, "items": bullet_items})

    return lists


# ── Détection de formules ─────────────────────────────────────────────────

def _extract_formulas(text: str) -> list[str]:
    """Détecte les formules et expressions mathématiques.

    Args:
        text: Texte complet.

    Returns:
        Liste de formules détectées.
    """
    formulas = set()
    for pattern in _FORMULA_PATTERNS:
        for m in re.finditer(pattern, text, re.MULTILINE):
            formula = m.group().strip()
            if 5 < len(formula) < 200:
                formulas.add(formula)
    return sorted(formulas)


# ── Extraction de n-grammes importants ───────────────────────────────────

def _extract_important_ngrams(text: str, max_ngram: int = 4) -> list[str]:
    """Extrait les n-grammes (bi/tri/quadri-grammes) les plus fréquents.

    Cela capture les concepts multi-mots comme "théorème de Pythagore",
    "réaction chimique", "guerre mondiale", etc.

    Args:
        text: Texte complet.
        max_ngram: Taille max des n-grammes.

    Returns:
        Liste des n-grammes les plus fréquents (triée par fréquence).
    """
    words = _tokenize(text)
    if len(words) < 3:
        return []

    ngram_counts: Counter = Counter()

    for n in range(2, max_ngram + 1):
        for i in range(len(words) - n + 1):
            ngram = ' '.join(words[i:i + n])
            # Ne garder que si au moins un mot hors stopwords
            ngram_words = ngram.split()
            non_stop = sum(1 for w in ngram_words if w.lower() not in _STOPWORDS)
            if non_stop >= max(1, n - 1):  # Au moins n-1 mots significatifs
                ngram_counts[ngram] += 1

    # Filtrer et trier
    min_freq = max(2, len(words) // 200)
    important = [gram for gram, count in ngram_counts.most_common(50)
                 if count >= min_freq]
    return important


# ── Analyse par chunk (pour retrieval) ─────────────────────────────────────

def _analyze_chunks(text: str, chunk_size: int = 500) -> list[dict]:
    """Analyse le vocabulaire de chaque chunk pour le scoring enrichi.

    Pour chaque chunk, calcule :
    - Les termes avec leur poids TF normalisé
    - La couverture lexicale

    Args:
        text: Texte complet.
        chunk_size: Nombre de mots par chunk.

    Returns:
        Liste d'analyses par chunk.
    """
    from core.document_store import chunk_text as split_chunks

    chunks = split_chunks(text, chunk_size=chunk_size)
    result = []

    for i, chunk in enumerate(chunks):
        words = _tokenize(chunk)
        if not words:
            continue

        # TF (normalisé)
        word_counts = Counter(words)
        max_count = max(word_counts.values()) if word_counts else 1
        terms = {
            w: count / max_count
            for w, count in word_counts.items()
            if w.lower() not in _STOPWORDS
        }

        # Moyenne des poids
        avg_weight = sum(terms.values()) / len(terms) if terms else 0

        result.append({
            "chunk_index": i,
            "terms": terms,
            "total_terms": len(terms),
            "avg_weight": avg_weight,
        })

    return result


# ── Utilitaires ───────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Tokenise un texte en mots (minuscules, sans ponctuation)."""
    return re.findall(r"[a-zA-ZéèêëàâîïôûùçÉÈÊËÀÂÎÏÔÛÙÇ0-9]+", text.lower())


def normalize_term(term: str) -> str:
    """Normalise un terme pour la recherche (singulier/pluriel simple)."""
    term = term.lower().strip()
    # Pluriel simple français
    if term.endswith('s') and not term.endswith('ss'):
        term = term[:-1]
    if term.endswith('aux'):
        term = term[:-2] + 'al'
    return term


def sentences_containing(text: str, keywords: set, max_results: int = 10) -> list[str]:
    """Trouve les phrases contenant le plus de mots-clés donnés.

    Args:
        text: Texte dans lequel chercher.
        keywords: Mots-clés à rechercher.
        max_results: Nombre max de phrases.

    Returns:
        Phrases triées par nombre de mots-clés présents.
    """
    sentences = _split_sentences(text)
    scored = []
    for sent in sentences:
        sent_lower = sent.lower()
        # Score : nombre de mots-clés + bonus pour la proximité
        kw_present = [k for k in keywords if k in sent_lower]
        if kw_present:
            # Bonus de proximité : si les mots-clés sont proches
            positions = []
            for k in kw_present:
                pos = sent_lower.index(k)
                positions.append(pos)
            proximity_bonus = 0
            if len(positions) > 1:
                max_dist = max(positions) - min(positions)
                if max_dist < 100:
                    proximity_bonus = 0.3
                elif max_dist < 200:
                    proximity_bonus = 0.1
            score = len(kw_present) + proximity_bonus
            scored.append((score, sent))

    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored[:max_results]]
