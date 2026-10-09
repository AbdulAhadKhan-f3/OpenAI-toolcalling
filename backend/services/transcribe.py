"""Audio → medical transcript using local Nemotron 3.5 ASR Streaming 0.6B.

Uses the same model as the live streaming path, so there is only one model
loaded in memory regardless of which endpoint is called first.
"""

from fastapi import HTTPException

from services.nemotron_asr import transcribe_bytes
from services.validation import sentences


ALLOWED = (
    ".mp3",
    ".wav",
    ".m4a",
    ".mp4",
    ".webm",
    ".ogg",
    ".flac",
    ".mpeg",
    ".mpga",
)


def transcribe_audio(data: bytes) -> dict:
    """Transcribe uploaded audio with Nemotron 3.5 ASR (batch mode)."""

    if not data:
        raise HTTPException(400, "The audio file is empty.")

    try:
        raw = transcribe_bytes(data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Transcription failed: {e}")

    if not raw:
        raise HTTPException(422, "No speech was detected in the audio.")

    return {
        "transcript": "\n".join(sentences(raw)),
        "raw": raw,
        "warning": "",
    }