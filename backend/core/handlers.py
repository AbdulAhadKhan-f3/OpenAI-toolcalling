"""Python implementations behind the model-facing tools."""

from checks import check_item, missing_hints, parse_turns, plan_warnings
from drugfix import correct_drug_names

DIAGNOSIS_STATUSES = {"confirmed", "suspected", "ruled_out", "history"}
MEDICATION_STATUSES = {"prescribed", "dose_changed", "continued", "stopped", "not_prescribed", "patient_reported"}
ALLOWED_STATUSES = {"diagnoses": DIAGNOSIS_STATUSES, "medications": MEDICATION_STATUSES}


class Case:
    """State and extracted data for one consultation."""

    def __init__(self, text=None):
        self.turns, self.corrections = [], []
        self.results = {}
        self.soap = None
        if text:
            self.set_transcript(text)

    def set_transcript(self, text):
        text, self.corrections = correct_drug_names(text)
        self.turns = parse_turns(text)

    def numbered_transcript(self):
        return "\n".join(
            f"[{number}] {speaker}: {text}" if speaker != "Unknown" else f"[{number}] {text}"
            for number, (speaker, text) in enumerate(self.turns, 1)
        )


def _item_identity(key, item):
    if key in ("diagnoses", "medications"):
        return (key, item.get("name", "").strip().lower())
    if key == "follow_up":
        return (key, item.get("type", ""), item.get("detail", "").strip().lower())
    return (key, item.get("category", ""), item.get("detail", "").strip().lower())


def extract(case, key, items, always_doctor=False):
    """Validate model-supplied items and retain accepted items across correction calls."""
    if not case.turns:
        return {"error": "There is no transcript."}
    if not isinstance(items, list):
        return {"error": f"{key} must be a list."}

    accepted, rejected = [], []
    for item in items:
        if not isinstance(item, dict):
            rejected.append(f"Invalid {key} item: expected an object.")
            continue
        allowed = ALLOWED_STATUSES.get(key)
        if allowed and item.get("status") not in allowed:
            rejected.append(
                f"{item.get('name', key)}: status is required and must be one of "
                f"{sorted(allowed)}. Choose based on the transcript; do not guess."
            )
            continue
        problem = check_item(item, case.turns, always_doctor)
        if problem:
            rejected.append(problem)
        else:
            accepted.append(item)

    merged = {_item_identity(key, item): item for item in case.results.get(key, [])}
    merged.update({_item_identity(key, item): item for item in accepted})   # newer replaces older
    case.results[key] = list(merged.values())
    return {key: accepted, "rejected": rejected}


def extract_diagnoses(case, diagnoses=None, **_):
    return extract(case, "diagnoses", diagnoses or [])


def extract_medications(case, medications=None, **_):
    return extract(case, "medications", medications or [])


def extract_follow_up(case, follow_up=None, **_):
    return extract(case, "follow_up", follow_up or [], always_doctor=True)


def extract_history(case, history=None, **_):
    return extract(case, "history", history or [])


def extract_findings(case, findings=None, **_):
    return extract(case, "findings", findings or [])


def generate_soap_note(case, subjective="", objective="", assessment="", plan="", summary="", **_):
    """Save the note. Problems are shown as warnings to the reviewer, not hidden."""
    case.soap = {
        "subjective": subjective or "Not stated.", "objective": objective or "Not stated.",
        "assessment": assessment or "Not stated.", "plan": plan or "Not stated.",
        "summary": summary or "Not stated.",
        "validation_warnings": plan_warnings(str(plan), case.turns)
        + missing_hints(case.turns, case.results.get("medications", []), case.results.get("diagnoses", [])),
    }
    return {"ok": True}


FUNCTIONS = {
    "extract_diagnoses": extract_diagnoses,
    "extract_medications": extract_medications,
    "extract_follow_up": extract_follow_up,
    "extract_history": extract_history,
    "extract_findings": extract_findings,
    "generate_soap_note": generate_soap_note,
}