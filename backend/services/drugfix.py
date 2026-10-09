"""Fix speech-recognition misspellings of drug names BEFORE the agent sees the transcript,
so the model's quotes still match the transcript word for word."""
import difflib
import re

KNOWN_DRUGS = [
    "lisinopril", "amlodipine", "metformin", "atorvastatin", "ibuprofen", "naproxen", "celecoxib",
    "paracetamol", "acetaminophen", "aspirin", "omeprazole", "pantoprazole", "levothyroxine",
    "amoxicillin", "azithromycin", "clarithromycin", "metronidazole", "cefepime", "vancomycin",
    "rivaroxaban", "warfarin", "clopidogrel", "losartan", "insulin", "prednisolone", "cetirizine",
]


def _closest(cand: str, cutoff: float):
    c = cand.lower()
    if c in KNOWN_DRUGS:
        return None
    m = difflib.get_close_matches(c, KNOWN_DRUGS, n=1, cutoff=cutoff)
    return m[0] if m else None


def correct_drug_names(text: str):
    """Returns (corrected_text, [(heard, corrected), ...])."""
    words = list(re.finditer(r"[A-Za-z]+", text))
    out, corrections, pos, i = [], [], 0, 0
    while i < len(words):
        w = words[i]
        out.append(text[pos:w.start()])
        fixed, last = None, w
        if i + 1 < len(words):                        # ASR often splits a drug name: "am lodopine"
            nxt = words[i + 1]
            joined = w.group() + nxt.group()
            first = w.group().lower()
            # only glue fragments: skip if the first word is already a drug (or a misspelled one),
            # otherwise "lisinopril ten" would be "corrected" and the dose word deleted
            if (text[w.end():nxt.start()] == " " and len(joined) >= 8 and len(first) <= 7
                    and first not in KNOWN_DRUGS and not _closest(first, 0.75)
                    and nxt.group().lower() not in KNOWN_DRUGS):
                fixed = _closest(joined, 0.85)
                if fixed:
                    last = nxt
        if not fixed and len(w.group()) >= 7:
            fixed = _closest(w.group(), 0.75)
        if fixed:
            heard = text[w.start():last.end()]
            corrections.append((heard, fixed))
            out.append(fixed.capitalize() if heard[0].isupper() else fixed)
        else:
            out.append(text[w.start():last.end()])
        pos, i = last.end(), words.index(last) + 1
    out.append(text[pos:])
    return "".join(out), corrections