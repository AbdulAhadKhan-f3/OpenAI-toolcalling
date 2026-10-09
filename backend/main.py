"""API routes only. The agent logic lives in agent.py, storage in db.py and care.py."""
import os
import asyncio
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile

from config.llm import MODEL, client
from database import care, db
from core.logger import get_logger
from services.agent import classify_diagnosis_term, run_agent
from services.transcribe import ALLOWED, transcribe_audio

log = get_logger(__name__)

import asyncio
from contextlib import asynccontextmanager

from services.nemotron_asr import get_model
from services.role_classifier import warm
from services import diarizer_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    async def _preload():
        try:
            if os.getenv("ASR_BACKEND", "nemotron").lower() != "qwen":
                await asyncio.to_thread(get_model)
            await asyncio.to_thread(warm)           # role classifier
            log.info("Models preloaded. Diarizer: %s", diarizer_client.status())
        except Exception:
            log.exception("Model preload failed; will retry on first use")

    task = asyncio.create_task(_preload())          # server starts at once
    yield
    task.cancel()


app = FastAPI(title="Clinical AI", lifespan=lifespan)

from routes_live import router as live_router
app.include_router(live_router)
db.init()
care.init()
log.info("ClinScribe API started — database initialised")


def _kind(kind):
    if kind not in care.FIELDS:
        raise HTTPException(404, "Unknown item type. Use tasks, recalls or referrals.")


def _store_care(eid, pid, title, result):
    """Save the consult (patient link, summary, token cost) and the AI-found tasks, recalls and referrals."""
    fs = result["final_state"]
    confirmed = ", ".join(d["diagnosis"] for d in fs["confirmed_diagnoses"])
    care.save_consult(eid, pid, title, confirmed, (result.get("soap") or {}).get("summary", ""), result.get("usage", {}))
    for kind in care.FIELDS:
        for item in result.get("extractions", {}).get(kind, []):
            care.add_item(kind, {**item, "encounter_id": eid, "patient_id": pid}, source="ai")


# ---------- analysis ----------
@app.post("/api/encounters")
async def create_encounter(file: UploadFile | None = File(None), text: str = Form(""),
                           patient_id: int | None = Form(None), patient_name: str = Form("")):
    """Analyze a TEXT transcript. Audio is transcribed first, through /api/transcribe."""
    title = "Pasted transcript"
    if patient_id is not None and not care.get_patient(patient_id):
        raise HTTPException(404, "Patient not found.")
    if file is not None and file.filename:
        if not file.filename.lower().endswith(".txt"):
            log.warning("Rejected non-txt file upload: %s", file.filename)
            raise HTTPException(400, "Only text reaches this endpoint. Transcribe audio with /api/transcribe first.")
        text = (await file.read()).decode("utf-8", errors="ignore")
        title = file.filename
        log.info("Received transcript file: %s (%d chars)", title, len(text))
    if not text.strip():
        log.warning("Empty transcript submission")
        raise HTTPException(400, "Upload a transcript or paste text.")
    log.info("Starting analysis for: '%s' (%d chars)", title, len(text.strip()))
    try:
        result = await asyncio.to_thread(run_agent, text.strip())
    except HTTPException as exc:
        log.error("Agent returned HTTP %d: %s", exc.status_code, exc.detail)
        raise
    except Exception as exc:
        log.critical("Unexpected error in run_agent", exc_info=True)
        raise HTTPException(500, "Internal server error — check server logs.") from exc
    eid = db.save(title, result["transcript"], result)
    pid = patient_id if patient_id is not None else care.find_or_create_patient(patient_name)
    _store_care(eid, pid, title, result)
    fs = result["final_state"]
    log.info("Encounter #%d saved for patient %s — dx=%d meds=%d tokens=%s", eid, pid,
             len(fs["confirmed_diagnoses"]) + len(fs["not_confirmed_diagnoses"]),
             len(fs["active_medications"]) + len(fs["stopped_medications"]) + len(fs["considered_only_medications"]),
             result.get("usage", {}).get("total_tokens"))
    return {"id": eid, "patient_id": pid, **result, "care": care.encounter_care(eid), "consult": care.get_consult(eid)}


@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """Audio in, editable labeled transcript out (the review-before-analysis flow)."""
    if not (file.filename or "").lower().endswith(ALLOWED):
        log.warning("Rejected unsupported audio type: %s", file.filename)
        raise HTTPException(400, f"Unsupported audio type. Use one of: {', '.join(ALLOWED)}")
    log.info("Transcribing audio file: %s", file.filename)
    try:
        result = await asyncio.to_thread(transcribe_audio, await file.read())
        log.info("Transcription complete for: %s", file.filename)
        return result
    except HTTPException:
        raise                                   # keep deliberate errors such as "No speech was detected"
    except Exception as exc:
        log.error("Transcription failed for %s", file.filename, exc_info=True)
        raise HTTPException(500, "Transcription failed — check server logs.") from exc


# ---------- encounters ----------
@app.get("/api/encounters")
def list_encounters(q: str = ""):
    log.debug("List encounters — query=%r", q)
    return db.list_encounters(q.strip())


@app.get("/api/encounters/{eid}")
def get_encounter(eid: int):
    log.debug("Fetching encounter #%d", eid)
    enc = db.get(eid)
    if not enc:
        log.warning("Encounter #%d not found", eid)
        raise HTTPException(404, "Encounter not found.")
    res = enc.get("result", {})
    if isinstance(res, dict) and "final_state" in res:
        fs = res["final_state"]
        for d in fs.get("confirmed_diagnoses", []) + fs.get("not_confirmed_diagnoses", []):
            if "term" not in d:
                d["term"] = classify_diagnosis_term(d.get("diagnosis"), d.get("status"))
    consult = care.get_consult(eid)
    enc["consult"] = consult                                   # patient link, token cost, summary
    enc["patient"] = care.get_patient(consult["patient_id"]) if consult and consult["patient_id"] else None
    enc["care"] = care.encounter_care(eid)                     # the editable tasks, recalls and referrals
    log.debug("Returning encounter #%d", eid)
    return enc


@app.put("/api/encounters/{eid}/patient")
def set_encounter_patient(eid: int, data: dict = Body(...)):
    """Attach an encounter (for example an old one) to a patient, by patient_id or by name."""
    enc = db.get(eid)
    if not enc:
        raise HTTPException(404, "Encounter not found.")
    pid = data.get("patient_id")
    if pid is None:
        pid = care.find_or_create_patient(data.get("patient_name"))
    elif not care.get_patient(pid):
        raise HTTPException(404, "Patient not found.")
    if pid is None:
        raise HTTPException(400, "Give a patient_id or a patient_name.")
    care.set_encounter_patient(eid, pid, title=enc.get("title", ""), created_at=enc.get("created_at"))
    return care.get_consult(eid)


# ---------- patients and history ----------
@app.get("/api/patients")
def list_patients(q: str = ""):
    return care.list_patients(q.strip())


@app.post("/api/patients")
def create_patient(data: dict = Body(...)):
    pid = care.find_or_create_patient(data.get("name"))
    if pid is None:
        raise HTTPException(400, "Patient name is required.")
    return care.get_patient(pid)


@app.get("/api/patients/{pid}")
def patient_history(pid: int):
    """Everything done with this patient: consults (with token cost), tasks, recalls and referrals."""
    history = care.patient_history(pid)
    if not history:
        raise HTTPException(404, "Patient not found.")
    return history


@app.patch("/api/patients/{pid}")
def update_patient(pid: int, data: dict = Body(...)):
    """Update patient demographic fields (name, date_of_birth, gender, phone, email, notes)."""
    if not care.get_patient(pid):
        raise HTTPException(404, "Patient not found.")
    updated = care.update_patient(pid, data)
    if not updated:
        raise HTTPException(404, "Patient not found.")
    return updated


# ---------- tasks, recalls, referrals (added by the AI or by hand) ----------
@app.post("/api/care/{kind}")
def create_care_item(kind: str, data: dict = Body(...)):
    _kind(kind)
    if not (data.get("detail") or data.get("refer_to")):
        raise HTTPException(400, "Add some text for this item.")
    if data.get("patient_id") is None and data.get("encounter_id") is not None:
        consult = care.get_consult(data["encounter_id"])
        data["patient_id"] = consult["patient_id"] if consult else None
    return care.add_item(kind, data, source="manual")


@app.patch("/api/care/{kind}/{item_id}")
def update_care_item(kind: str, item_id: int, data: dict = Body(...)):
    _kind(kind)
    try:
        item = care.update_item(kind, item_id, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not item:
        raise HTTPException(404, "Item not found.")
    return item


@app.delete("/api/care/{kind}/{item_id}")
def delete_care_item(kind: str, item_id: int):
    _kind(kind)
    if not care.delete_item(kind, item_id):
        raise HTTPException(404, "Item not found.")
    return {"deleted": item_id}

# ---------- diagnoses (editable) ----------
@app.get("/api/encounters/{eid}/diagnoses")
def get_diagnoses(eid: int):
    if not db.get(eid):
        raise HTTPException(404, "Encounter not found.")
    return db.list_diagnoses(eid)


@app.post("/api/encounters/{eid}/diagnoses")
def create_diagnosis(eid: int, data: dict = Body(...)):
    if not db.get(eid):
        raise HTTPException(404, "Encounter not found.")
    try:
        return db.add_diagnosis(eid, data, source="manual")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.patch("/api/encounters/{eid}/diagnoses/{item_id}")
def patch_diagnosis(eid: int, item_id: int, data: dict = Body(...)):
    if not db.get(eid):
        raise HTTPException(404, "Encounter not found.")
    try:
        item = db.update_diagnosis(eid, item_id, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not item:
        raise HTTPException(404, "Diagnosis not found.")
    return item


@app.delete("/api/encounters/{eid}/diagnoses/{item_id}")
def remove_diagnosis(eid: int, item_id: int):
    if not db.get(eid):
        raise HTTPException(404, "Encounter not found.")
    if not db.delete_diagnosis(eid, item_id):
        raise HTTPException(404, "Diagnosis not found.")
    return {"deleted": item_id}


# ---------- medications (editable) ----------
@app.get("/api/encounters/{eid}/medications")
def get_medications(eid: int):
    if not db.get(eid):
        raise HTTPException(404, "Encounter not found.")
    return db.list_medications(eid)


@app.post("/api/encounters/{eid}/medications")
def create_medication(eid: int, data: dict = Body(...)):
    if not db.get(eid):
        raise HTTPException(404, "Encounter not found.")
    try:
        return db.add_medication(eid, data, source="manual")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.patch("/api/encounters/{eid}/medications/{item_id}")
def patch_medication(eid: int, item_id: int, data: dict = Body(...)):
    if not db.get(eid):
        raise HTTPException(404, "Encounter not found.")
    try:
        item = db.update_medication(eid, item_id, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not item:
        raise HTTPException(404, "Medication not found.")
    return item


@app.delete("/api/encounters/{eid}/medications/{item_id}")
def remove_medication(eid: int, item_id: int):
    if not db.get(eid):
        raise HTTPException(404, "Encounter not found.")
    if not db.delete_medication(eid, item_id):
        raise HTTPException(404, "Medication not found.")
    return {"deleted": item_id}