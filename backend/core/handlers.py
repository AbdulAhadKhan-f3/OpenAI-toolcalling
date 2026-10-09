"""Python implementations behind the model-facing tools."""
from services.soap_builder import build_soap
from services.drugfix import correct_drug_names
from services.validation import check_item, missing_hints, parse_turns

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


def _low(item, field):
    return str(item.get(field, "")).strip().lower()


def _item_identity(key, item):
    """Two items with the same identity are the same thing; the newer one replaces the older one."""
    if key in ("diagnoses", "medications"):
        return (key, _low(item, "name"))
    if key == "follow_up":
        return (key, item.get("type", ""), _low(item, "detail"))
    if key in ("tasks", "recalls"):
        return (key, _low(item, "detail"), _low(item, "due"))
    if key == "referrals":
        return (key, _low(item, "refer_to"), _low(item, "detail"))
    return (key, item.get("category", ""), _low(item, "detail"))


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


# What the doctor arranges for later: only the doctor's words count.
def extract_referrals(case, referrals=None, **_):
    return extract(case, "referrals", referrals or [], always_doctor=True)


def extract_recalls(case, recalls=None, **_):
    return extract(case, "recalls", recalls or [], always_doctor=True)


def extract_tasks(case, tasks=None, **_):
    return extract(case, "tasks", tasks or [], always_doctor=True)


def generate_soap_note(case, summary="", **_):
    """The four sections are built in Python from accepted items; only the summary is the model's text."""
    sections = build_soap(case.results)
    case.soap = {**sections, "summary": summary or "Not stated.",
                 "validation_warnings": missing_hints(case.turns, case.results.get("medications", []),
                                                      case.results.get("diagnoses", []))}
    return {"ok": True}


FUNCTIONS = {
    "extract_diagnoses": extract_diagnoses,
    "extract_medications": extract_medications,
    "extract_follow_up": extract_follow_up,
    "extract_history": extract_history,
    "extract_findings": extract_findings,
    "extract_referrals": extract_referrals,
    "extract_recalls": extract_recalls,
    "extract_tasks": extract_tasks,
    "generate_soap_note": generate_soap_note,
}
