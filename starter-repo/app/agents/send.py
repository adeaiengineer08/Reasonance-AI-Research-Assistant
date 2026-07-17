"""Send node: delivers an approved (or edited) draft via the send_response tool."""
from __future__ import annotations

from app.state import TicketState
from app.tools.send_response import send_response


def send_node(state: TicketState) -> dict:
    step_log = list(state.get("step_log", []))

    if state.get("approval") not in ("approved", "edited") or state.get("sent"):
        step_log.append("Send: refused (approval not granted or already sent)")
        return {"step_log": step_log}

    draft = state["draft"] or {}
    raw = state["raw"] or {}
    result = send_response.invoke(
        {
            "ticket_id": state["ticket_id"],
            "subject": draft.get("subject", ""),
            "body": draft.get("body", ""),
            "to": raw.get("sender", ""),
        }
    )
    step_log.append(f"Send: sent as {result.get('sent_id')}")
    return {"sent": True, "step_log": step_log}
