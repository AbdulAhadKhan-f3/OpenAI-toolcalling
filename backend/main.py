"""API routes only. The agent logic lives in agent.py, storage in db.py."""
import asyncio

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

import db
from agent import run_agent
from transcribe import ALLOWED, transcribe_audio

app = FastAPI(title="Clinical AI")
db.init()


@app.post("/api/encounters")
async def create_encounter(file: UploadFile | None = File(None), text: str = Form("")):
    """Analyze a TEXT transcript. Audio is transcribed first, through /api/transcribe."""
    title = "Pasted transcript"
    if file is not None and file.filename:
        if not file.filename.lower().endswith(".txt"):
            raise HTTPException(400, "Only text reaches this endpoint. Transcribe audio with /api/transcribe first.")
        text = (await file.read()).decode("utf-8", errors="ignore")
        title = file.filename
    if not text.strip():
        raise HTTPException(400, "Upload a transcript or paste text.")
    result = await asyncio.to_thread(run_agent, text.strip())
    eid = db.save(title, result["transcript"], result)
    return {"id": eid, **result}


@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """Audio in, editable labeled transcript out (the review-before-analysis flow)."""
    if not (file.filename or "").lower().endswith(ALLOWED):
        raise HTTPException(400, f"Unsupported audio type. Use one of: {', '.join(ALLOWED)}")
    return await asyncio.to_thread(transcribe_audio, await file.read())


@app.get("/api/encounters")
def list_encounters(q: str = ""):
    return db.list_encounters(q.strip())


@app.get("/api/encounters/{eid}")
def get_encounter(eid: int):
    enc = db.get(eid)
    if not enc:
        raise HTTPException(404, "Encounter not found.")
    return enc