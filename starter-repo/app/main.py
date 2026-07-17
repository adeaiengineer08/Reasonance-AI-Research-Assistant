"""FastAPI app: research SSE UI."""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.graph import stream_research

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

UI_DIR = Path(__file__).parent / "ui"

app = FastAPI(title="Reasonance AI Research Assistant")
app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")

_threads: dict[str, str] = {}


class ResearchRequest(BaseModel):
    question: str


@app.get("/")
async def index():
    return FileResponse(UI_DIR / "index.html")


@app.post("/research")
async def start_research(req: ResearchRequest):
    thread_id = str(uuid.uuid4())
    _threads[thread_id] = req.question
    return {"thread_id": thread_id}


@app.get("/stream/{thread_id}")
async def stream(thread_id: str):
    question = _threads.get(thread_id, "")

    async def event_generator():
        try:
            async for event in stream_research(question, thread_id):
                yield {"data": json.dumps(event, default=str)}
        except Exception as e:
            logger.exception("Graph stream error for thread %s", thread_id)
            yield {"data": json.dumps({"kind": "error", "error": f"{type(e).__name__}: {e}"})}
        yield {"data": json.dumps({"kind": "end"})}

    return EventSourceResponse(event_generator())
