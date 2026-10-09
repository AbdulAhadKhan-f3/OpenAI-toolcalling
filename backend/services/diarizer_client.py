"""Client for the Nemotron 3 Diarization service (Kaggle or any GPU machine)."""
import json
import os
import uuid
import urllib.request
from pathlib import Path
from core.logger import get_logger

URL_FILE = Path(__file__).resolve().parent.parent / "diarizer_url.txt"
HEADERS = {"User-Agent": "ClinScribe/1.0"}

_url = None
log = get_logger(__name__)


class DiarizerError(Exception):
    """Network/HTTP/parse failure. Different from 'no speech' (empty list)."""


def get_url() -> str:
    global _url
    if _url is None:
        raw = os.getenv("DIARIZER_URL") or (URL_FILE.read_text().strip() if URL_FILE.exists() else "")
        _url = raw.strip().rstrip("/")
    return _url


def set_url(url: str):
    global _url
    _url = url.strip().rstrip("/")
    URL_FILE.write_text(_url)


def configured() -> bool:
    return bool(get_url())


def status() -> dict:
    if not configured():
        return {"url": "", "reachable": False}
    try:
        req = urllib.request.Request(get_url() + "/health", headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as reply:
            return {"url": get_url(), "reachable": True, **json.load(reply)}
    except Exception as exc:
        return {"url": get_url(), "reachable": False, "error": str(exc)[:200]}


def new_session() -> str:
    return str(uuid.uuid4())


def diarize(pcm: bytes, session: str, final: bool = False, timeout: float = 60) -> list[dict]:
    """Send NEW audio (16 kHz mono PCM16). The server keeps the session audio and
    returns segments for the WHOLE conversation so far, in session time.
    Returns [] for silence; raises DiarizerError on failure."""
    if not configured():
        return []

    req = urllib.request.Request(
        f"{get_url()}/diarize?session={session}&final={int(final)}",
        data=pcm,
        method="POST",
        headers={**HEADERS, "Content-Type": "application/octet-stream"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as reply:
            data = json.load(reply)
    except Exception as e:
        raise DiarizerError(str(e)) from e

    segments = data.get("segments", [])
    log.info("Diarizer: %d segments, %.1fs total audio", len(segments), data.get("seconds", 0))
    return segments