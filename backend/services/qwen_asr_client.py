"""Streaming ASR via the remote Qwen3-ASR service. Same interface as nemotron_asr.StreamingSession."""
import json
import os
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.logger import get_logger

log = get_logger(__name__)

URL_FILE = Path(__file__).resolve().parent.parent / "diarizer_url.txt"
HEADERS = {"User-Agent": "ClinScribe/1.0"}
SAMPLE_RATE = 16_000
STEP_S = float(os.getenv("QWEN_STEP_S", "1.0"))      # audio seconds per request


def get_url() -> str:
    raw = os.getenv("QWEN_ASR_URL") or (URL_FILE.read_text().strip() if URL_FILE.exists() else "")
    return raw.strip().rstrip("/")


def _post(url: str, session: str, pcm: bytes, final: bool, timeout: float = 60) -> dict:
    req = urllib.request.Request(
        f"{url}/asr?session={session}&final={int(final)}", data=pcm, method="POST",
        headers={**HEADERS, "Content-Type": "application/octet-stream"})
    with urllib.request.urlopen(req, timeout=timeout) as reply:
        return json.load(reply)


class StreamingSession:
    """feed(pcm) returns the transcript so far and never blocks; finish() flushes and returns the final text."""

    def __init__(self):
        self._url = get_url()
        if not self._url:
            raise RuntimeError("Qwen ASR URL not set. Put it in QWEN_ASR_URL or asr_url.txt.")
        self._id = str(uuid.uuid4())
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qwen-asr")
        self._pending = None            # (future, pcm)
        self._buf: list[bytes] = []
        self._buf_s = 0.0
        self._text = ""
        self._failures = 0
        self._next_try = 0.0
        log.info("Qwen ASR session %s (server=%s, step=%.1fs)", self._id[:8], self._url, STEP_S)

    def feed(self, pcm_bytes: bytes) -> str:
        self._buf.append(pcm_bytes)
        self._buf_s += len(pcm_bytes) / 2 / SAMPLE_RATE
        self._collect()
        if self._pending is None and self._buf_s >= STEP_S and time.time() >= self._next_try:
            self._submit(final=False)
        return self._text

    def finish(self) -> str:
        self._collect(block=True)
        self._submit(final=True)         # always send the final flag
        self._collect(block=True)
        self._pool.shutdown(wait=False)
        return self._text

    def _submit(self, final: bool):
        pcm = b"".join(self._buf)
        self._buf, self._buf_s = [], 0.0
        self._pending = (self._pool.submit(_post, self._url, self._id, pcm, final), pcm)

    def _collect(self, block: bool = False):
        if self._pending is None:
            return
        fut, pcm = self._pending
        if not (fut.done() or block):
            return
        self._pending = None
        try:
            out = fut.result()
        except Exception as exc:
            self._failures += 1
            wait = min(2 * self._failures, 15)
            self._next_try = time.time() + wait
            self._buf.insert(0, pcm)     # re-queue so no audio is lost
            self._buf_s += len(pcm) / 2 / SAMPLE_RATE
            log.warning("Qwen ASR call failed (%s). Retry in %ds.", exc, wait)
            return
        self._failures = 0
        text = (out.get("text") or "").strip()
        if text:
            self._text = text