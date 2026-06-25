import os
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.agent import chat_with_agent
from backend.utils import get_chunk_data

logger = logging.getLogger(__name__)

app = FastAPI(title="Sovereignty Agent API")


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    logger.info(f"Received chat request for session '{request.session_id}'")
    try:
        response_text = chat_with_agent(request.message, request.session_id)
        logger.info(f"Successfully generated response for session '{request.session_id}'")
        return {"reply": response_text}
    except Exception as e:
        logger.error(f"Error during chat generation: {e}", exc_info=True)
        return {"reply": "Ein interner Fehler ist aufgetreten. Bitte siehe in den Docker Logs nach."}


@app.get("/api/chunk/{chunk_id}")
async def get_chunk(chunk_id: str):
    logger.info(f"Received chunk request for '{chunk_id}'")
    try:
        data = get_chunk_data(chunk_id)
        if not data:
            return {"error": "Chunk nicht gefunden."}
        return data
    except Exception as e:
        logger.error(f"Error retrieving chunk {chunk_id}: {e}", exc_info=True)
        return {"error": "Ein Fehler ist aufgetreten."}


# Serve HTML frontend
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/static", StaticFiles(directory=frontend_path), name="static")


@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(frontend_path, "index.html"))
