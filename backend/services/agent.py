"""ONE model call: the model answers with all its tool calls at once, then Python runs them."""
import json
import os
from types import SimpleNamespace
from fastapi import HTTPException

from core.handlers import FUNCTIONS, Case, generate_soap_note
from core.logger import get_logger
from core.prompt import INSTRUCTIONS
from core.tools import TOOLS
from config.llm import MODEL, client
from services.soap_builder import build_soap

log = get_logger(__name__)

# each extract tool, and the key where its accepted items are stored in case.results
EXTRACT_KEYS = {"extract_diagnoses": "diagnoses", "extract_medications": "medications",
                "extract_follow_up": "follow_up", "extract_history": "history",
                "extract_findings": "findings" , "extract_tasks": "tasks", "extract_recalls": "recalls", "extract_referrals": "referrals",}
API_STYLE = os.getenv("LLM_API", "responses").lower()

def classify_diagnosis_term(name, status, explicit_term=None):
    if explicit_term in ("short_term", "long_term"):
        return explicit_term
    if status == "history":
        return "long_term"
    return "short_term"


def to_final_state(results):
    """Sort the accepted items into the groups the web page displays."""
    state = {"confirmed_diagnoses": [], "not_confirmed_diagnoses": [], "active_medications": [],
             "stopped_medications": [], "considered_only_medications": []}
    for d in results.get("diagnoses", []):
        term = classify_diagnosis_term(d.get("name"), d.get("status"), d.get("term"))
        dx_type = d.get("dx_type") or d.get("type") or d.get("category") or ""
        row = {
            "diagnosis": d.get("name", "?"),
            "status": d.get("status", "?"),
            "evidence": d.get("evidence", ""),
            "term": term,
            "dx_type": dx_type,
            "note": d.get("note", ""),
            "speaker": d.get("speaker", "unclear")
        }
        group = "confirmed_diagnoses" if d.get("status") == "confirmed" else "not_confirmed_diagnoses"
        state[group].append(row)
    for m in results.get("medications", []):
        row = {**m, "new": m.get("status") in ("prescribed", "dose_changed")}
        group = {"stopped": "stopped_medications",
                 "not_prescribed": "considered_only_medications"}.get(m.get("status"), "active_medications")
        state[group].append(row)
    return state


def compile_fallback_soap(case):
    """If the model skipped generate_soap_note, build the note from the accepted items (no model call)."""
    r = case.results
    diagnoses = r.get("diagnoses", [])
    confirmed = [d.get("name") for d in diagnoses if d.get("status") == "confirmed"]
    suspected = [d.get("name") for d in diagnoses if d.get("status") == "suspected"]
    complaint = next((h.get("detail") for h in r.get("history", [])
                      if h.get("category") == "chief_complaint" and h.get("detail")), "")
    parts = ["Clinical consultation" + (f" for: {complaint}." if complaint else ".")]
    if confirmed:
        parts.append("Confirmed: " + ", ".join(confirmed) + ".")
    if suspected:
        parts.append("Suspected: " + ", ".join(suspected) + ".")
    if r.get("medications"):
        parts.append(f"{len(r['medications'])} medicine(s) recorded.")
    # The four sections come from build_soap; generate_soap_note stores them and adds the validation checks.
    generate_soap_note(case, summary=" ".join(parts), **build_soap(r))


def _chat_tools(tools):
    """Re-wrap flat Responses-style tool definitions as Chat Completions tools."""
    out = []
    for t in tools:
        if "function" in t:
            out.append(t)
        else:
            out.append({"type": "function", "function": {k: v for k, v in t.items() if k != "type"}})
    return out


def call_model(transcript):
    """One model call. Returns (calls, usage_info, reply_text); calls have .name and .arguments (JSON string)."""
    if API_STYLE == "chat":
        stream = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": INSTRUCTIONS},
                      {"role": "user", "content": f"Transcript:\n{transcript}"}],
            tools=_chat_tools(TOOLS), tool_choice="auto", parallel_tool_calls=True,
            stream=True, stream_options={"include_usage": True},
            extra_body={"chat_template_kwargs": {"enable_thinking": False}})
        parts, text = {}, ""
        usage = {"model": MODEL, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        for chunk in stream:
            u = getattr(chunk, "usage", None)
            if u:
                usage.update(input_tokens=u.prompt_tokens or 0, output_tokens=u.completion_tokens or 0,
                             total_tokens=u.total_tokens or 0)
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                text += delta.content
            for tc in (delta.tool_calls or []):
                p = parts.setdefault(tc.index, {"name": "", "arguments": ""})
                if tc.function and tc.function.name:
                    p["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    p["arguments"] += tc.function.arguments
        calls = [SimpleNamespace(name=p["name"], arguments=p["arguments"]) for _, p in sorted(parts.items())]
        return calls, usage, text

def run_agent(text):
    """Analyze a text transcript. Audio is transcribed earlier, in its own step (/api/transcribe)."""
    case = Case(text=text)
    if not case.turns:
        log.warning("Empty or unparseable transcript submitted")
        raise HTTPException(400, "Nothing to analyze.")

    # True when no line has a Doctor:/Patient: label, so speakers can't be verified by code.
    unlabeled = all(speaker == "Unknown" for speaker, _ in case.turns)
    if unlabeled:
        log.debug("Transcript has no speaker labels — model will infer speakers")

    # The only model call: it may send many tool calls at once, or none.
    log.info("Calling model '%s' — %d turns in transcript", MODEL, len(case.turns))
    try:
        calls, usage_info, reply_text = call_model(case.numbered_transcript())
    except Exception as e:
        log.error("Model API call failed: %s", e, exc_info=True)
        raise HTTPException(502, f"Model API error: {e}")
    log.info("Model produced %d tool call(s)", len(calls))
    if not calls:
        msg = reply_text or "No clinical information was found."
        log.warning("Model returned no tool calls: %s", msg)
        raise HTTPException(422, msg)

    # A tool the model skipped counts as "nothing found", and we tell the user.
    warnings = []
    if unlabeled:
        warnings.append("This transcript had no speaker labels. Speakers were inferred by the model "
                        "and could not be verified, so check diagnoses, medications and follow-up carefully.")
    called = {call.name for call in calls}
    for tool, key in EXTRACT_KEYS.items():
        if tool not in called:
            case.results[key] = []
            log.debug("Nothing to record for '%s'", tool)
    if "generate_soap_note" not in called:
        log.warning("Model did not call generate_soap_note — will compile fallback SOAP note")

    # Run the tools. The note goes last, so it is checked against what was actually accepted.
    trace = []
    for call in sorted(calls, key=lambda c: c.name == "generate_soap_note"):
        function = FUNCTIONS.get(call.name)
        try:
            args = json.loads(call.arguments or "{}")
            result = function(case, **args) if function else {"error": f"unknown tool {call.name}"}
            accepted = sum(len(v) for k, v in result.items() if isinstance(v, list) and k != "rejected")
            log.debug("Tool '%s' executed — accepted=%d rejected=%d",
                call.name, accepted, len(result.get("rejected", [])))
        except Exception as e:                     # bad arguments from the model: report, don't crash
            log.error("Tool '%s' raised %s: %s", call.name, type(e).__name__, e, exc_info=True)
            args, result = {}, {"error": f"{type(e).__name__}: {e}"}
        trace.append({"tool": call.name, "args": args, "result": result})
        warnings += result.get("rejected", [])     # items that failed the evidence check

    # If the model omitted generate_soap_note, compile a complete SOAP note from extracted items
    if case.soap is None:
        log.info("Compiling fallback SOAP note from extracted clinical findings")
        compile_fallback_soap(case)
        warnings.append("The SOAP note was compiled automatically from extracted clinical findings.")

    if not any(case.results.get(key) for key in EXTRACT_KEYS.values()):   # code check, independent of the model
        log.error("All tool calls returned empty results — no clinical data extracted")
        raise HTTPException(422, "No clinical information was found in this text.")
    if case.soap:
        case.soap["validation_warnings"] += warnings

    log.info("Analysis complete — dx=%d meds=%d warnings=%d trace_steps=%d",
             len(case.results.get("diagnoses", [])),
             len(case.results.get("medications", [])),
             len(warnings),
             len(trace))
    return {"transcript": "\n".join(f"{s}: {t}" if s != "Unknown" else t for s, t in case.turns),
            "turns": [{"n": i, "speaker": s, "text": t} for i, (s, t) in enumerate(case.turns, 1)],
            "final_state": to_final_state(case.results), "extractions": case.results,
            "soap": case.soap, "trace": trace, "complete": case.soap is not None,
            "usage": usage_info,
            "warnings": warnings, "corrections": list(dict.fromkeys(case.corrections))}