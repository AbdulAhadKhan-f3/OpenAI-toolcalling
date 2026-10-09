"""Nemotron 3.5 ASR Streaming 0.6B — CPU-only streaming + batch inference.

Two streaming modes:
  cache   Real cache-aware streaming via model.conformer_stream_step (default).
  window  Fallback: re-transcribes a rolling window of recent audio about once
          per second. Slower and less elegant, but uses only model.transcribe(),
          which is known to work.

If "cache" mode raises on the first chunk, the full traceback is logged and the
session switches to "window" mode automatically, so you always get a transcript.

Environment variables:
    ASR_CHUNK_MS      80 / 320 / 560 / 1120 (cache mode). Default 320.
    ASR_LANG          Language code, e.g. "en-US". Default "en-US".
    ASR_THREADS       CPU threads for torch. Default: all cores.
    ASR_STREAM_MODE   "cache" (default) or "window".
"""
from __future__ import annotations

import os

# Force CPU — must happen BEFORE torch is imported
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")

import io
import logging
import re
import threading

import librosa
import numpy as np
import torch

logging.getLogger("nemo_logger").setLevel(logging.ERROR)

torch.set_grad_enabled(False)
_CPU = torch.device("cpu")
torch.set_num_threads(int(os.getenv("ASR_THREADS", str(os.cpu_count() or 4))))

from core.logger import get_logger  # noqa: E402

log = get_logger(__name__)

_MODEL_NAME = "nvidia/nemotron-speech-streaming-en-0.6b"
_LANG = os.getenv("ASR_LANG", "en-US")
_SAMPLE_RATE = 16_000
_HOP = 160                      # 10 ms mel hop at 16 kHz
_STREAM_MODE = os.getenv("ASR_STREAM_MODE", "cache").lower()

# chunk length (ms) -> att_context_size supported by this checkpoint
_ATT_CONTEXT = {80: [70, 0], 160: [70, 1], 560: [70, 6], 1120: [70, 13]}
_CHUNK_MS = int(os.getenv("ASR_CHUNK_MS", "560"))
if _CHUNK_MS not in _ATT_CONTEXT:
    log.warning("ASR_CHUNK_MS=%s invalid; using 560 (valid: %s)",
                _CHUNK_MS, sorted(_ATT_CONTEXT))
    _CHUNK_MS = 560

# window-mode settings
_WIN_INFER_EVERY_S = 1.0        # run the model every N seconds of new audio
_WIN_MAX_S = 15.0               # commit text and reset window after this long
_HEALTH_CHECK_S = 6.0           # cache mode must produce text within this much speech

_model = None
_cache_mode_ready = False
_lock = threading.Lock()         # guards model loading
_infer_lock = threading.Lock()   # serialises inference across sessions


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def get_model():
    """Load the Nemotron ASR model once; reuse across all calls."""
    global _model, _cache_mode_ready
    with _lock:
        if _model is None:
            log.info("Loading %s ...", _MODEL_NAME)
            import nemo.collections.asr as nemo_asr

            m = nemo_asr.models.ASRModel.from_pretrained(
                model_name=_MODEL_NAME, map_location=_CPU
            )
            m = m.to(_CPU)
            m.eval()

            try:  # deterministic features for streaming
                m.preprocessor.featurizer.dither = 0.0
                m.preprocessor.featurizer.pad_to = 0
            except Exception:
                log.exception("Could not adjust preprocessor")

            try:  # configure cache-aware streaming
                m.encoder.set_default_att_context_size(_ATT_CONTEXT[_CHUNK_MS])
                m.encoder.setup_streaming_params()
                _cache_mode_ready = True
                log.info("Streaming configured: chunk=%d ms, att_context=%s, cfg=%s",
                         _CHUNK_MS, _ATT_CONTEXT[_CHUNK_MS], m.encoder.streaming_cfg)
            except Exception:
                _cache_mode_ready = False
                log.exception("Cache-aware streaming setup failed; window mode only")

            _model = m
            log.info("Nemotron ASR model ready.")
    return _model


_TAG_RE = re.compile(r"<[^<>\s]{1,16}>")      # <en-US>, <eou>, <unk> ...


def _text_of(x) -> str:
    if x is None:
        return ""
    t = str(x.text if hasattr(x, "text") else x)
    t = _TAG_RE.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def _first_text(result) -> str:
    """Pull the first transcript out of whatever transcribe() returned."""
    if isinstance(result, tuple):          # some versions return (best, all)
        result = result[0]
    if isinstance(result, list) and result:
        return _text_of(result[0])
    return ""


def _transcribe_samples(model, samples: np.ndarray) -> str:
    """Batch-transcribe a float32 16 kHz mono array."""
    audio = samples.astype(np.float32)
    with _infer_lock, torch.no_grad():
        try:
            res = model.transcribe([audio], batch_size=1,  verbose=False)
        except TypeError:                  # older NeMo without `verbose`
            res = model.transcribe([audio], batch_size=1)
    return _first_text(res)


# ---------------------------------------------------------------------------
# Batch transcription (used by /api/transcribe)
# ---------------------------------------------------------------------------

def transcribe_bytes(audio_bytes: bytes) -> str:
    """Transcribe raw audio file bytes -> text."""
    speech, _ = librosa.load(io.BytesIO(audio_bytes), sr=_SAMPLE_RATE, mono=True)
    if speech.size == 0:
        return ""
    return _transcribe_samples(get_model(), speech)


# ---------------------------------------------------------------------------
# Streaming session (used by live_session.py)
# ---------------------------------------------------------------------------

class StreamingSession:
    """
    One live session.

        sess = StreamingSession()
        partial = sess.feed(pcm16_bytes)   # call repeatedly
        final = sess.finish()
    """

    def __init__(self):
        self._model = get_model()
        self._mode = "cache" if (_STREAM_MODE == "cache" and _cache_mode_ready) else "window"
        self._text_so_far = ""
        self._buffer = np.empty(0, dtype=np.float32)   # raw audio awaiting a full chunk
        self._chunk_samples = int(_CHUNK_MS * _SAMPLE_RATE / 1000)
        self._history: list[np.ndarray] = []   # raw audio kept until cache mode proves it works
        self._hist_done = False
        self._init_cache_state()
        self._init_window_state()
        log.info("StreamingSession created (mode=%s, chunk=%d ms, lang=%s)",
                 self._mode, _CHUNK_MS, _LANG)

    # ---- public API -------------------------------------------------------
    def feed(self, pcm_bytes: bytes) -> str:
        samples = (
            np.frombuffer(pcm_bytes[: len(pcm_bytes) // 2 * 2], dtype=np.int16)
            .astype(np.float32) / 32768.0
        )
        if self._mode == "cache":
            try:
                if not self._hist_done:
                    self._history.append(samples)
                self._buffer = np.concatenate([self._buffer, samples])
                while len(self._buffer) >= self._chunk_samples:
                    chunk = self._buffer[: self._chunk_samples]
                    self._buffer = self._buffer[self._chunk_samples:]
                    self._cache_push_audio(chunk)
                self._check_cache_health()
                return self._text_so_far
            except Exception:
                log.exception("Cache-aware streaming failed; switching to window mode")
                self._mode = "window"
                self._buffer = np.empty(0, dtype=np.float32)
                # fall through: window mode starts with this chunk onward
        return self._window_feed(samples)

    def finish(self) -> str:
        if self._mode == "cache":
            try:
                return self._cache_finish()
            except Exception:
                log.exception("Cache-aware finish failed")
                return self._text_so_far
        return self._window_finish()

    # ---- cache-aware mode -------------------------------------------------
    def _init_cache_state(self):
        if self._mode != "cache":
            return
        enc = self._model.encoder
        cfg = enc.streaming_cfg
        self._first_frames, self._next_frames = self._pair(cfg.chunk_size)
        _, self._pre_size = self._pair(cfg.pre_encode_cache_size)
        self._drop = cfg.drop_extra_pre_encoded or 0
        n_mels = int(self._model.cfg.preprocessor.features)
        self._n_mels = n_mels
        self._mel_q = torch.zeros((1, n_mels, 0))
        self._pre_cache = torch.zeros((1, n_mels, max(self._pre_size, 0)))
        self._c_ch, self._c_time, self._c_len = enc.get_initial_cache_state(batch_size=1)
        self._prev_hyp = None
        self._pred_out = None
        self._step = 0

    @staticmethod
    def _pair(v):
        if isinstance(v, (list, tuple)):
            return (int(v[0]), int(v[1])) if len(v) > 1 else (int(v[0]), int(v[0]))
        return int(v), int(v)

    def _cache_push_audio(self, chunk: np.ndarray):
        m = self._model
        sig = torch.from_numpy(chunk).unsqueeze(0)
        sig_len = torch.tensor([chunk.shape[0]])
        with _infer_lock, torch.no_grad():
            mel, _ = m.preprocessor(input_signal=sig, length=sig_len)
        mel = mel[:, :, : chunk.shape[0] // _HOP]      # drop the extra centre frame
        self._mel_q = torch.cat([self._mel_q, mel], dim=-1)
        self._drain(last=False)

    def _drain(self, last: bool):
        while True:
            need = self._first_frames if self._step == 0 else self._next_frames
            if self._mel_q.shape[-1] < need:
                break
            frames = self._mel_q[:, :, :need]
            self._mel_q = self._mel_q[:, :, need:]
            self._run_step(frames, keep_all=False)

    def _run_step(self, frames: torch.Tensor, keep_all: bool):
        m = self._model
        mel_in = frames
        if self._step > 0 and self._pre_size > 0:
            mel_in = torch.cat([self._pre_cache, frames], dim=-1)
        if self._pre_size > 0:
            self._pre_cache = mel_in[:, :, -self._pre_size:]
        mel_len = torch.tensor([mel_in.shape[-1]])

        with _infer_lock, torch.no_grad():
            out = m.conformer_stream_step(
                processed_signal=mel_in,
                processed_signal_length=mel_len,
                cache_last_channel=self._c_ch,
                cache_last_time=self._c_time,
                cache_last_channel_len=self._c_len,
                keep_all_outputs=keep_all,
                previous_hypotheses=self._prev_hyp,
                previous_pred_out=self._pred_out,
                drop_extra_pre_encoded=0 if self._step == 0 else self._drop,
                return_transcription=True,
            )
        # (pred_out, texts, cache_ch, cache_time, cache_len, hypotheses)
        self._pred_out, texts, self._c_ch, self._c_time, self._c_len, self._prev_hyp = out[:6]
        self._step += 1
        if self._step <= 3 or self._step % 50 == 0:
            log.info("stream step %d: texts=%r | pred_out=%r | hyp=%r",
                     self._step, str(texts)[:200], str(self._pred_out)[:120],
                     str(self._prev_hyp)[:200])
        t = _first_text(texts)
        if t:
            self._text_so_far = t

    def _cache_finish(self) -> str:
        # push leftover raw audio (padded to a full chunk), then flush the lookahead
        if len(self._buffer) > 0:
            pad = np.zeros(self._chunk_samples - len(self._buffer), dtype=np.float32)
            self._cache_push_audio(np.concatenate([self._buffer, pad]))
            self._buffer = np.empty(0, dtype=np.float32)
        need = self._first_frames if self._step == 0 else self._next_frames
        rest = self._mel_q.shape[-1]
        if rest < need:
            self._mel_q = torch.cat(
                [self._mel_q, torch.zeros((1, self._n_mels, need - rest))], dim=-1
            )
        self._run_step(self._mel_q[:, :, :need], keep_all=True)
        self._mel_q = self._mel_q[:, :, need:]
        return self._text_so_far

    def _check_cache_health(self):
        """If cache mode yields no text for several seconds of real speech, switch to window mode."""
        if self._hist_done or self._mode != "cache":
            return
        if self._text_so_far:
            log.info("Cache-aware streaming is producing text; health check passed.")
            self._hist_done, self._history = True, []
            return
        audio = np.concatenate(self._history) if self._history else np.empty(0, np.float32)
        secs = len(audio) / _SAMPLE_RATE
        if secs < _HEALTH_CHECK_S:
            return
        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms > 0.01:
            log.warning("Cache mode gave NO text after %.1fs of audio (rms=%.4f). "
                        "Switching this session to window mode.", secs, rms)
            self._mode = "window"
            self._buffer = np.empty(0, dtype=np.float32)
            self._win = audio
            self._since = 0
            self._window_infer()
            self._text_so_far = self._joined()
            self._hist_done, self._history = True, []
        elif secs > 30:                      # long silence: stop hoarding audio
            self._hist_done, self._history = True, []

    # ---- window (fallback) mode ------------------------------------------
    # Inference runs in a worker thread; feed() never waits for it. If audio
    # arrives faster than the model runs, intermediate windows are skipped.
    def _init_window_state(self):
        self._win = np.empty(0, dtype=np.float32)
        self._since = 0
        self._committed = ""
        self._win_text = ""
        self._win_lock = threading.Lock()
        self._win_event = threading.Event()
        self._win_stop = False
        self._win_thread = None

    def _joined(self) -> str:
        return (self._committed + " " + self._win_text).strip()

    def _ensure_worker(self):
        if self._win_thread is None:
            self._win_thread = threading.Thread(target=self._worker, daemon=True)
            self._win_thread.start()

    def _worker(self):
        while True:
            self._win_event.wait()
            self._win_event.clear()
            if self._win_stop:
                return
            self._window_infer()

    def _window_feed(self, samples: np.ndarray) -> str:
        with self._win_lock:
            self._win = np.concatenate([self._win, samples])
            self._since += len(samples)
            due = self._since >= int(_WIN_INFER_EVERY_S * _SAMPLE_RATE)
            if due:
                self._since = 0
        if due:
            self._ensure_worker()
            self._win_event.set()
        self._text_so_far = self._joined()
        return self._text_so_far

    def _window_infer(self):
        with self._win_lock:
            audio = self._win.copy()
        if len(audio) < _SAMPLE_RATE // 4:
            return
        try:
            text = _transcribe_samples(self._model, audio)
        except Exception:
            log.exception("Window transcription failed")
            return
        with self._win_lock:
            self._win_text = text
            if len(audio) > int(_WIN_MAX_S * _SAMPLE_RATE):
                # commit what was transcribed; keep any audio that arrived meanwhile
                self._committed = self._joined()
                self._win = self._win[len(audio):]
                self._win_text = ""

    def _window_finish(self) -> str:
        self._win_stop = True
        self._win_event.set()
        if self._win_thread is not None:
            self._win_thread.join(timeout=60)
        self._window_infer()
        self._text_so_far = self._joined()
        return self._text_so_far