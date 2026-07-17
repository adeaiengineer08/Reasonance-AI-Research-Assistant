"""Shared state definitions for Project 1 graphs."""
from typing import Literal, TypedDict


class ResearchState(TypedDict):
    question: str
    user_id: str
    memories: list[dict]  # recalled memories: {"key": str, "value": dict, "score": float}
    sub_questions: list[dict]  # {"text": str, "source": Literal["web", "local", "both"]}
    findings: list[dict]  # {"sub_question_index": int, "claim": str, "evidence_url": str, "evidence_text": str}
    report: str
    step_log: list[str]
