"""🧠 Moteur de Q&A sans LLM — Analyse de documents et réponses intelligentes.

Ce package implémente un système complet de questions-réponses qui
fonctionne **sans appel à aucun LLM**. Il utilise des techniques de
NLP traditionnel, de recherche d'information et d'extraction de
connaissances pour répondre aux questions des élèves.

Architecture
------------
document_analyzer.py   → Analyse hors ligne des documents (définitions,
                         entités, phrases-clés, structure)
question_analyzer.py   → Classification et compréhension des questions
retrieval.py           → Recherche BM25, phrases, proximité
strategies.py          → 9 stratégies de réponse spécialisées
engine.py              → Orchestrateur principal avec scoring de confiance

Flux
----
1. À l'indexation : document_analyzer enrichit chaque document
   avec des métadonnées structurelles et sémantiques.
2. À la question : question_analyzer classifie la question →
   engine sélectionne la stratégie → retrieval trouve les passages →
   strategies construit la réponse → engine retourne le résultat.
"""

from .engine import answer_question_non_llm, analyze_document, get_document_analysis

__all__ = [
    "answer_question_non_llm",
    "analyze_document",
    "get_document_analysis",
]
