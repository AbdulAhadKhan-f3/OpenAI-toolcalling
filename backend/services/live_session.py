"""Near-real-time consultation transcript: Nemotron streaming ASR + remote diarizer.

How speakers are assigned:
- Every recognised word is stamped with the AUDIO time at which it appeared.
- The remote diarizer returns speaker segments (session time). Each word is
  matched to a segment, and consecutive words from one speaker become a line.
- The diarizer runs in a background thread so it never stalls the ASR.

WebSocket flow (unchanged for the frontend):
  Browser -> bytes (PCM16 16 kHz)  -> feed()
  Browser -> "stop"                -> finish(), result()
  Server  -> {"type":"line", ...}  -> line updates
"""
from __future__ import annotations

import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from core.logger import get_logger
from services import diarizer_client
if os.getenv("ASR_BACKEND", "nemotron").lower() == "qwen":
    from services.qwen_asr_client import StreamingSession
else:
    from services.nemotron_asr import StreamingSession

log = get_logger(__name__)

SAMPLE_RATE     = 16_000
REMOTE_INTERVAL = float(os.getenv("DIARIZER_INTERVAL", "2.0"))   # audio seconds between calls
DIARIZER_TIMES  = os.getenv("DIARIZER_TIMES", "session").lower()
# Words are emitted a little after they are spoken (chunk + lookahead). Shift
# word times back by this much before matching them to diarizer segments.
WORD_LAG        = float(os.getenv("ASR_WORD_LAG", "0.6"))
NEAR_SEGMENT_S  = 1.0     # a word this close to a segment still gets its speaker
SEC_PER_WORD    = 0.35    # max spread when several words appear in one update
MIN_WORDS_ROLE  = 8       # words per speaker before running the role classifier


class LiveSession:
    """One live consultation, from WebSocket open to 'stop'."""

    def __init__(self):
        self._asr = StreamingSession()

        # diarizer
        self.session_id = diarizer_client.new_session()
        self.use_remote = diarizer_client.configured()
        self.diar_segments: list[dict] = []
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="diar") if self.use_remote else None
        self._pending = None            # (future, pcm, offset, seconds)
        self._diar_audio: list[bytes] = []
        self._diar_seconds = 0.0
        self._sent_seconds = 0.0
        self.next_remote_try = 0.0
        self.remote_failures = 0

        # transcript state
        self._audio_seconds = 0.0       # total audio received (the session clock)
        self._words: list[dict] = []    # {"w": str, "t": audio_time}
        self._last_t = 0.0
        self._prev_text = ""
        self._lines: list[dict] = []    # {speaker_id, text, start, end}

        self.role_map: dict[int, str] = {}
        self.roles_classified = False
        self._role_future = None        # background role-classification call
        self._role_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="roles")

        log.info("LiveSession ready (diarizer=%s)", "on" if self.use_remote else "off")

    # ------------------------------------------------------------------ public

    def feed(self, pcm_bytes: bytes) -> list[dict]:
        n_sec = (len(pcm_bytes) // 2) / SAMPLE_RATE
        self._audio_seconds += n_sec
        self._diar_audio.append(pcm_bytes)
        self._diar_seconds += n_sec

        updates: list[dict] = []

        partial = self._asr.feed(pcm_bytes)
        if partial and partial != self._prev_text:
            self._prev_text = partial
            self._update_words(partial)
            self._rebuild_lines()
            if self._lines:
                updates.append(self._message(len(self._lines) - 1))

        if self.use_remote:
            updates.extend(self._poll_remote())
            self._maybe_submit()

        return updates

    def finish(self) -> list[dict]:
        updates: list[dict] = []

        final_text = self._asr.finish()
        if final_text and final_text != self._prev_text:
            self._prev_text = final_text
            self._update_words(final_text)
            self._rebuild_lines()
            if self._lines:
                updates.append(self._message(len(self._lines) - 1))

        if self.use_remote:
            updates.extend(self._poll_remote(block=True))      # finish any in-flight call
            if self._diar_audio or self._sent_seconds > 0:
                self._submit(final=True)                       # always send the final flag
                updates.extend(self._poll_remote(block=True))
            self._poll_roles(block=True)
            self._pool.shutdown(wait=False)
            self._role_pool.shutdown(wait=False)

        if self._classify_final():                             # roles from the full conversation
            updates.extend(self._all_messages())

        return updates

    def result(self) -> dict:
        out = [
            {
                "type":       "line",
                "index":      i,
                "speaker_id": l["speaker_id"],
                "speaker":    self._name(l["speaker_id"]),
                "text":       l["text"],
                "start":      round(l["start"], 1),
            }
            for i, l in enumerate(self._lines)
        ]
        return {
            "lines":      out,
            "transcript": "\n".join(f"{l['speaker']}: {l['text']}" for l in out),
        }

    # ----------------------------------------------------------- words & lines

    def _update_words(self, text: str):
        """Sync the stamped word list with the latest transcript text."""
        words = text.split()
        keep = min(len(self._words), len(words))
        self._words = self._words[:keep]
        for i in range(keep):
            self._words[i]["w"] = words[i]

        new = words[keep:]
        if new:
            now = self._audio_seconds
            start = max(self._last_t, now - SEC_PER_WORD * len(new))
            k = len(new)
            for j, w in enumerate(new):
                self._words.append({"w": w, "t": start + (now - start) * (j + 1) / k})
        self._last_t = self._audio_seconds

    def _speaker_at(self, t: float) -> int | None:
        best, best_d = None, NEAR_SEGMENT_S
        for seg in self.diar_segments:
            if seg["start"] <= t <= seg["end"]:
                return seg["speaker"]
            d = seg["start"] - t if t < seg["start"] else t - seg["end"]
            if d < best_d:
                best, best_d = seg["speaker"], d
        return best

    def _rebuild_lines(self):
        lines: list[dict] = []
        last = None
        for w in self._words:
            sid = self._speaker_at(w["t"] - WORD_LAG)
            if sid is None:
                sid = last if last is not None else 0
            last = sid
            if lines and lines[-1]["speaker_id"] == sid:
                lines[-1]["words"].append(w["w"])
                lines[-1]["end"] = w["t"]
            else:
                lines.append({"speaker_id": sid, "words": [w["w"]],
                              "start": w["t"], "end": w["t"]})
        for l in lines:
            l["text"] = " ".join(l.pop("words"))
        self._lines = lines

    def _name(self, speaker_id: int) -> str:
        return self.role_map.get(speaker_id, f"Speaker {speaker_id + 1}")

    def _message(self, index: int) -> dict:
        l = self._lines[index]
        return {
            "type":       "line",
            "index":      index,
            "speaker_id": l["speaker_id"],
            "speaker":    self._name(l["speaker_id"]),
            "text":       l["text"],
            "start":      round(l["start"], 1),
        }

    # --------------------------------------------------- diarizer integration

    def _maybe_submit(self):
        if self._pending or not self._diar_audio:
            return
        if self._diar_seconds < REMOTE_INTERVAL or time.time() < self.next_remote_try:
            return
        self._submit(final=False)

    def _submit(self, final: bool):
        pcm = b"".join(self._diar_audio)
        secs = len(pcm) / 2 / SAMPLE_RATE
        offset = self._sent_seconds
        self._diar_audio = []
        self._diar_seconds = 0.0
        fut = self._pool.submit(diarizer_client.diarize, pcm, self.session_id, final)
        self._pending = (fut, pcm, offset, secs)

    def _all_messages(self) -> list[dict]:
        return [self._message(i) for i in range(len(self._lines))]

    def _poll_roles(self, block: bool = False) -> bool:
        """Collect a finished background role classification. True if roles changed."""
        f = self._role_future
        if f is None or not (f.done() or block):
            return False
        self._role_future = None
        try:
            roles = f.result()
        except Exception:
            log.exception("Role classification failed")
            return False
        if roles:
            self.role_map = roles
            self.roles_classified = True
            log.info("Roles mapped: %s", roles)
            return True
        return False

    def _poll_remote(self, block: bool = False) -> list[dict]:
        roles_changed = self._poll_roles(block)
        if not self._pending:
            return self._all_messages() if roles_changed else []
        fut, pcm, offset, secs = self._pending
        if not (fut.done() or block):
            return self._all_messages() if roles_changed else []
        self._pending = None

        try:
            segments = fut.result()
        except Exception as e:                      # DiarizerError or anything else
            self.remote_failures += 1
            wait = min(5 * self.remote_failures, 30)
            self.next_remote_try = time.time() + wait
            self._diar_audio.insert(0, pcm)         # re-queue so nothing is lost
            self._diar_seconds += secs
            log.warning("Diarizer failed (%s). Retry in %ds.", e, wait)
            return self._all_messages() if roles_changed else []

        self.remote_failures = 0
        self.next_remote_try = 0.0
        self._sent_seconds += secs

        if not segments:
            return self._all_messages() if roles_changed else []

        self._store_segments(segments, offset)
        self._relabel()
        return self._all_messages()

    def _store_segments(self, segments: list[dict], offset: float):
        parsed = [{"start": float(s["start"]), "end": float(s["end"]),
                   "speaker": int(s["speaker"])} for s in segments]
        if DIARIZER_TIMES == "session":
            self.diar_segments = parsed             # server returns the whole session each time
        else:
            for s in parsed:
                self.diar_segments.append({"start": s["start"] + offset,
                                           "end":   s["end"] + offset,
                                           "speaker": s["speaker"]})

    def _speaker_texts(self) -> dict[int, list[str]]:
        texts: defaultdict[int, list[str]] = defaultdict(list)
        for l in self._lines:
            texts[l["speaker_id"]].append(l["text"])
        return dict(texts)

    def _relabel(self):
        self._rebuild_lines()
        texts = self._speaker_texts()
        from services.role_classifier import classify_roles

        # 1) instant provisional labels (no LLM), until the LLM confirms
        if not self.roles_classified and not self.role_map:
            quick = classify_roles(texts, quick=True)
            if quick:
                self.role_map = quick
                log.info("Provisional roles (heuristic): %s", quick)

        # 2) LLM verification in its own thread, once there is enough speech
        if self.roles_classified or self._role_future is not None:
            return
        enough = [s for s, t in texts.items()
                  if sum(len(x.split()) for x in t) >= MIN_WORDS_ROLE]
        if len(enough) >= 2:
            self._role_future = self._role_pool.submit(classify_roles, texts)

    def _classify_final(self) -> bool:
        """Re-classify on the whole conversation at the end, even if it is short."""
        texts = self._speaker_texts()
        if len(texts) < 2:
            log.info("Only %d speaker(s) found; cannot assign roles.", len(texts))
            return False
        from services.role_classifier import classify_roles
        roles = classify_roles(texts, force=True)
        if roles:
            self.role_map = roles
            self.roles_classified = True
            log.info("Final roles: %s", roles)
            return True
        return False