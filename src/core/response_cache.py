"""💾 Cache de réponses aux questions (évite les appels LLM redondants).

Stocke les questions normalisées et leurs réponses dans un fichier JSON.
Au-delà de 200 entrées, les plus anciennes sont automatiquement supprimées."""

import hashlib
import json
import os
import re
from datetime import datetime

_DATA_DIR = os.getenv("DATA_DIR", "./data")
_CACHE_FILE = os.path.join(_DATA_DIR, "response_cache.json")
_MAX_ENTRIES = 200


def _normalize(question: str) -> str:
    """Normalise une question pour la clé de cache."""
    q = question.lower().strip()
    q = re.sub(r"[^\w\s]", "", q)  # enlève ponctuation
    q = re.sub(r"\s+", " ", q)     # espacement uniforme
    return q


def _load() -> dict:
    """Charge le cache depuis le fichier JSON."""
    if not os.path.exists(_CACHE_FILE):
        return {}
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def _save(cache: dict):
    """Sauvegarde le cache dans le fichier JSON."""
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def _make_key(question: str) -> str:
    """Génère une clé de cache à partir de la question normalisée."""
    return hashlib.sha256(_normalize(question).encode()).hexdigest()


def get(question: str) -> dict | None:
    """Retourne la réponse en cache si elle existe.

    Args:
        question: Question posée.

    Returns:
        Dict avec 'answer' et 'sources', ou None.
    """
    key = _make_key(question)
    cache = _load()
    entry = cache.get(key)
    if entry is None:
        return None
    return {"answer": entry["answer"], "sources": entry["sources"]}


def set(question: str, answer: str, sources: list[str]):
    """Stocke une réponse dans le cache.

    Args:
        question: Question posée.
        answer: Réponse générée.
        sources: Liste des sources.
    """
    key = _make_key(question)
    cache = _load()

    cache[key] = {
        "question": _normalize(question),
        "answer": answer,
        "sources": sources,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Éviter la croissance infinie
    if len(cache) > _MAX_ENTRIES:
        # Trier par timestamp et garder les plus récents
        sorted_items = sorted(
            cache.items(),
            key=lambda x: x[1].get("timestamp", ""),
            reverse=True,
        )
        cache = dict(sorted_items[:_MAX_ENTRIES])

    _save(cache)


def clear():
    """Vide le cache."""
    if os.path.exists(_CACHE_FILE):
        os.remove(_CACHE_FILE)


def stats() -> dict:
    """Retourne des statistiques sur le cache.

    Returns:
        Dict avec 'entries' (int), 'file_size' (str).
    """
    cache = _load()
    size = 0
    if os.path.exists(_CACHE_FILE):
        size = os.path.getsize(_CACHE_FILE)

    if size < 1024:
        size_str = f"{size} o"
    elif size < 1024 * 1024:
        size_str = f"{size / 1024:.1f} Ko"
    else:
        size_str = f"{size / (1024 * 1024):.1f} Mo"

    return {"entries": len(cache), "file_size": size_str}

