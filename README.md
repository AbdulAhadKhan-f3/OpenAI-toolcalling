# Clinical Conversation Analyzer

## Run
```bash
cd backend
pip install -r requirements.txt
# NeMo model auto-downloads from HuggingFace on first run (~2.5 GB, one time only)
python -m uvicorn main:app --reload

# In another terminal:
cd frontend
npm install
npm run dev
```

The frontend is served by Vite; its `/api` requests are proxied to FastAPI on port 8000.

## Architecture

### ASR — Nemotron 3.5 Streaming 0.6B (`nvidia/nemotron-3.5-asr-streaming-0.6b`)
- **Model**: Cache-Aware FastConformer-RNNT, 600M params, multilingual
- **Streaming** (`live_session.py`): 160 ms audio chunks → Nemotron → partial text
  returned per chunk; no VAD boundary-waiting; Kaggle diarizer adds speaker labels
- **Batch** (`transcribe.py`): uploaded file → same model → full transcript
- **Single model instance** shared by both paths — loaded once on first use

### Data Flow
```
Mic → WebSocket → 160 ms PCM chunks → Nemotron streaming cache
                                     → partial text per chunk
                                     → Kaggle diarizer (every 5 s) → speaker labels
                                     → role classifier → Doctor / Patient
File upload → /api/transcribe → librosa → Nemotron batch → transcript
```

### Backend modules
| File | Role |
|------|------|
| `main.py` | FastAPI routes |
| `services/nemotron_asr.py` | Nemotron 3.5 model wrapper (streaming + batch) |
| `services/live_session.py` | WebSocket session: chunk feed → ASR → diarizer |
| `services/transcribe.py` | Batch file transcription |
| `services/diarizer_client.py` | Kaggle diarization REST client (unchanged) |
| `services/role_classifier.py` | Doctor/Patient role classification via Ollama |
| `routes_live.py` | WebSocket route `/ws/transcribe` |

### Dead files (safe to delete)
- `services/fast_asr.py` — replaced by `nemotron_asr.py`
- `services/download_nemotron.py` — no longer needed (NeMo auto-downloads)

## Known limits
- The NeMo streaming API (`transcribe_streaming`) requires NeMo ≥ 2.1. If your
  installed version is older, `live_session.py` falls back to batch-per-chunk
  automatically.
- Diarization still requires the Kaggle service. Update `diarizer_url.txt` or
  set `DIARIZER_URL` env var with your running Kaggle URL.
