"""Mock send tool: logs the outbound reply to a JSONL file and returns a fake id."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from langchain_core.tools import tool

_LOG = Path(__file__).resolve().parents[2] / "data" / "sent_responses.jsonl"


@tool
def send_response(ticket_id: str, subject: str, body: str, to: str) -> dict:
    """Send a drafted reply to the ticket requester. Use this when a human has approved the draft."""
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    fake_id = f"SND-{uuid.uuid4().hex[:8]}"
    record = {
        "sent_id": fake_id,
        "ticket_id": ticket_id,
        "subject": subject,
        "body": body,
        "to": to,
        "ts": datetime.now(UTC).isoformat(),
    }
    with _LOG.open("a") as f:
        f.write(json.dumps(record) + "\n")
    return {"sent_id": fake_id, "status": "ok"}
