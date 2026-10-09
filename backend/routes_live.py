"""Live consultation WebSocket. Replaces the old /ws/transcribe handler in main.py."""
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.logger import get_logger
from services.live_session import LiveSession

router = APIRouter()
log = get_logger(__name__)


@router.websocket("/ws/transcribe")
async def live_transcribe(websocket: WebSocket):
    """
    Browser sends 16 kHz mono PCM16 as binary frames, then the text 'stop'.
    Server sends:
      - ready
      - line (new or updated, by index)
      - final
      - error
    """
    await websocket.accept()
    session = None
    try:
        # Create session in a thread (loads models)
        session = await asyncio.to_thread(LiveSession)
        log.info("session created for live transcription")
        await websocket.send_json({"type": "ready"})

        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                break

            # Incoming audio chunk
            if message.get("bytes"):
                updates = await asyncio.to_thread(session.feed, message["bytes"])
                for update in updates:
                    await websocket.send_json(update)

            # User clicked Stop
            elif message.get("text") == "stop":
                updates = await asyncio.to_thread(session.finish)
                for update in updates:
                    await websocket.send_json(update)

                # Send the final complete result
                await websocket.send_json({
                    "type": "final",
                    **session.result()
                })
                # Brief pause so the client can receive the final message
                # before we close the connection.
                await asyncio.sleep(0.3)
                break

    except WebSocketDisconnect:
        log.info("Live transcription client disconnected")
    except Exception as exc:
        log.exception("Live transcription failed")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(exc)[:300]
            })
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass