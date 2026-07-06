"""⚖️ Intégration Legifrance — API PISTE + mode manuel.

Recherche et récupération d'articles juridiques.
Deux modes :
  1. API officielle PISTE (si PISTE_API_KEY configurée dans .env)
  2. Mode manuel : URL d'article Legifrance ou texte brut
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger(__name__)


# ── Types ──────────────────────────────────────────────────────────────────

@dataclass
class LegalArticle:
    """Article de loi ou de code juridique."""
    title: str
    text: str
    source: str          # "piste" / "url" / "manual"
    url: str = ""
    code_name: str = ""  # ex: "Code civil"
    article_id: str = "" # ex: "LEGIARTI000039041983"


@dataclass
class LegalSearchResult:
    """Résultat d'une recherche Legifrance."""
    title: str
    url: str
    snippet: str
    article_id: str = ""


# ── Configuration ─────────────────────────────────────────────────────────

PISTE_API_KEY = os.getenv("PISTE_API_KEY", "")
PISTE_BASE_URL = "https://api.piste.gouv.fr/legifrance/v1"


# ── Helpers ────────────────────────────────────────────────────────────────

def _clean_html(raw: str) -> str:
    """Nettoie le HTML basique pour ne garder que le texte."""
    import html
    raw = html.unescape(raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def _extract_legifrance_id(url: str) -> Optional[str]:
    """Extrait l'ID Legifrance depuis une URL."""
    patterns = [
        r"/article_lc/(LEGIARTI\d+)",
        r"/article_jo/(LEGIARTI\d+)",
        r"/code_article/(LEGIARTI\d+)",
        r"id=LEGIARTI(\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(0).lstrip("/") if "/" in pat else f"LEGIARTI{m.group(1)}"
    # Fallback : l'URL contient peut-être directement l'ID
    m = re.search(r"(LEGI[A-Z]+\d+)", url)
    return m.group(1) if m else None


# ── Mode 1 : API PISTE ────────────────────────────────────────────────────

def search_via_piste(query: str, max_results: int = 10) -> list[LegalSearchResult]:
    """Recherche via l'API PISTE Legifrance.

    Nécessite PISTE_API_KEY dans .env.
    Inscription : https://api.piste.gouv.fr

    Args:
        query: La recherche textuelle.
        max_results: Nombre max de résultats.

    Returns:
        Liste de résultats de recherche.

    Raises:
        RuntimeError: Si la clé API n'est pas configurée.
    """
    if not PISTE_API_KEY:
        raise RuntimeError(
            "Clé API PISTE non configurée. "
            "Inscrivez-vous sur https://api.piste.gouv.fr "
            "et ajoutez PISTE_API_KEY dans .env"
        )

    headers = {
        "X-API-Key": PISTE_API_KEY,
        "Accept": "application/json",
    }
    params = {
        "q": query,
        "pageSize": min(max_results, 50),
        "pageNumber": 1,
        "sort": "pertinence",
    }

    try:
        resp = requests.get(
            f"{PISTE_BASE_URL}/recherche/operation",
            headers=headers,
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("results", []):
            results.append(LegalSearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=_clean_html(item.get("snippet", "")),
                article_id=item.get("id", ""),
            ))
        return results

    except requests.RequestException as e:
        logger.error("Erreur API PISTE : %s", e)
        return []


def get_article_via_piste(article_id: str) -> Optional[LegalArticle]:
    """Récupère le texte intégral d'un article via l'API PISTE."""
    if not PISTE_API_KEY:
        return None

    headers = {
        "X-API-Key": PISTE_API_KEY,
        "Accept": "application/json",
    }
    params = {"id": article_id}

    try:
        resp = requests.get(
            f"{PISTE_BASE_URL}/consultation/article",
            headers=headers,
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        return LegalArticle(
            title=data.get("title", f"Article {article_id}"),
            text=_clean_html(data.get("content", "")),
            source="piste",
            url=data.get("url", ""),
            code_name=data.get("codeName", ""),
            article_id=article_id,
        )

    except requests.RequestException as e:
        logger.error("Erreur récupération article PISTE : %s", e)
        return None


# ── Mode 2 : URL Legifrance ────────────────────────────────────────────────

def fetch_article_from_url(url: str) -> Optional[LegalArticle]:
    """Tente de récupérer le contenu d'un article Legifrance via son URL.

    Note : Legifrance utilise Cloudflare - cette méthode peut échouer.
    Dans ce cas, préférez l'API PISTE ou le mode manuel.

    Args:
        url: URL complète de l'article Legifrance.

    Returns:
        L'article si récupéré, None sinon.
    """
    article_id = _extract_legifrance_id(url)
    if not article_id:
        # Essayer via l'API PISTE comme fallback
        if PISTE_API_KEY:
            return get_article_via_piste(url)
        return None

    # Tenter une récupération via l'API publique mobile
    # (moins protégée par Cloudflare)
    mobile_url = f"https://api.legifrance.gouv.fr/legifrance/v1/article/{article_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://www.legifrance.gouv.fr/",
    }

    try:
        resp = requests.get(mobile_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return LegalArticle(
                title=data.get("titre", f"Article {article_id}"),
                text=_clean_html(data.get("contenu", "")),
                source="url",
                url=url,
                code_name=data.get("code", ""),
                article_id=article_id,
            )
    except requests.RequestException:
        pass

    return None


# ── Mode 3 : Texte manuel ────────────────────────────────────────────────

def create_manual_article(
    title: str,
    text: str,
    code_name: str = "Document juridique",
) -> LegalArticle:
    """Crée un article à partir d'un texte saisi manuellement.

    Args:
        title: Titre/nom de l'article.
        text: Contenu textuel.
        code_name: Nom du code juridique (optionnel).

    Returns:
        L'article créé.
    """
    return LegalArticle(
        title=title,
        text=text,
        source="manual",
        code_name=code_name,
    )


# ── Formatage pour le RAG ────────────────────────────────────────────────

def format_article_for_rag(article: LegalArticle) -> str:
    """Formate un article juridique pour l'indexation RAG.

    Returns:
        Texte formaté : titre + code + contenu.
    """
    parts = [f"Titre : {article.title}"]
    if article.code_name:
        parts.append(f"Code : {article.code_name}")
    if article.source:
        parts.append(f"Source : {article.source}")
    parts.append("")
    parts.append(article.text)
    return "\n".join(parts)


def get_article_metadata(article: LegalArticle) -> dict:
    """Retourne les métadonnées pour ChromaDB."""
    return {
        "source": article.source,
        "url": article.url,
        "code_name": article.code_name,
        "article_id": article.article_id,
        "type": "legal",
    }