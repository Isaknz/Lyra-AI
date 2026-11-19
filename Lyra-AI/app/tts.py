"""Voz local con Piper: texto a voz sin salir del equipo."""

from __future__ import annotations

import io
import os
import threading
import wave
from pathlib import Path

import httpx

VOICE_DIR = Path(__file__).resolve().parent.parent / "models" / "voices"
VOICE_NAME = os.getenv("OH_TTS_VOICE", "es_ES-davefx-medium")
VOICE_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

_voice = None
_lock = threading.Lock()


def voice_path() -> Path:
    return VOICE_DIR / f"{VOICE_NAME}.onnx"


def _remote_candidates() -> list[str]:
    """URLs posibles para la voz, en orden de preferencia.

    El nombre sigue el patrón ``<locale>-<hablante>-<calidad>``, p. ej.
    ``es_ES-davefx-medium``. En HuggingFace la ruta incluye el idioma y el
    hablante como carpetas: ``es/es_ES/davefx/medium/``. Algunas voces no
    tienen hablante, así que se prueba también la ruta corta.
    """
    parts = VOICE_NAME.split("-")
    if len(parts) < 2:
        return []
    locale, quality = parts[0], parts[-1]
    language = locale.split("_")[0]
    speaker = "-".join(parts[1:-1])
    urls = []
    if speaker:
        urls.append(f"{VOICE_BASE}/{language}/{locale}/{speaker}/{quality}")
    urls.append(f"{VOICE_BASE}/{language}/{locale}/{quality}")
    return urls


def piper_installed() -> bool:
    try:
        import piper  # noqa: F401
    except ImportError:
        return False
    return True


def available() -> bool:
    """La voz está lista o se puede descargar sola."""
    return piper_installed()


def ensure_voice() -> None:
    """Descarga el modelo de voz la primera vez (unos 60 MB)."""
    if voice_path().exists():
        return
    if not piper_installed():
        raise RuntimeError(
            "Falta el paquete de voz. Instálalo con: pip install piper-tts"
        )
    candidates = _remote_candidates()
    if not candidates:
        raise RuntimeError(f"Nombre de voz no válido: {VOICE_NAME}")

    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for folder in candidates:
        try:
            payloads = {}
            for suffix in (".onnx", ".onnx.json"):
                url = f"{folder}/{VOICE_NAME}{suffix}"
                response = httpx.get(url, follow_redirects=True, timeout=180.0)
                response.raise_for_status()
                payloads[suffix] = response.content
        except httpx.HTTPError as exc:
            last_error = exc
            continue
        for suffix, content in payloads.items():
            (VOICE_DIR / f"{VOICE_NAME}{suffix}").write_bytes(content)
        return
    raise RuntimeError(
        f"No se pudo descargar la voz {VOICE_NAME}. Revisa el nombre en "
        f"https://rhasspy.github.io/piper-samples/ ({last_error})"
    )


def _load():
    global _voice
    if _voice is None:
        from piper import PiperVoice

        _voice = PiperVoice.load(str(voice_path()))
    return _voice


def synthesize(text: str) -> bytes:
    """Devuelve un WAV en memoria con el texto hablado."""
    ensure_voice()
    with _lock:
        voice = _load()
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            voice.synthesize_wav(text, wav)
        return buffer.getvalue()
