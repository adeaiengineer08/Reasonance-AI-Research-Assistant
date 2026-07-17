"""FastAPI app: research SSE UI + ticket triage HITL approval API."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.graph import get_ticket_graph, stream_research

_executor = ThreadPoolExecutor(max_workers=4)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

UI_DIR = Path(__file__).parent / "ui"

app = FastAPI(title="Monk Agents")
app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")

_threads: dict[str, str] = {}
_ticket_threads: set[str] = set()


class ResearchRequest(BaseModel):
    question: str


class IngestRequest(BaseModel):
    ticket: dict
    domain: Literal["support", "it-helpdesk", "oncall"]


class ApproveRequest(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edited_body: str | None = None


@app.get("/")
async def index():
    return FileResponse(UI_DIR / "index.html")


@app.get("/approval")
async def approval_page():
    return FileResponse(UI_DIR / "approval.html")


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


def _run_ticket_graph(thread_id: str, ticket: dict, domain: str) -> None:
    graph = get_ticket_graph()
    ticket_id = str(ticket.get("id") or ticket.get("ticket_id") or thread_id)
    try:
        result = graph.invoke(
            {
                "ticket_id": ticket_id,
                "raw": ticket,
                "domain": domain,
                "classification": None,
                "severity": None,
                "findings": [],
                "investigated": False,
                "draft": None,
                "approval": "pending",
                "sent": False,
                "next": "",
                "step_log": [],
            },
            config={"configurable": {"thread_id": thread_id}, "recursion_limit": 50},
        )
        logger.info(
            "Ticket graph for %s returned (approval=%s, sent=%s)",
            thread_id,
            result.get("approval") if isinstance(result, dict) else "?",
            result.get("sent") if isinstance(result, dict) else "?",
        )
    except Exception as exc:
        logger.exception("Ticket graph failed for thread %s: %s", thread_id, type(exc).__name__)


@app.post("/ingest")
async def ingest(req: IngestRequest):
    thread_id = str(uuid.uuid4())
    _ticket_threads.add(thread_id)
    loop = asyncio.get_event_loop()
    loop.run_in_executor(_executor, _run_ticket_graph, thread_id, req.ticket, req.domain)
    return {"thread_id": thread_id}


def _interrupt_payload(snap) -> dict | None:
    """Extract the first pending HITL interrupt value from a state snapshot."""
    for task in snap.tasks or ():
        for intr in getattr(task, "interrupts", ()) or ():
            value = getattr(intr, "value", None)
            if value is not None:
                return value
    return None


@app.get("/pending")
async def pending():
    graph = get_ticket_graph()
    items: list[dict] = []
    for thread_id in list(_ticket_threads):
        snap = graph.get_state({"configurable": {"thread_id": thread_id}})
        payload = _interrupt_payload(snap)
        if payload is not None:
            items.append({"thread_id": thread_id, "payload": payload})
    return items


@app.post("/approve/{thread_id}")
async def approve(thread_id: str, req: ApproveRequest):
    if thread_id not in _ticket_threads:
        raise HTTPException(status_code=404, detail="unknown thread_id")

    graph = get_ticket_graph()
    snap = graph.get_state({"configurable": {"thread_id": thread_id}})
    if _interrupt_payload(snap) is None:
        raise HTTPException(status_code=409, detail="thread is not waiting for approval")

    resume_payload = {"action": req.action, "edited_body": req.edited_body}
    try:
        graph.invoke(
            Command(resume=resume_payload),
            config={"configurable": {"thread_id": thread_id}},
        )
    except Exception as e:
        logger.exception("Resume failed for thread %s", thread_id)
        raise HTTPException(status_code=500, detail=str(e)) from e

    return {"ok": True, "thread_id": thread_id, "action": req.action}
