"""🔍 Recherche avancée dans les documents pour le Q&A sans LLM.

Module de retrieval qui implémente la recherche par BM25, correspondance
de phrases exactes, scoring de proximité, et bonus structurels.

Ce module s'appuie sur le ``document_store`` existant tout en ajoutant
des techniques de recherche d'information plus sophistiquées :
  - BM25 scoring (implémentation pure Python, pas de lib externe)
  - Phrase matching avec bonus pour les bigrammes exacts
  - Proximité entre mots-clés dans un même chunk
  - Section-aware scoring (bonus intra-section)
  - Title matching (bonus si les mots-clés apparaissent dans un titre)

Fonctions principales
---------------------
search_documents       → Recherche BM25 enrichie, retourne les meilleurs chunks
batch_retrieve_paragraphs → Version paragraphes (fusion de chunks adjacents)
find_exact_phrase      → Recherche textuelle de phrase exacte
score_by_term_proximity → Score de proximité entre mots-clés
"""

import math
import re
from collections import defaultdict
from typing import Optional

from .question_analyzer import QuestionAnalysis


# ── Constantes BM25 ────────────────────────────────────────────────────────

_K1 = 1.5       # Paramètre de saturation TF (BM25)
_B = 0.75       # Paramètre de normalisation de longueur (BM25)

# ── Bonus de scoring ───────────────────────────────────────────────────────

_PHRASE_BONUS = 0.3          # Bonus pour bigramme exact dans le chunk
_TITLE_BONUS = 0.2           # Bonus si les mots-clés sont dans le titre
_SECTION_BONUS = 0.1         # Bonus pour chunk dans une section déjà bien scorée
_PROXIMITY_BONUS_MAX = 0.25  # Max du bonus de proximité entre mots-clés

# ── Fallback ───────────────────────────────────────────────────────────────

_DEFAULT_AVG_DOC_LEN = 100.0

# ── Patrons de titres de section ───────────────────────────────────────────

_SECTION_PATTERNS = re.compile(
    r'^(?:'
    r'(?:CHAPITRE|Chapitre|chapitre|SECTION|Section|section|'
    r'PARTIE|Partie|partie|TITRE|Titre|titre|ANNEXE|Annexe|annexe)'
    r'(?:\s+\d+(?:\.\d+)*)?'    # numéro de section optionnel
    r'\s*[.:]\s+|'               # séparateur ": " ou ". "
    r'(?:I[VX]?|IV|V|VI{0,3})\s*[.:]\s*|'   # chiffres romains
    r'[1-9]\d*(?:\.[1-9]\d*)*\s*[.:]\s*|'    # numérotation 1.1, 1.2
    r'\d+[.)]\s+[A-Z]'           # liste numérotée "1) Titre"
    r')',
    re.IGNORECASE,
)

# ── Stopwords pour le scoring de proximité ─────────────────────────────────

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
    "c'est", "il", "elle", "on", "ce", "cet", "cette", "ces",
    "aux", "ses", "sa", "son", "leurs", "notre", "votre",
    "si", "lui", "eux", "moi", "toi", "nous", "vous",
    "ça", "cela", "ceci", "celle", "celui", "ceux",
}


# ───────────────────────────────────────────────────────────────────────────
# Utilitaires de texte
# ───────────────────────────────────────────────────────────────────────────


def _tokenize(text: str) -> list[str]:
    """Tokenise un texte en mots (minuscules, sans ponctuation)."""
    return re.findall(r"[a-zA-ZéèêëàâîïôûùçÉÈÊËÀÂÎÏÔÛÙÇ0-9]+", text.lower())


def _get_bigrams(text: str) -> list[str]:
    """Extrait les bigrammes (paires de mots consécutifs) d'un texte.

    Args:
        text: Texte à bigrammiser.

    Returns:
        Liste de bigrammes ``["mot1 mot2", "mot2 mot3", ...]``.
    """
    words = _tokenize(text)
    return [f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1)]


def _remove_stopwords(words: list[str]) -> list[str]:
    """Filtre les stopwords d'une liste de mots.

    Args:
        words: Liste de mots (déjà tokenisés).

    Returns:
        Mots hors stopwords, dans l'ordre original.
    """
    return [w for w in words if w not in _STOPWORDS]


# ───────────────────────────────────────────────────────────────────────────
# Détection de sections dans les chunks
# ───────────────────────────────────────────────────────────────────────────


def _extract_section_titles(chunks: list[str]) -> list[Optional[str]]:
    """Extrait les titres de section à partir des chunks.

    Pour chaque chunk, regarde si la première ligne ressemble à un titre
    de section (Chapitre, Section, 1.1, etc.). Retourne une liste de
    même taille que ``chunks`` : soit le titre nettoyé, soit ``None``.

    Args:
        chunks: Liste des chunks de texte.

    Returns:
        Liste de même longueur que ``chunks``, chaque élément est
        soit le titre de section (``str``), soit ``None``.
    """
    titles: list[Optional[str]] = []
    for chunk in chunks:
        first_line = chunk.strip().split("\n")[0].strip()
        if _SECTION_PATTERNS.match(first_line):
            # Nettoyer le titre : enlever la numérotation / mot-section
            title = _clean_section_title(first_line)
            titles.append(title if title else first_line.strip())
        else:
            titles.append(None)
    return titles


def _clean_section_title(first_line: str) -> str:
    """Nettoie une ligne de titre de section pour en extraire le nom.

    Enlève les préfixes comme ``Chapitre 1 :``, ``Section 1.1 :``,
    ``I.``, ``1)``, etc.

    Args:
        first_line: Ligne brute potentiellement contenant un titre.

    Returns:
        Titre nettoyé (vide si seul le préfixe était présent).
    """
    title = first_line

    # 1. Enlever les mots-clés de section + numéro optionnel + séparateur
    #    Ex: "Chapitre 1 : Les bases" → "Les bases"
    #    Ex: "Section 1.1. Sous-partie" → "Sous-partie"
    title = re.sub(
        r"^(?:CHAPITRE|Chapitre|chapitre|SECTION|Section|section|"
        r"PARTIE|Partie|partie|TITRE|Titre|titre|ANNEXE|Annexe|annexe)"
        r"(?:\s+\d+(?:\.\d+)*)?"
        r"\s*[.:]\s*",
        "",
        title,
        flags=re.IGNORECASE,
    )

    # 2. Enlever la numérotation pure (1.1, 1.2.1, etc.)
    title = re.sub(r"^\d+(?:\.\d+)*\s*[.:]\s*", "", title)

    # 3. Enlever les chiffres romains + séparateur
    title = re.sub(r"^(?:I[VX]?|IV|V|VI{0,3})\s*[.:]\s*", "", title, flags=re.IGNORECASE)

    # 4. Enlever les listes numérotées (1), 2), etc.)
    title = re.sub(r"^\d+[.)]\s+", "", title)

    return title.strip()


def _map_chunks_to_sections(chunks: list[str]) -> list[int]:
    """Assigne chaque chunk à un identifiant de section numérique.

    Une nouvelle section commence dès qu'un chunk contient un titre
    (détecté par ``_SECTION_PATTERNS``). Les chunks avant le premier
    titre reçoivent l'ID 0 (section d'introduction implicite).

    Args:
        chunks: Liste des chunks de texte ordonnés.

    Returns:
        Liste d'IDs de section (``int``) de même longueur que ``chunks``.
    """
    section_ids: list[int] = []
    current_section = 0

    for chunk in chunks:
        first_line = chunk.strip().split("\n")[0].strip()
        if _SECTION_PATTERNS.match(first_line):
            current_section += 1
        section_ids.append(current_section)

    return section_ids


def _get_section_titles_map(chunks: list[str]) -> dict[int, str]:
    """Construit un dictionnaire ``section_id -> titre``.

    Seules les sections qui ont un titre explicite sont incluses.

    Args:
        chunks: Liste des chunks de texte.

    Returns:
        Mapping ``{section_id: titre_nettoyé}``.
    """
    section_titles: dict[int, str] = {}
    current_section = 0

    for chunk in chunks:
        first_line = chunk.strip().split("\n")[0].strip()
        if _SECTION_PATTERNS.match(first_line):
            current_section += 1
            title = _clean_section_title(first_line)
            section_titles[current_section] = title.strip() if title else first_line.strip()

    return section_titles


# ───────────────────────────────────────────────────────────────────────────
# Score BM25
# ───────────────────────────────────────────────────────────────────────────


def _compute_idf(term: str, all_chunks: list[str]) -> float:
    """Calcule l'IDF d'un terme selon la formule BM25.

    .. math::

        IDF = \\log\\frac{N - n_k + 0.5}{n_k + 0.5}

    où :
        - ``N`` = nombre total de chunks
        - ``n_k`` = nombre de chunks contenant le terme

    Args:
        term: Le terme (mot individuel) dont on calcule l'IDF.
        all_chunks: Collection complète des chunks.

    Returns:
        Valeur IDF (0.0 si le terme n'apparaît dans aucun chunk).
    """
    N = len(all_chunks)
    if N == 0:
        return 0.0

    term_lower = term.lower()
    n_k = sum(1 for chunk in all_chunks if term_lower in chunk.lower())

    if n_k == 0:
        return 0.0

    return math.log((N - n_k + 0.5) / (n_k + 0.5))


def _bm25_term_score(
    tf: float,
    idf: float,
    doc_len: float,
    avg_doc_len: float,
) -> float:
    """Calcule la contribution d'un terme au score BM25.

    .. math::

        \\text{score} = IDF \\cdot \\frac{TF \\cdot (k_1 + 1)}
                                    {TF + k_1 \\cdot (1 - b + b \\cdot \\frac{|d|}{\\text{avgdl}})}

    Args:
        tf: Fréquence brute du terme dans le chunk (raw count).
        idf: IDF pré-calculé du terme.
        doc_len: Longueur du chunk (en mots).
        avg_doc_len: Longueur moyenne des chunks (en mots).

    Returns:
        Contribution BM25 de ce terme (>= 0).
    """
    if idf <= 0.0 or tf <= 0.0:
        return 0.0

    if avg_doc_len <= 0.0:
        avg_doc_len = 1.0

    length_norm = 1.0 - _B + _B * (doc_len / avg_doc_len)
    denominator = tf + _K1 * length_norm

    if denominator <= 0.0:
        return 0.0

    return idf * (tf * (_K1 + 1.0)) / denominator


def _compute_bm25_score(
    chunk: str,
    query_terms: list[str],
    all_chunks: list[str],
    avg_doc_len: float,
    idf_cache: Optional[dict[str, float]] = None,
) -> float:
    """Calcule le score BM25 complet d'un chunk pour une requête.

    Pour chaque terme individuel de ``query_terms``, calcule sa fréquence
    dans le chunk et accumule le score BM25. Les bigrammes (termes avec
    espace) sont ignorés ici — ils servent pour le ``_PHRASE_BONUS``.

    Args:
        chunk: Texte du chunk à scorer.
        query_terms: Termes de la requête (mots individuels uniquement,
            les bigrammes sont filtrés silencieusement).
        all_chunks: Tous les chunks de la collection (pour l'IDF).
        avg_doc_len: Longueur moyenne des chunks (en mots).
        idf_cache: Cache des valeurs IDF pour éviter de les recalculer.

    Returns:
        Score BM25 total (>= 0).
    """
    if not chunk or not query_terms:
        return 0.0

    # Ne garder que les mots individuels (pas les bigrammes)
    single_terms = [t.lower() for t in query_terms if " " not in t]
    if not single_terms:
        return 0.0

    chunk_words = _tokenize(chunk)
    doc_len = len(chunk_words)

    if doc_len == 0:
        return 0.0

    # Compter la fréquence de chaque terme dans le chunk
    term_tf: dict[str, int] = {}
    for word in chunk_words:
        if word in single_terms:
            term_tf[word] = term_tf.get(word, 0) + 1

    if not term_tf:
        return 0.0

    # Calculer le score BM25 avec cache IDF
    idf_cache = idf_cache if idf_cache is not None else {}
    total_score = 0.0

    for term, tf in term_tf.items():
        if term not in idf_cache:
            idf_cache[term] = _compute_idf(term, all_chunks)
        idf = idf_cache[term]
        total_score += _bm25_term_score(float(tf), idf, float(doc_len), avg_doc_len)

    return total_score


# ───────────────────────────────────────────────────────────────────────────
# Scoring d'enrichissement
# ───────────────────────────────────────────────────────────────────────────


def score_by_term_proximity(chunk: str, keywords: set) -> float:
    """Calcule un score de proximité entre les mots-clés dans un chunk.

    Plus les mots-clés sont proches les uns des autres dans le texte,
    plus le score est élevé (entre 0 et 1). La distance est calculée
    en nombre de mots entre les occurrences de mots-clés différents.

    Args:
        chunk: Texte du chunk à analyser.
        keywords: Ensemble de mots-clés (str) de la question.

    Returns:
        Score de proximité entre 0.0 et 1.0.
    """
    if not chunk or not keywords or len(keywords) < 2:
        return 0.0

    chunk_lower = chunk.lower()
    words = _tokenize(chunk)

    if len(words) < 2:
        return 0.0

    # Identifier les mots-clés effectivement présents dans le chunk
    present = {kw for kw in keywords if kw.lower() in chunk_lower}
    if len(present) < 2:
        return 0.0

    # Indexer toutes les positions de chaque mot-clé
    keyword_positions: dict[str, list[int]] = defaultdict(list)
    for i, word in enumerate(words):
        if word in present:
            keyword_positions[word].append(i)

    if not keyword_positions:
        return 0.0

    # Construire la liste plate (position, mot_clé)
    all_positions: list[tuple[int, str]] = []
    for kw, positions in keyword_positions.items():
        for pos in positions:
            all_positions.append((pos, kw))

    all_positions.sort(key=lambda x: x[0])

    if len(all_positions) < 2:
        return 0.0

    # Calculer la distance moyenne entre paires ordonnées de mots-clés
    # différents (jusqu'à 5 mots d'écart pour rester local)
    total_distance = 0.0
    pairs = 0

    for i in range(len(all_positions) - 1):
        pos_i, kw_i = all_positions[i]
        for j in range(i + 1, min(i + 5, len(all_positions))):
            pos_j, kw_j = all_positions[j]
            if kw_i != kw_j:  # On ne compare que des mots-clés différents
                distance = abs(pos_j - pos_i)
                normalized_dist = distance / len(words) if len(words) > 0 else 1.0
                total_distance += normalized_dist
                pairs += 1

    if pairs == 0:
        return 0.0

    avg_distance = total_distance / pairs

    # Transformation : distance 0 → score 1.0, distance 0.5 → ~0.29
    score = 1.0 / (1.0 + 5.0 * avg_distance)

    return min(score, 1.0)


def find_exact_phrase(texts: list[str], phrase: str) -> list[str]:
    """Recherche une phrase exacte dans une liste de textes.

    La comparaison est insensible à la casse. Retourne les textes
    (parmi ``texts``) qui contiennent la phrase textuellement.

    Args:
        texts: Liste de textes (chunks, phrases, etc.).
        phrase: Phrase exacte à rechercher.

    Returns:
        Liste des textes contenant la phrase (dans l'ordre original).
    """
    if not texts or not phrase:
        return []

    phrase_lower = phrase.lower().strip()
    if not phrase_lower:
        return []

    return [text for text in texts if phrase_lower in text.lower()]


def _compute_phrase_bonus(chunk: str, bigram_terms: list[str]) -> float:
    """Calcule le bonus pour correspondance de bigrammes exacts.

    Si la question contient des bigrammes (termes avec espace) et que
    l'un d'eux apparaît textuellement dans le chunk, un bonus fixe
    ``_PHRASE_BONUS`` est ajouté.

    Args:
        chunk: Texte du chunk.
        bigram_terms: Termes de la requête contenant un espace (bigrammes).

    Returns:
        Bonus (0.0 ou ``_PHRASE_BONUS``).
    """
    if not chunk or not bigram_terms:
        return 0.0

    chunk_lower = chunk.lower()
    for term in bigram_terms:
        if " " in term and term.lower() in chunk_lower:
            return _PHRASE_BONUS

    return 0.0


def _compute_title_bonus(
    chunk_idx: int,
    section_titles: dict[int, str],
    section_ids: list[int],
    keywords: set,
) -> float:
    """Calcule le bonus si des mots-clés apparaissent dans le titre
    de la section contenant ce chunk.

    Args:
        chunk_idx: Index du chunk dans le document.
        section_titles: Mapping ``section_id -> titre``.
        section_ids: Mapping ``chunk_idx -> section_id``.
        keywords: Mots-clés de la question (``analysis.keywords``).

    Returns:
        Bonus (0.0 ou ``_TITLE_BONUS``).
    """
    if not section_titles or not keywords:
        return 0.0

    section_id = section_ids[chunk_idx]
    title = section_titles.get(section_id)
    if not title:
        return 0.0

    title_lower = title.lower()
    for kw in keywords:
        if kw.lower() in title_lower:
            return _TITLE_BONUS

    return 0.0


# ───────────────────────────────────────────────────────────────────────────
# Agrégation de chunks en paragraphes
# ───────────────────────────────────────────────────────────────────────────


def _merge_group(group: list[tuple[int, str, float]]) -> dict:
    """Fusionne un groupe de chunks en un seul paragraphe.

    Args:
        group: Liste de tuples ``(chunk_index, text, score)``,
               ordonnée par index croissant.

    Returns:
        Dict avec les clés ``text``, ``score``, ``metadata``, ``chunks_merged``.
    """
    texts = [t[1] for t in group]
    merged_text = "\n\n".join(texts)

    scores = [t[2] for t in group]
    avg_score = sum(scores) / len(scores) if scores else 0.0

    # Index du premier et du dernier chunk fusionné
    first_idx = group[0][0]
    last_idx = group[-1][0]

    return {
        "text": merged_text,
        "score": avg_score,
        "metadata": {
            "first_chunk": first_idx,
            "last_chunk": last_idx,
        },
        "chunks_merged": len(group),
    }


def _merge_adjacent_chunks(
    chunks_scores: list[tuple[int, str, float]],
    max_gap: int = 2,
) -> list[dict]:
    """Fusionne les chunks adjacents bien scorés en paragraphes cohérents.

    Parcourt les chunks dans l'ordre de leur index et fusionne ceux
    qui sont proches (``gap <= max_gap``). Le score du groupe résultant
    est la moyenne des scores individuels.

    Args:
        chunks_scores: Liste de tuples ``(chunk_index, text, score)``,
                       **non triée** (le tri se fait automatiquement).
        max_gap: Écart maximal entre deux index consécutifs pour qu'ils
                 soient considérés comme adjacents et donc fusionnés.

    Returns:
        Liste de dicts avec les clés ``text``, ``score``, ``metadata``,
        ``chunks_merged``.
    """
    if not chunks_scores:
        return []

    # Trier par index de chunk
    sorted_chunks = sorted(chunks_scores, key=lambda x: x[0])

    merged: list[dict] = []
    current_group: list[tuple[int, str, float]] = [sorted_chunks[0]]

    for i in range(1, len(sorted_chunks)):
        prev_idx = sorted_chunks[i - 1][0]
        curr_idx = sorted_chunks[i][0]

        if curr_idx - prev_idx <= max_gap:
            current_group.append(sorted_chunks[i])
        else:
            merged.append(_merge_group(current_group))
            current_group = [sorted_chunks[i]]

    if current_group:
        merged.append(_merge_group(current_group))

    return merged


# ───────────────────────────────────────────────────────────────────────────
# Cœur du scoring : fonction partagée
# ───────────────────────────────────────────────────────────────────────────


def _score_all_chunks(
    docs: list[dict],
    query_terms: list[str],
    analysis: QuestionAnalysis,
) -> tuple[list[str], list[dict]]:
    """Calcule le score enrichi de tous les chunks de tous les documents.

    Combinaison de :
      1. BM25 scoring sur les termes individuels
      2. Bonus de bigramme exact
      3. Bonus de proximité entre mots-clés
      4. Bonus de titre de section
      5. Section-aware bonus (second-pass)

    Args:
        docs: Liste des documents (du ``document_store``).
        query_terms: Termes de recherche (mots + bigrammes).
        analysis: Analyse structurée de la question.

    Returns:
        Tuple ``(all_chunks, scored)`` où :
        - ``all_chunks`` : liste plate de tous les chunks (str)
        - ``scored`` : liste de dicts avec ``flat_idx``, ``doc_idx``,
          ``chunk_idx``, ``text``, ``score``, ``bm25_score``,
          ``filename``, ``metadata``, ``doc``.
    """
    if not docs:
        return [], []

    # ── 1. Aplatir tous les chunks ─────────────────────────────────────
    all_chunks: list[str] = []
    chunk_doc_map: list[tuple[int, int, dict]] = []  # (doc_idx, chunk_idx, doc)

    for doc_idx, doc in enumerate(docs):
        doc_chunks = doc.get("chunks") or []
        for chunk_idx, chunk in enumerate(doc_chunks):
            all_chunks.append(chunk)
            chunk_doc_map.append((doc_idx, chunk_idx, doc))

    if not all_chunks:
        return [], []

    # ── 2. Prérequis BM25 ──────────────────────────────────────────────
    total_words = sum(len(_tokenize(c)) for c in all_chunks)
    avg_doc_len = total_words / len(all_chunks) if all_chunks else _DEFAULT_AVG_DOC_LEN

    # ── 3. Séparer termes individuels et bigrammes ────────────────────
    single_terms = [t for t in query_terms if " " not in t]
    bigram_terms = [t for t in query_terms if " " in t]

    # ── 4. Premier passage : BM25 + bonus directs ─────────────────────
    idf_cache: dict[str, float] = {}
    scored: list[dict] = []

    for flat_idx, chunk in enumerate(all_chunks):
        doc_idx, chunk_idx, doc = chunk_doc_map[flat_idx]

        bm25_score = _compute_bm25_score(
            chunk, single_terms, all_chunks, avg_doc_len, idf_cache,
        )

        # Bonus bigramme exact
        phrase_bonus = _compute_phrase_bonus(chunk, bigram_terms)

        # Bonus proximité
        prox = score_by_term_proximity(chunk, analysis.keywords)
        proximity_bonus = prox * _PROXIMITY_BONUS_MAX

        total = bm25_score + phrase_bonus + proximity_bonus

        if total > 0.0 or bm25_score > 0.0:
            scored.append({
                "flat_idx": flat_idx,
                "doc_idx": doc_idx,
                "chunk_idx": chunk_idx,
                "text": chunk,
                "score": total,
                "bm25_score": bm25_score,
                "filename": doc.get("filename", ""),
                "metadata": dict(doc.get("metadata", {})),
                "doc": doc,
            })

    if not scored:
        return all_chunks, []

    # ── 5. Second passage : section-aware + title bonus ────────────────
    # Regrouper par document
    doc_groups: dict[int, list[dict]] = defaultdict(list)
    for r in scored:
        doc_groups[r["doc_idx"]].append(r)

    # Seuil : top 20 % des scores (ou au moins le premier)
    scored_sorted_by_score = sorted(scored, key=lambda x: -x["score"])
    threshold_idx = max(0, len(scored_sorted_by_score) // 5)
    score_threshold = scored_sorted_by_score[threshold_idx]["score"] if scored else 0.0

    for doc_idx, results in doc_groups.items():
        doc = docs[doc_idx]
        chunks = doc.get("chunks") or []

        section_ids = _map_chunks_to_sections(chunks)
        section_titles = _get_section_titles_map(chunks)

        # Sections "importantes" : celles qui contiennent au moins un
        # chunk dans le top 20 % des scores
        important_sections: set[int] = set()
        for r in results:
            if r["score"] >= score_threshold:
                sec_id = section_ids[r["chunk_idx"]]
                important_sections.add(sec_id)

        # Appliquer les bonus
        for r in results:
            sec_id = section_ids[r["chunk_idx"]]

            # Section-aware bonus : chunks dans une section importante
            # mais en dessous du seuil reçoivent un petit bonus
            if sec_id in important_sections and r["score"] < score_threshold:
                r["score"] += _SECTION_BONUS

            # Title bonus : les mots-clés sont dans le titre de la section ?
            title_bonus = _compute_title_bonus(
                r["chunk_idx"],
                section_titles,
                section_ids,
                analysis.keywords,
            )
            if title_bonus > 0.0:
                r["score"] += title_bonus

    return all_chunks, scored


# ───────────────────────────────────────────────────────────────────────────
# API publique
# ───────────────────────────────────────────────────────────────────────────


def search_documents(
    docs: list[dict],
    query_terms: list[str],
    analysis: QuestionAnalysis,
    n_results: int = 10,
) -> list[dict]:
    """Recherche les chunks les plus pertinents par BM25 enrichi.

    Combine le scoring BM25 avec des bonus de :
      - Bigrammes exacts (phrase matching)
      - Proximité des mots-clés dans le chunk
      - Titre de section contenant les mots-clés
      - Cohérence de section (section-aware)

    Args:
        docs: Liste des documents depuis le ``document_store``.
            Chaque document doit avoir au moins les clés ``chunks``,
            ``filename`` et ``metadata``.
        query_terms: Termes de recherche (mots + bigrammes) provenant
            de ``question_analyzer.get_search_terms()``.
        analysis: Analyse de la question (``QuestionAnalysis``) avec
            ``.keywords`` et ``.question_type``.
        n_results: Nombre maximum de résultats à retourner (défaut: 10).

    Returns:
        Liste de dicts, chacun contenant :
        - ``text``: Texte du chunk.
        - ``score``: Score total de pertinence.
        - ``metadata``: Dict avec ``filename`` et les métadonnées du doc.

    Example:
        >>> docs = document_store.get_documents_list()
        >>> analysis = question_analyzer.analyze_question("Qu'est-ce que Newton ?")
        >>> terms = question_analyzer.get_search_terms(analysis)
        >>> results = search_documents(docs, terms, analysis, n_results=5)
        >>> results[0]["text"]
        "Newton est un physicien et mathématicien..."
    """
    _, scored = _score_all_chunks(docs, query_terms, analysis)

    if not scored:
        return []

    # Trier par score décroissant
    scored.sort(key=lambda x: -x["score"])

    # Normaliser les scores entre 0 et 1
    max_score = scored[0]["score"]
    if max_score > 0.0:
        for r in scored:
            r["score"] = r["score"] / max_score

    # Formater les résultats
    results: list[dict] = []
    for r in scored[:n_results]:
        meta = dict(r["metadata"])
        meta["filename"] = r["filename"]
        meta["chunk_index"] = r["chunk_idx"]

        results.append({
            "text": r["text"],
            "score": r["score"],
            "metadata": meta,
        })

    return results


def batch_retrieve_paragraphs(
    docs: list[dict],
    query_terms: list[str],
    analysis: QuestionAnalysis,
    n_results: int = 10,
) -> list[dict]:
    """Version enrichie qui retourne des PARAGRAPHES complets (pas des chunks).

    Au lieu de retourner des chunks atomiques, cette fonction :
      1. Score tous les chunks (BM25 + bonus).
      2. Regroupe les chunks adjacents bien scorés en paragraphes.
      3. Retourne des blocs de texte cohérents et plus longs.

    Args:
        docs: Liste des documents depuis le ``document_store``.
        query_terms: Termes de recherche.
        analysis: Analyse de la question.
        n_results: Nombre maximum de paragraphes à retourner.

    Returns:
        Liste de dicts, chacun contenant :
        - ``text``: Texte complet du paragraphe (plusieurs chunks fusionnés).
        - ``score``: Score moyen du paragraphe.
        - ``metadata``: Dict avec ``filename``, ``first_chunk``, ``last_chunk``.
        - ``chunks_merged``: Nombre de chunks fusionnés.

    Example:
        >>> docs = document_store.get_documents_list()
        >>> analysis = question_analyzer.analyze_question("Explique la relativité")
        >>> terms = question_analyzer.get_search_terms(analysis)
        >>> paragraphs = batch_retrieve_paragraphs(docs, terms, analysis)
        >>> for p in paragraphs:
        ...     print(f"[Score: {p['score']:.2f}] {p['text'][:100]}...")
    """
    _, scored = _score_all_chunks(docs, query_terms, analysis)

    if not scored:
        return []

    # Normaliser les scores
    max_score = max(r["score"] for r in scored)
    if max_score > 0.0:
        for r in scored:
            r["score"] = r["score"] / max_score

    # Regrouper par document pour la fusion
    doc_groups: dict[str, list[dict]] = defaultdict(list)
    for r in scored:
        doc_groups[r["filename"]].append(r)

    merged_results: list[dict] = []

    for filename, results in doc_groups.items():
        # Trier par chunk_index au sein du document
        results.sort(key=lambda x: x["chunk_idx"])

        chunk_scores = [
            (r["chunk_idx"], r["text"], r["score"]) for r in results
        ]

        merged = _merge_adjacent_chunks(chunk_scores, max_gap=2)

        for m in merged:
            m["metadata"]["filename"] = filename
            # Re-normaliser le score du paragraphe (moyenne déjà faite)
            # par rapport au max global
            m["score"] = m["score"] / max_score if max_score > 0.0 else 0.0
            merged_results.append(m)

    # Trier par score décroissant
    merged_results.sort(key=lambda x: -x["score"])

    return merged_results[:n_results]
