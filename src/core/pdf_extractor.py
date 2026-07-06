"""📄 Extraction de texte depuis des fichiers PDF."""

import io
from typing import Optional

import PyPDF2
import pdfplumber


def extract_text_from_pdf(file_path: str) -> str:
    """Extrait le texte d'un fichier PDF.

    Utilise pdfplumber (meilleure qualité) avec PyPDF2 en fallback.

    Args:
        file_path: Chemin vers le fichier PDF.

    Returns:
        Texte extrait du PDF.
    """
    text = _extract_with_pdfplumber(file_path)
    if not text.strip():
        text = _extract_with_pypdf2(file_path)
    return text.strip()


def extract_text_from_bytes(pdf_bytes: bytes) -> str:
    """Extrait le texte depuis des bytes PDF.

    Args:
        pdf_bytes: Contenu du fichier PDF en bytes.

    Returns:
        Texte extrait du PDF.
    """
    text = _extract_with_pdfplumber_bytes(pdf_bytes)
    if not text.strip():
        text = _extract_with_pypdf2_bytes(pdf_bytes)
    return text.strip()


def _extract_with_pdfplumber(file_path: str) -> str:
    """Extraction via pdfplumber (meilleure qualité)."""
    text_parts = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts)


def _extract_with_pdfplumber_bytes(pdf_bytes: bytes) -> str:
    """Extraction via pdfplumber depuis des bytes."""
    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts)


def _extract_with_pypdf2(file_path: str) -> str:
    """Extraction via PyPDF2 (fallback)."""
    text_parts = []
    with open(file_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts)


def _extract_with_pypdf2_bytes(pdf_bytes: bytes) -> str:
    """Extraction via PyPDF2 depuis des bytes."""
    text_parts = []
    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_parts.append(page_text)
    return "\n\n".join(text_parts)


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Découpe un texte en chunks de taille fixe avec recouvrement.

    Args:
        text: Texte à découper.
        chunk_size: Nombre de mots par chunk.
        overlap: Nombre de mots de recouvrement entre chunks.

    Returns:
        Liste de chunks de texte.
    """
    words = text.split()
    chunks = []

    if len(words) <= chunk_size:
        return [text]

    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += chunk_size - overlap

    return chunks