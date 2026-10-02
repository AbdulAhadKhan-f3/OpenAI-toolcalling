# Clinical Conversation Analyzer

## Run
```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload
# In another terminal:
cd frontend
npm install
npm run dev
```

The frontend is served by Vite; its `/api` requests are proxied to FastAPI on port 8000.

## Architecture
- `backend/main.py` exposes the encounter, transcription, and history API routes.
- `backend/agent.py` manages the Responses API tool loop for one consultation.
- `backend/core/tools.py` defines tool schemas and their Python implementations. `Case` holds the transcript, extracted data, corrections, and SOAP note for one request.
- `backend/checks.py` parses speaker turns and validates quoted evidence, speaker permissions, and plan claims.
- `backend/drugfix.py` corrects recognized medication-name transcription errors before extraction.
- `backend/llm.py` configures the OpenAI-compatible client and JSON response helper.
- `backend/transcribe.py` transcribes audio and adds speaker labels. The current `.env` selects local Nemotron; its model downloads on first use.
- `backend/db.py` stores completed encounters and searchable diagnosis/medication records in SQLite.
- `frontend/src/App.jsx` contains the upload, transcript-review, results, and history views; `App.css` styles them.

The normal audio workflow is: upload to `/api/transcribe`, review the labeled transcript in the frontend, then send that transcript to `/api/encounters` for extraction and SOAP generation. The encounter endpoint accepts transcript text only.

The text model is selected with `MODEL` and can use an OpenAI-compatible `OPENAI_BASE_URL`. Audio transcription always uses local Nemotron; there is no cloud transcription fallback.

## Known limits
- Local Nemotron transcription does not diarize speakers; speaker labels are inferred from transcript text and should be reviewed.
- Extraction remains model-assisted. Review medication-name corrections, speaker labels, evidence, and the tool trace before relying on generated documentation.
