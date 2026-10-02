"""Audio -> transcript using local Nemotron ASR. No OpenAI/LLM calls in this file."""
from fastapi import HTTPException

from checks import sentences

ALLOWED = (".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg", ".flac", ".mpeg", ".mpga")

_local_pipe = None


def _transcribe_nemotron(data: bytes) -> str:
    """Local NVIDIA Nemotron ASR (600M) via transformers. First call downloads/loads the model."""
    global _local_pipe
    if _local_pipe is None:
        from transformers import pipeline
        _local_pipe = pipeline("automatic-speech-recognition",
                               model="nvidia/nemotron-3.5-asr-streaming-0.6b")
    return _local_pipe(data)["text"].strip()      # default language prompt is en-US


def transcribe_audio(data: bytes):
    if not data:
        raise HTTPException(400, "The audio file is empty.")
    try:
        raw = _transcribe_nemotron(data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Transcription failed: {e}")
    if not raw:
        raise HTTPException(422, "No speech was detected in the audio.")
    # No speaker labels here (that would need an LLM call). One sentence per line,
    # so each sentence becomes its own numbered turn in agent.py.
    # The user can add Doctor:/Patient: labels by hand in the review step.
    return {"transcript": "\n".join(sentences(raw)), "raw": raw, "warning": ""}