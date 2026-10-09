"""Builds the SOAP sections from the accepted, validated items. No model call and no invented text."""

EMPTY = {"", "not stated", "not specified", "unspecified", "unknown", "n/a", "na", "null", "none",
         "not applicable", "not prescribed"}

DX_GROUPS = [("Confirmed", "confirmed"), ("Suspected", "suspected"), ("Ruled out", "ruled_out"), ("Past or chronic", "history")]
MED_GROUPS = [("Started", "prescribed"), ("Dose changed", "dose_changed"), ("Continued", "continued"),
              ("Stopped", "stopped"), ("Not prescribed", "not_prescribed"),
              ("Reported by the patient, not addressed by the doctor", "patient_reported")]
CARE_GROUPS = [("Recall", "recalls"), ("Referral", "referrals"), ("Tasks", "tasks")]
FOLLOW_UP_GROUPS = [("Tests ordered", "test_ordered"), ("Warning signs", "warning_sign"), ("Advice", "advice")]
HISTORY_GROUPS = [("Chief complaint", "chief_complaint"), ("Symptoms", "symptom"), ("Allergies", "allergy"),
                  ("Past history", "past_history"), ("Family history", "family_history"), ("Social history", "social_history")]
FINDING_GROUPS = [("Vital signs", "vital_sign"), ("Examination", "exam"), ("Test results", "test_result")]


def _v(value):
    """The value as text, or '' when it is empty or a placeholder such as 'not stated'."""
    text = str(value or "").strip()
    return "" if text.lower() in EMPTY else text


def _with(detail, extra):
    """'detail (extra)', without repeating text that is already in the detail."""
    detail, extra = _v(detail), _v(extra)
    if not detail or not extra or extra.lower() in detail.lower():
        return detail
    return f"{detail} ({extra})"


def _lines(groups, items_for):
    """One 'Title: a; b; c' line for each group that has items."""
    out = []
    for title, key in groups:
        items = [i for i in items_for(key) if i]
        if items:
            out.append(f"{title}: " + "; ".join(items))
    return out


def _med(m):
    how = ", ".join(p for p in (_v(m.get(k)) for k in ("dose", "route", "frequency", "timing", "duration")) if p)
    extra = [f"{label}: {_v(m.get(k))}" for label, k in
             (("start", "start"), ("end", "end"), ("for", "indication"), ("reason", "reason"), ("note", "instructions"))
             if _v(m.get(k))]
    return _v(m.get("name")) + (f" {how}" if how else "") + (f" ({'; '.join(extra)})" if extra else "")


def _referral(r):
    extra = "; ".join(p for p in (_v(r.get("urgency")), _v(r.get("condition"))) if p)
    return _with(_with(r.get("refer_to"), r.get("detail")), extra)


def _task(t):
    owner = _v(t.get("owner"))
    who = "" if owner == "unclear" else owner.replace("_", " ")
    return _with(t.get("detail"), ", ".join(p for p in (who, _v(t.get("due"))) if p))


CARE_FORMAT = {
    "recalls": lambda r: _with(r.get("detail"), r.get("due")),
    "referrals": _referral,
    "tasks": _task,
}


def build_soap(results):
    history = results.get("history", [])
    findings = results.get("findings", [])
    diagnoses = results.get("diagnoses", [])
    meds = results.get("medications", [])
    follow_up = results.get("follow_up", [])

    subjective = _lines(HISTORY_GROUPS, lambda c: [_with(h.get("detail"), h.get("duration")) for h in history if h.get("category") == c])
    before_visit = [_v(m.get("name")) for m in meds if m.get("status") in ("continued", "patient_reported", "dose_changed", "stopped")]
    if before_visit:
        subjective.append("Medicines taken before the visit: " + ", ".join(before_visit))

    objective = _lines(FINDING_GROUPS, lambda c: [_v(f.get("detail")) for f in findings if f.get("category") == c])
    assessment = _lines(DX_GROUPS, lambda s: [", ".join(_v(d.get("name")) for d in diagnoses if d.get("status") == s)])
    plan = (_lines(MED_GROUPS, lambda s: [_med(m) for m in meds if m.get("status") == s])
            + _lines(CARE_GROUPS, lambda k: [CARE_FORMAT[k](i) for i in results.get(k, [])])
            + _lines(FOLLOW_UP_GROUPS, lambda t: [_with(f.get("detail"), f.get("timing")) for f in follow_up if f.get("type") == t]))

    return {
        "subjective": "\n".join(subjective) or "Not stated.",
        "objective": "\n".join(objective) or "Not stated.",
        "assessment": "\n".join(assessment) or "No diagnosis was stated by the doctor.",
        "plan": "\n".join(plan) or "No plan was stated in the conversation.",
    }
