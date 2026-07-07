"""🎬 Traitement des vidéos MP4 — Extraction audio et transcription via API."""

import os
import subprocess
from typing import Optional

import imageio_ffmpeg


# ── API Groq (transcription cloud) ─────────────────────────────────────────

def _get_groq_client():
    """Retourne le client Groq si la clé API est configurée."""
    from groq import Groq
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    return Groq(api_key=api_key)


def transcribe_with_groq(audio_path: str, language: str = "fr") -> dict:
    """Transcrit un fichier audio via l'API Groq (Whisper large-v3).

    Args:
        audio_path: Chemin vers le fichier audio WAV.
        language: Langue ("fr", "en", ou None pour auto-détection).

    Returns:
        Dict avec "text", "segments", "language".

    Raises:
        RuntimeError: Si GROQ_API_KEY n'est pas configurée.
    """
    client = _get_groq_client()
    if client is None:
        raise RuntimeError(
            "GROQ_API_KEY non configurée. "
            "Ajoutez-la dans votre fichier .env pour la transcription vidéo."
        )

    with open(audio_path, "rb") as f:
        file_data = f.read()
        filename = os.path.basename(audio_path)

    transcription = client.audio.transcriptions.create(
        file=(filename, file_data),
        model="whisper-large-v3",
        language=language,
        response_format="verbose_json",
    )

    # Formater les segments comme l'ancien Whisper local
    segments = []
    for seg in getattr(transcription, "segments", []):
        segments.append({
            "start": seg.get("start", 0),
            "end": seg.get("end", 0),
            "text": seg.get("text", ""),
        })

    return {
        "text": transcription.text.strip(),
        "segments": segments,
        "language": language or "unknown",
    }


# ── Extraction audio (locale, via ffmpeg) ──────────────────────────────────

def _get_ffmpeg_path() -> str:
    """Retourne le chemin vers le binaire ffmpeg fourni par imageio-ffmpeg."""
    return imageio_ffmpeg.get_ffmpeg_exe()


def extract_audio_from_mp4(video_path: str, audio_path: Optional[str] = None) -> str:
    """Extrait la piste audio d'un fichier MP4 en WAV.

    Args:
        video_path: Chemin vers le fichier MP4.
        audio_path: Chemin de sortie pour le WAV (auto-généré si None).

    Returns:
        Chemin vers le fichier audio WAV extrait.
    """
    if audio_path is None:
        audio_path = video_path.rsplit(".", 1)[0] + "_audio.wav"

    ffmpeg = _get_ffmpeg_path()

    cmd = [
        ffmpeg,
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        "-y",
        audio_path,
    ]

    subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )

    return audio_path


# ── Pipeline complet ───────────────────────────────────────────────────────

def process_video(video_path: str, language: str = "fr") -> dict:
    """Traite une vidéo complète : extraction audio + transcription API.

    Args:
        video_path: Chemin vers le fichier MP4.
        language: Langue pour la transcription.

    Returns:
        Dict avec les clés :
            - "text" : texte transcrit
            - "segments" : segments avec timings
            - "duration" : durée de la vidéo en secondes
    """
    audio_path = video_path.rsplit(".", 1)[0] + "_audio.wav"

    try:
        # 1. Extraire l'audio (via ffmpeg, en local)
        extract_audio_from_mp4(video_path, audio_path)

        # 2. Transcrire via Groq API (cloud)
        result = transcribe_with_groq(audio_path, language)

        # 3. Durée approximative
        duration = _get_video_duration(video_path)

        return {
            "text": result["text"],
            "segments": result["segments"],
            "duration": duration,
        }
    finally:
        # Nettoyer le fichier audio temporaire
        if os.path.exists(audio_path):
            os.unlink(audio_path)


def _get_video_duration(video_path: str) -> float:
    """Récupère la durée d'une vidéo en secondes via ffmpeg."""
    ffmpeg = _get_ffmpeg_path()

    cmd = [ffmpeg, "-i", video_path, "-f", "null", "-"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        for line in result.stderr.split("\n"):
            if "Duration" in line:
                duration_str = line.split("Duration:")[1].split(",")[0].strip()
                parts = duration_str.split(":")
                hours = float(parts[0])
                minutes = float(parts[1])
                seconds = float(parts[2])
                return hours * 3600 + minutes * 60 + seconds
        return 0.0
    except (ValueError, IndexError, subprocess.CalledProcessError):
        return 0.0