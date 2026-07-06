"""🎬 Traitement des vidéos MP4 — Extraction audio et transcription."""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import imageio_ffmpeg
import whisper


# ── Modèle Whisper (chargé une seule fois) ───────────────────────────────
_MODEL: Optional[whisper.Whisper] = None


def _get_whisper_model(model_size: str = "base") -> whisper.Whisper:
    """Charge le modèle Whisper (singleton).

    Args:
        model_size: Taille du modèle ("tiny", "base", "small", "medium", "large").

    Returns:
        Instance du modèle Whisper.
    """
    global _MODEL
    if _MODEL is None:
        _MODEL = whisper.load_model(model_size)
    return _MODEL


def _get_ffmpeg_path() -> str:
    """Retourne le chemin vers le binaire ffmpeg fourni par imageio-ffmpeg.

    Returns:
        Chemin absolu vers ffmpeg.
    """
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
        "-vn",              # Pas de vidéo
        "-acodec", "pcm_s16le",  # Codec audio WAV
        "-ar", "16000",     # Fréquence 16 kHz (optimal pour Whisper)
        "-ac", "1",         # Mono
        "-y",               # Écraser si existe
        audio_path,
    ]

    subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )

    return audio_path


def transcribe_audio(
    audio_path: str,
    language: Optional[str] = "fr",
    model_size: str = "base",
) -> dict:
    """Transcrit un fichier audio avec Whisper.

    Args:
        audio_path: Chemin vers le fichier audio.
        language: Langue (None = auto-détection, "fr" = français).
        model_size: Taille du modèle Whisper.

    Returns:
        Dict avec les clés :
            - "text" : texte transcrit complet
            - "segments" : liste des segments avec timings
            - "language" : langue détectée
    """
    model = _get_whisper_model(model_size)

    result = model.transcribe(
        audio_path,
        language=language,
        task="transcribe",
        verbose=False,
    )

    return {
        "text": result["text"].strip(),
        "segments": result.get("segments", []),
        "language": result.get("language", language),
    }


def process_video(
    video_path: str,
    language: str = "fr",
    model_size: str = "base",
) -> dict:
    """Traite une vidéo complète : extraction audio + transcription.

    Args:
        video_path: Chemin vers le fichier MP4.
        language: Langue pour la transcription.
        model_size: Taille du modèle Whisper.

    Returns:
        Dict avec les clés :
            - "text" : texte transcrit
            - "segments" : segments avec timings
            - "duration" : durée de la vidéo en secondes
    """
    # 1. Extraire l'audio
    audio_path = video_path.rsplit(".", 1)[0] + "_audio.wav"

    try:
        extract_audio_from_mp4(video_path, audio_path)

        # 2. Transcrire
        result = transcribe_audio(audio_path, language, model_size)

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
    """Récupère la durée d'une vidéo en secondes via ffmpeg.

    Args:
        video_path: Chemin vers la vidéo.

    Returns:
        Durée en secondes.
    """
    ffmpeg = _get_ffmpeg_path()

    cmd = [
        ffmpeg,
        "-i", video_path,
        "-f", "null",
        "-",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
        # La durée est dans stderr, format: "  Duration: 00:01:30.50, start: ..."
        for line in result.stderr.split("\n"):
            if "Duration" in line:
                duration_str = line.split("Duration:")[1].split(",")[0].strip()
                # Format: HH:MM:SS.mmm
                parts = duration_str.split(":")
                hours = float(parts[0])
                minutes = float(parts[1])
                seconds = float(parts[2])
                return hours * 3600 + minutes * 60 + seconds
        return 0.0
    except (ValueError, IndexError, subprocess.CalledProcessError):
        return 0.0