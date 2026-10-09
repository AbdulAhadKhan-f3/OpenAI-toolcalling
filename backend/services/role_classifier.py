"""Doctor vs Patient role classifier (HF DistilBERT text classifier + heuristic fallback)."""
import os
import re
import threading

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from core.logger import get_logger

log = get_logger(__name__)

MODEL_ID = os.getenv("ROLE_MODEL", "LukeGPT88/patient-doctor-text-classifier-eng")
DOCTOR_LABEL = os.getenv("ROLE_DOCTOR_LABEL", "").strip()   # e.g. "LABEL_1" if names are generic
MIN_WORDS = int(os.getenv("ROLE_MIN_WORDS", "8"))           # live: words each speaker needs before the model runs
QUICK_MIN_WORDS = 3
MARGIN = float(os.getenv("ROLE_MARGIN", "0.05"))            # min gap in mean P(doctor) to trust the model
MAX_CHUNK_WORDS = 40                                        # utterance-sized pieces suit this model best

_lock = threading.Lock()
_tok = _model = None
_doctor_idx: int | None = None


def _load():
    """Load once (thread-safe). Call warm() at startup so the first consult is not slow."""
    global _tok, _model, _doctor_idx
    if _model is not None:
        return
    with _lock:
        if _model is not None:
            return
        tok = AutoTokenizer.from_pretrained(MODEL_ID)
        model = AutoModelForSequenceClassification.from_pretrained(MODEL_ID).eval()
        id2label = {int(i): str(l) for i, l in model.config.id2label.items()}
        log.info("Role model labels: %s", id2label)

        idx = None
        if DOCTOR_LABEL:
            idx = next((i for i, l in id2label.items() if l.lower() == DOCTOR_LABEL.lower()), None)
        else:
            idx = next((i for i, l in id2label.items()
                        if any(k in l.lower() for k in ("doctor", "clinician", "physician"))), None)
        if idx is None:
            raise RuntimeError(
                f"Cannot tell which label means 'doctor' in {id2label}. Set ROLE_DOCTOR_LABEL.")
        _tok, _doctor_idx, _model = tok, idx, model


def warm():
    try:
        _load()
    except Exception:
        log.exception("Role model failed to load; the heuristic will be used")


def _word_count(texts: list[str]) -> int:
    return sum(len(t.split()) for t in texts)


def _question_ratio(texts: list[str]) -> float:
    joined = " ".join(texts)
    return joined.count("?") / max(len(joined.split()), 1)


def _chunks(texts: list[str]) -> list[str]:
    out = []
    for t in texts:
        for sent in re.split(r"(?<=[.?!])\s+", t.strip()):
            words = sent.split()
            for i in range(0, len(words), MAX_CHUNK_WORDS):
                piece = " ".join(words[i:i + MAX_CHUNK_WORDS])
                if piece:
                    out.append(piece)
    return out


@torch.inference_mode()
def _doctor_score(texts: list[str]) -> float | None:
    """Mean P(doctor) over a speaker's chunks, weighted by chunk length."""
    chunks = _chunks(texts)
    if not chunks:
        return None
    _load()
    total, weight = 0.0, 0
    for i in range(0, len(chunks), 16):
        batch = chunks[i:i + 16]
        enc = _tok(batch, return_tensors="pt", padding=True, truncation=True, max_length=128)
        probs = torch.softmax(_model(**enc).logits, dim=-1)[:, _doctor_idx]
        for p, c in zip(probs.tolist(), batch):
            w = len(c.split())
            total += p * w
            weight += w
    return total / weight if weight else None


def _roles(all_ids, doctor, patient) -> dict[int, str]:
    roles = {s: "Other" for s in all_ids}
    roles[doctor], roles[patient] = "Doctor", "Patient"
    return roles


def classify_roles(speaker_texts: dict[int, list[str]], force: bool = False,
                   quick: bool = False) -> dict[int, str] | None:
    """
    speaker_texts: {speaker_id: [utterances]}
    force=True skips the minimum-words gate (used once, at the end of a session).
    quick=True is the instant no-model guess (clinicians ask more questions).
    Returns {speaker_id: "Doctor"/"Patient"/"Other"} or None if not enough data.
    """
    speakers = {s: t for s, t in speaker_texts.items() if _word_count(t) > 0}
    if len(speakers) < 2:
        return None

    ranked = sorted(speakers, key=lambda s: _word_count(speakers[s]), reverse=True)
    s1, s2 = ranked[0], ranked[1]
    low = min(_word_count(speakers[s1]), _word_count(speakers[s2]))
    if not (force or quick) and low < MIN_WORDS:
        return None

    q1, q2 = _question_ratio(speakers[s1]), _question_ratio(speakers[s2])

    if quick:
        if low < QUICK_MIN_WORDS or q1 == q2:
            return None
        doctor, patient = (s1, s2) if q1 > q2 else (s2, s1)
        return _roles(speaker_texts, doctor, patient)

    try:
        d1, d2 = _doctor_score(speakers[s1]), _doctor_score(speakers[s2])
    except Exception:
        log.exception("Role model failed; using question heuristic")
        d1 = d2 = None

    if d1 is not None and d2 is not None and abs(d1 - d2) >= MARGIN:
        doctor = s1 if d1 > d2 else s2
        log.info("Role scores P(doctor): speaker %s=%.2f, speaker %s=%.2f", s1, d1, s2, d2)
    else:
        doctor = s1 if q1 >= q2 else s2
        log.info("Model scores inconclusive (%s, %s); used question heuristic", d1, d2)

    patient = s2 if doctor == s1 else s1
    roles = _roles(speaker_texts, doctor, patient)
    log.info("Roles: %s", roles)
    return roles