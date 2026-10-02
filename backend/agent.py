"""ONE model call: the model answers with all its tool calls at once, then Python runs them."""
import json

from fastapi import HTTPException

from core.handlers import FUNCTIONS, Case
from core.prompt import INSTRUCTIONS
from core.tools import TOOLS
from llm import MODEL, client

# each extract tool, and the key where its accepted items are stored in case.results
EXTRACT_KEYS = {"extract_diagnoses": "diagnoses", "extract_medications": "medications",
                "extract_follow_up": "follow_up", "extract_history": "history",
                "extract_findings": "findings"}


def to_final_state(results):
    """Sort the accepted items into the groups the web page displays."""
    state = {"confirmed_diagnoses": [], "not_confirmed_diagnoses": [], "active_medications": [],
             "stopped_medications": [], "considered_only_medications": []}
    for d in results.get("diagnoses", []):
        row = {"diagnosis": d.get("name", "?"), "status": d.get("status", "?"), "evidence": d["evidence"]}
        group = "confirmed_diagnoses" if d.get("status") == "confirmed" else "not_confirmed_diagnoses"
        state[group].append(row)
    for m in results.get("medications", []):
        row = {**m, "new": m.get("status") in ("prescribed", "dose_changed")}
        group = {"stopped": "stopped_medications",
                 "not_prescribed": "considered_only_medications"}.get(m.get("status"), "active_medications")
        state[group].append(row)
    return state


def run_agent(text):
    """Analyze a text transcript. Audio is transcribed earlier, in its own step (/api/transcribe)."""
    case = Case(text=text)
    if not case.turns:
        raise HTTPException(400, "Nothing to analyze.")

    # True when no line has a Doctor:/Patient: label, so speakers can't be verified by code.
    unlabeled = all(speaker == "Unknown" for speaker, _ in case.turns)

    # The only model call: it may send many tool calls at once, or none if the text is not clinical.
    try:
        response = client.responses.create(
            model=MODEL, instructions=INSTRUCTIONS, tools=TOOLS,
            input=f"Transcript:\n{case.numbered_transcript()}",
            tool_choice="auto", parallel_tool_calls=True)      # "auto": the model may decide there is nothing to record
    except Exception as e:
        raise HTTPException(502, f"Model API error: {e}")
    calls = [item for item in response.output if item.type == "function_call"]
    if not calls:                               # the model chose not to record anything
        raise HTTPException(422, getattr(response, "output_text", "") or
                            "No clinical information was found. The text may not be a medical conversation.")

    # A tool the model skipped counts as "nothing found", and we tell the user.
    warnings = []
    if unlabeled:
        warnings.append("This transcript had no speaker labels. Speakers were inferred by the model "
                        "and could not be verified, so check diagnoses, medications and follow-up carefully.")
    called = {call.name for call in calls}
    for tool, key in EXTRACT_KEYS.items():
        if tool not in called:
            case.results[key] = []
            warnings.append(f"The model did not call {tool}, so nothing was recorded for it.")
    if "generate_soap_note" not in called:
        warnings.append("The model did not write a SOAP note.")

    # Run the tools. The note goes last, so it is checked against what was actually accepted.
    trace = []
    for call in sorted(calls, key=lambda c: c.name == "generate_soap_note"):
        function = FUNCTIONS.get(call.name)
        try:
            args = json.loads(call.arguments or "{}")
            result = function(case, **args) if function else {"error": f"unknown tool {call.name}"}
        except Exception as e:                     # bad arguments from the model: report, don't crash
            args, result = {}, {"error": f"{type(e).__name__}: {e}"}
        trace.append({"tool": call.name, "args": args, "result": result})
        warnings += result.get("rejected", [])     # items that failed the evidence check
    if not any(case.results.get(key) for key in EXTRACT_KEYS.values()):   # code check, independent of the model
        raise HTTPException(422, "No clinical information was found in this text.")
    if case.soap:
        case.soap["validation_warnings"] += warnings

    return {"transcript": "\n".join(f"{s}: {t}" if s != "Unknown" else t for s, t in case.turns),
            "turns": [{"n": i, "speaker": s, "text": t} for i, (s, t) in enumerate(case.turns, 1)],
            "final_state": to_final_state(case.results), "extractions": case.results,
            "soap": case.soap, "trace": trace, "complete": case.soap is not None,
            "warnings": warnings, "corrections": list(dict.fromkeys(case.corrections))}