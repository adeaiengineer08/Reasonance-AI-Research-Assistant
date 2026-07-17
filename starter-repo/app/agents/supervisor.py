"""Supervisor: pure routing logic for the ticket triage graph (no LLM)."""
from __future__ import annotations

from app.state import TicketState


def supervisor_node(state: TicketState) -> dict:
    if state.get("classification") is None:
        nxt = "triager"
    elif not state.get("investigated"):
        nxt = "investigator"
    elif state.get("draft") is None:
        nxt = "responder"
    elif state.get("approval") == "pending":
        nxt = "hitl"
    elif state.get("approval") in ("approved", "edited") and not state.get("sent"):
        nxt = "send"
    else:
        nxt = "END"

    step_log = list(state.get("step_log", []))
    step_log.append(f"Supervisor: next={nxt}")
    return {"next": nxt, "step_log": step_log}
