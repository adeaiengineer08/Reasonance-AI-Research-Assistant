"""Shared state definitions for all graphs."""
from typing import Literal, TypedDict


class ResearchState(TypedDict):
    question: str
    user_id: str
    memories: list[dict]  # recalled memories: {"key": str, "value": dict, "score": float}
    sub_questions: list[dict]  # {"text": str, "source": Literal["web", "local", "both"]}
    findings: list[dict]  # {"sub_question_index": int, "claim": str, "evidence_url": str, "evidence_text": str}
    report: str
    step_log: list[str]


class TicketState(TypedDict):
    ticket_id: str
    raw: dict  # {"subject": str, "body": str, "sender": str, ...}
    domain: Literal["support", "it-helpdesk", "oncall"]
    classification: dict | None  # {"category": str, "confidence": float, "rationale": str}
    severity: Literal["P1", "P2", "P3", "P4"] | None
    findings: list[dict]
    investigated: bool  # set True after investigator runs (prevents re-loop on empty findings)
    draft: dict | None
    approval: Literal["pending", "approved", "edited", "rejected"]
    sent: bool
    next: str  # supervisor routing target
    step_log: list[str]
