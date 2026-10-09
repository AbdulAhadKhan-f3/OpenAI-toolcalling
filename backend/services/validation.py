"""Plain Python rules that check what the LLM extracted. The LLM proposes, these functions decide."""
import difflib
import re

from services.drugfix import KNOWN_DRUGS


def parse_turns(text):
    """Turn 'Doctor: ...' / 'Patient: ...' lines into [(speaker, sentence), ...]."""
    turns = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(doctor|dr|physician|patient|pt|d|p)\s*[:\-]\s*(.*)$", line, re.I)
        if m:
            speaker = "Patient" if m.group(1).lower() in ("patient", "pt", "p") else "Doctor"
            turns.append([speaker, m.group(2)])
        elif turns and turns[-1][0] != "Unknown":
            turns[-1][1] += " " + line               # continuation of a labeled turn
        else:
            turns.append(["Unknown", line])          # no label: the line is its own turn
    return [tuple(t) for t in turns]


def norm(text):
    """Lowercase, no punctuation, single spaces, so quotes compare fairly."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text.lower())).strip()


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def find_evidence(evidence, turns):
    """Return (turn_number, speaker) if the quote appears word for word in a turn, else None."""
    for number, (speaker, text) in enumerate(turns, 1):
        if evidence and norm(evidence) in norm(text):
            return number, speaker
    return None


def closest_sentence(evidence, turns):
    """The transcript sentence most similar to a bad quote (used in the fix-it message)."""
    candidates = [s for _, text in turns for s in sentences(text)]
    return max(candidates, key=lambda s: difflib.SequenceMatcher(None, norm(evidence), norm(s)).ratio())


def best_sentence_with(name, evidence, turns):
    """Among the sentences that mention `name`, the one most like the model's quote (None if no sentence does)."""
    candidates = [s for _, text in turns for s in sentences(text) if norm(name) in norm(s)]
    if not candidates:
        return None
    return max(candidates, key=lambda s: difflib.SequenceMatcher(None, norm(evidence), norm(s)).ratio())


# Statuses that only the doctor can decide. A patient's words cannot create them.
DOCTOR_ONLY = {"confirmed", "suspected", "ruled_out",
               "prescribed", "dose_changed", "continued", "stopped", "not_prescribed"}
SPEAKER_CLAIMS = {"doctor", "patient", "unclear"}


def check_item(item, turns, always_doctor=False):
    """Return None if the item is trustworthy, else a message telling the LLM what to fix."""
    name = item.get("name") or item.get("detail", "item")
    evidence = item.get("evidence", "")
    claimed_speaker = str(item.get("speaker", "")).lower()
    if claimed_speaker not in SPEAKER_CLAIMS:
        return f"{name}: speaker is required and must be doctor, patient, or unclear."
    found = find_evidence(evidence, turns)
    if not found:
        better = best_sentence_with(item["name"], evidence, turns) if item.get("name") else None
        if better:
            item["evidence"] = better               # the item IS in the transcript: use the real sentence
            found = find_evidence(better, turns)
        else:
            return f"{name}: evidence not found in the transcript. Closest sentence: {closest_sentence(evidence, turns)!r}"
    number, speaker = found
    if speaker == "Unknown":                         # the text has no label here: use who the model says spoke
        speaker = {"doctor": "Doctor", "patient": "Patient"}.get(claimed_speaker, "Unclear")
    if (always_doctor or item.get("status") in DOCTOR_ONLY) and speaker != "Doctor":
        who = "the patient" if speaker == "Patient" else "a speaker who is unclear"
        return f"{name}: this can only come from the doctor, but the quote is from {who}."
    item["turn"], item["speaker"] = number, speaker.lower()
    return None


# Things a plan might claim, and the words that would prove someone said it.
PLAN_CLAIMS = {
    "follow-up":       (r"follow.?up|return in|come back", r"follow.?up|come back|return|see you|recheck|review you"),
    "a referral":      (r"referr|refer\b",                 r"refer"),
    "extra tests":     (r"\b(tests?|labs?|blood work|imaging|scan)\b",
                        r"\b(tests?|labs?|blood work|imaging|scan|x.?ray|ecg|endoscopy)\b"),
    "diet advice":     (r"\bdiet\b|nutrition",             r"\bdiet\b|\beat\b|nutrition|food"),
    "exercise advice": (r"exercise|physical activity",     r"exercise|activity|walk"),
    "warning signs":   (r"warning signs|emergency|urgent care", r"emergency|urgent|warning|go to the"),
}


def plan_warnings(plan, turns):
    """Warn about plan items nobody mentioned in the conversation."""
    said = " ".join(text for _, text in turns).lower()
    return [f"Plan mentions {label}, but nobody said it in the conversation."
            for label, (in_plan, in_talk) in PLAN_CLAIMS.items()
            if re.search(in_plan, plan.lower()) and not re.search(in_talk, said)]


RULE_OUT = r"rule[sd]? (that |this |it )?out|no sign of|not consistent with"


def missing_hints(turns, medications, diagnoses):
    """Things the transcript mentions that the model never recorded."""
    hints = []
    recorded = " ".join(m.get("name", "") for m in medications).lower()
    for drug in KNOWN_DRUGS:
        if drug in recorded:
            continue
        for number, (_, text) in enumerate(turns, 1):
            hit = next((s for s in sentences(text) if drug in s.lower()), None)
            if hit:
                hints.append(f"'{drug}' is mentioned in turn {number} but was not recorded with extract_medications. Sentence: {hit!r}")
                break
    if not any(d.get("status") == "ruled_out" for d in diagnoses):
        for number, (speaker, text) in enumerate(turns, 1):
            for s in sentences(text):
                if speaker != "Patient" and re.search(RULE_OUT, s, re.I):
                    hints.append(f"Turn {number}: {s!r} If this rules out a condition, record it with extract_diagnoses (status ruled_out).")
    return hints[:8]