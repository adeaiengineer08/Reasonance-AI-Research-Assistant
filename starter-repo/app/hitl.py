"""Human-in-the-loop gate: pause for approval before sending a draft reply."""
from __future__ import annotations

from langgraph.types import interrupt

from app.state import TicketState


def hitl_node(state: TicketState) -> dict:
    """Pause the graph and apply the human's approve / edit / reject decision."""
    payload = interrupt(
        {
            "draft": state["draft"],
            "classification": state["classification"],
            "severity": state["severity"],
            "findings": state["findings"],
            "raw": state["raw"],
        }
    )
    # Resume payload: {"action": "approve"|"edit"|"reject", "edited_body": str | None}
    action = (payload or {}).get("action")
    step_log = list(state.get("step_log", []))

    if action == "approve":
        step_log.append("HITL: approved")
        return {"approval": "approved", "step_log": step_log}

    if action == "edit":
        draft = dict(state["draft"] or {})
        draft["body"] = payload.get("edited_body")
        step_log.append("HITL: edited body")
        return {"approval": "edited", "draft": draft, "step_log": step_log}

    if action == "reject":
        step_log.append("HITL: rejected")
        return {"approval": "rejected", "step_log": step_log}

    step_log.append(f"HITL: unknown action {action!r}; treating as rejected")
    return {"approval": "rejected", "step_log": step_log}
