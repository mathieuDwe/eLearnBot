"""🧠 Moteur principal de Q&A sans LLM — Orchestration et scoring de confiance.

Ce module est le point d'entrée unique du système de questions-réponses
sans LLM. Il coordonne les 4 sous-modules :

1. **document_analyzer** — Analyse les documents pour en extraire la structure
2. **question_analyzer** — Analyse et classifie la question
3. **retrieval** — Recherche les passages pertinents (BM25, proximité)
4. **strategies** — Applique la stratégie adaptée au type de question

Flux complet
------------
1. À l'indexation : ``analyze_document(text, filename)`` pré-calcule les
   métadonnées structurelles du document.
2. À la question : ``answer_question_non_llm(question, docs)`` :
   a. Analyse la question → type, mots-clés, terme cible
   b. Récupère les analyses pré-calculées des documents
   c. Sélectionne la stratégie adaptée au type de question
   d. Exécute la stratégie avec les passages les plus pertinents
   e. Retourne la réponse avec un score de confiance

Scoring de confiance
--------------------
Le moteur attribue un score de confiance à chaque réponse (0.0 – 1.0) :

- **1.0** : Réponse trouvée dans une définition explicite ou une liste
  structurée du document
- **0.8** : Réponse construite à partir des phrases-clés avec fort
  recouvrement de mots-clés
- **0.6** : Réponse basée sur des passages pertinents avec recouvrement
  partiel des mots-clés
- **0.4** : Réponse générique utilisant les key_sentences du document
- **0.0** : Aucune information trouvée dans les documents
"""

import json
import logging
import os
from typing import Optional

from core import document_store

from .document_analyzer import analyze_document_text
from .question_analyzer import analyze_question, QuestionType
from .strategies import execute_strategy, get_strategies
from .retrieval import search_documents, batch_retrieve_paragraphs

logger = logging.getLogger(__name__)

# ── Clé de stockage des analyses dans les métadonnées ────────────────────
_ANALYSIS_META_KEY = "_non_llm_analysis"


# ── API publique ─────────────────────────────────────────────────────────

def analyze_document(text: str, filename: str = "") -> dict:
    """Analyse un document et stocke l'analyse dans ses métadonnées.

    À appeler juste après ``document_store.add_document()`` pour enrichir
    le document avec les informations nécessaires au Q&A sans LLM.

    L'analyse est stockée dans les métadonnées du document sous la clé
    ``_non_llm_analysis`` et est persistée dans le cloud avec le document.

    Args:
        text: Texte complet du document.
        filename: Nom du fichier (pour le logging).

    Returns:
        L'analyse complète (dict).
    """
    # 1. Générer l'analyse
    analysis = analyze_document_text(text, filename)

    # 2. Récupérer le document existant
    doc = document_store.get_document_by_filename(filename)
    if doc is None:
        logger.warning(
            "Document '%s' non trouvé dans le store. "
            "Appelez d'abord add_document(). Analyse non persistée.",
            filename,
        )
        return analysis

    # 3. Ajouter l'analyse aux métadonnées
    metadata = doc.get("metadata", {})
    metadata[_ANALYSIS_META_KEY] = analysis

    # 4. Mettre à jour le document (add_document écrase l'existant)
    document_store.add_document(
        text=doc["text"],
        filename=filename,
        metadata=metadata,
        content_hash=metadata.get("content_hash"),
    )

    logger.info(
        "Analyse non-LLM pour '%s' : %d phrases-clés, %d définitions, %d sections",
        filename,
        len(analysis.get("key_sentences", [])),
        len(analysis.get("definitions", [])),
        len(analysis.get("sections", [])),
    )

    return analysis


def get_document_analysis(filename: str) -> Optional[dict]:
    """Récupère l'analyse pré-calculée d'un document.

    Args:
        filename: Nom du fichier.

    Returns:
        L'analyse complète (dict), ou None si non disponible.
    """
    doc = document_store.get_document_by_filename(filename)
    if doc is None:
        return None

    metadata = doc.get("metadata", {})
    return metadata.get(_ANALYSIS_META_KEY)


def answer_question_non_llm(
    question: str,
    document_name: str = None,
    min_confidence: float = 0.0,
) -> dict:
    """Répond à une question SANS utiliser aucun LLM.

    C'est la fonction principale du système. Elle :

    1. Analyse la question pour déterminer son type et ses mots-clés
    2. Récupère les analyses pré-calculées des documents
    3. Construit les passages pertinents via BM25 + proximité
    4. Sélectionne et exécute la stratégie adaptée
    5. Retourne la réponse avec un score de confiance

    Args:
        question: Question en langage naturel.
        document_name: Filtrer sur un document spécifique (ou None pour tous).
        min_confidence: Seuil de confiance minimum (0.0 pour tout accepter).

    Returns:
        Dict avec les clés :
            - "answer" (str) : La réponse construite
            - "sources" (list[str]) : Citations textuelles utilisées
            - "confidence" (float) : Score de confiance (0.0 – 1.0)
            - "question_type" (str) : Type de question détecté
            - "strategy_used" (str) : Stratégie employée
    """
    if not question or not question.strip():
        return _empty_response("Aucune question posée.")

    # ── 1. Analyser la question ────────────────────────────────────────
    analysis = analyze_question(question)

    if not analysis.keywords and analysis.question_type == QuestionType.UNKNOWN:
        return _empty_response(
            "Je n'ai pas compris votre question. "
            "Essayez de reformuler avec des mots plus précis."
        )

    # ── 2. Récupérer les documents et leurs analyses ───────────────────
    docs = document_store._load_cache()  # Accès direct au cache

    # Filtrer par document si demandé
    if document_name:
        docs = [d for d in docs if d["filename"] == document_name]

    if not docs:
        return _empty_response(
            "Aucun document disponible pour répondre à votre question. "
            "Demandez à votre professeur d'uploader des cours."
        )

    # Récupérer les analyses pré-calculées
    analyses = {}
    for d in docs:
        meta = d.get("metadata", {})
        a = meta.get(_ANALYSIS_META_KEY)
        if a:
            analyses[d["filename"]] = a

    # ── 3. Vérifier si on a des analyses disponibles ───────────────────
    if not analyses:
        # Mode dégradé : pas d'analyse pré-calculée
        # On utilise la recherche basique + stratégie extractive simple
        return _fallback_search(question, docs, analysis)

    # ── 4. Chercher les passages pertinents ────────────────────────────
    query_terms = [analysis.target_term] if analysis.target_term else []
    query_terms.extend([k for k in analysis.keywords if ' ' not in k])

    try:
        passages = batch_retrieve_paragraphs(
            docs=docs,
            query_terms=query_terms,
            analysis=analysis,
            n_results=5,
        )
    except Exception as e:
        logger.warning("Retrieval avancé échoué, fallback basique : %s", e)
        passages = _basic_search(docs, analysis.keywords)

    # ── 5. Exécuter la stratégie adaptée au type de question ──────────
    strategies = get_strategies()
    qtype = analysis.question_type

    if qtype in strategies:
        try:
            result = execute_strategy(qtype, analysis, analyses, docs)
        except Exception as e:
            logger.error("Stratégie %s échouée : %s", qtype.value, e)
            # Fallback : réponse basée sur les passages
            result = _passage_based_answer(passages, analysis)
    else:
        # Type inconnu → réponse basée sur les passages
        result = _passage_based_answer(passages, analysis)

    # ── 6. Adapter la confiance et structurer la réponse ───────────────
    confidence = result.get("confidence", 0.0)
    answer = result.get("answer", "")
    sources = result.get("sources", [])

    # Si la confiance est trop basse, essayer le fallback extraction pure
    if confidence < min_confidence and passages:
        result = _passage_based_answer(passages, analysis)
        confidence = result.get("confidence", 0.0)
        answer = result.get("answer", "")
        sources = result.get("sources", [])

    # Si toujours rien, message par défaut
    if not answer:
        return _empty_response(
            "Je n'ai pas trouvé d'information pertinente dans les cours "
            "pour répondre à votre question."
        )

    # Ajouter le type de question et la stratégie à la réponse
    strategy_name = strategies.get(qtype, type('', (), {'name': 'fallback'})).name \
        if qtype in strategies else "fallback"

    return {
        "answer": answer,
        "sources": sources[:5],  # Max 5 sources
        "confidence": confidence,
        "question_type": qtype.value,
        "strategy_used": strategy_name,
    }


# ── Réponses de fallback ────────────────────────────────────────────────

def _empty_response(message: str) -> dict:
    """Retourne une réponse vide standardisée."""
    return {
        "answer": message,
        "sources": [],
        "confidence": 0.0,
        "question_type": "unknown",
        "strategy_used": "none",
    }


def _fallback_search(question: str, docs: list[dict], analysis) -> dict:
    """Mode dégradé : recherche basique sans analyses pré-calculées.

    Utilise la fonction search() du document_store comme fallback
    quand les analyses ne sont pas disponibles.
    """
    results = document_store.search(
        query=question,
        n_results=8,
        document_name=None,
    )

    if not results:
        return _empty_response(
            "Je n'ai pas trouvé de passages pertinents "
            "dans les cours pour répondre à votre question."
        )

    # Regrouper par document
    from collections import defaultdict
    docs_grouped = defaultdict(list)
    for r in results:
        fname = r['metadata'].get('filename', 'Source')
        docs_grouped[fname].append(r)

    # Construire une réponse documentaire
    answer_parts = [
        f"🔍 **{len(docs_grouped)} document(s) trouvé(s)** "
        f"pour votre question sur «{analysis.target_term or question}» :\n"
    ]
    sources = []

    for fname, chunks in docs_grouped.items():
        answer_parts.append(f"\n📄 **{fname}** ({len(chunks)} passage(s) trouvé(s))")
        for i, c in enumerate(chunks[:2], 1):
            text = c['text'][:200].rsplit(' ', 1)[0] + '…' if len(c['text']) > 200 else c['text']
            answer_parts.append(f"  {i}. {text}")
            sources.append(f"{fname} — {text[:100]}…")

    return {
        "answer": "\n".join(answer_parts),
        "sources": sources[:5],
        "confidence": 0.4,
        "question_type": analysis.question_type.value,
        "strategy_used": "fallback_search",
    }


def _passage_based_answer(passages: list[dict], analysis) -> dict:
    """Construit une réponse à partir des passages les plus pertinents.

    Args:
        passages: Liste de passages (avec 'text', 'score', 'metadata').
        analysis: Analyse de la question.

    Returns:
        Dict réponse standardisé.
    """
    if not passages:
        return _empty_response(
            "Je n'ai pas trouvé de passages pertinents dans les cours."
        )

    # Prendre les 3 meilleurs passages
    top_passages = passages[:3]
    answer_parts = [
        f"📖 Voici ce que j'ai trouvé dans les cours "
        f"à propos de «{analysis.target_term or 'votre question'}» :\n"
    ]
    sources = []

    for i, p in enumerate(top_passages, 1):
        text = p.get("text", "")
        if not text:
            continue
        source_name = p.get("metadata", {}).get("filename", "Source inconnue")
        score = p.get("score", 0)

        # Formater le passage
        if len(text) > 300:
            text = text[:297].rsplit(' ', 1)[0] + '…'

        answer_parts.append(
            f"\n**Passage {i}** (pertinence: {score:.0%}) — {source_name} :\n"
            f"> {text}"
        )
        sources.append(f"{source_name} — {text[:100]}…")

    return {
        "answer": "\n".join(answer_parts),
        "sources": sources,
        "confidence": min(0.5 + len(passages) * 0.05, 0.7),
        "question_type": analysis.question_type.value,
        "strategy_used": "passage_extraction",
    }


def _basic_search(docs: list[dict], keywords: set) -> list[dict]:
    """Recherche basique par mots-clés dans les documents.

    Utilisé comme fallback quand le retrieval avancé échoue.

    Args:
        docs: Liste des documents.
        keywords: Mots-clés à rechercher.

    Returns:
        Liste de passages avec score.
    """
    results = []
    for d in docs:
        meta = d.get("metadata", {})
        meta["filename"] = d["filename"]
        for chunk in d.get("chunks", []):
            chunk_lower = chunk.lower()
            score = sum(1 for k in keywords if k in chunk_lower)
            if score > 0:
                results.append({
                    "text": chunk,
                    "score": score / max(len(keywords), 1),
                    "metadata": dict(meta),
                })

    results.sort(key=lambda x: -x["score"])
    return results[:10]
