"""Triager agent: classify a ticket into a taxonomy category and severity."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.llm import get_chat_model
from app.state import TicketState

_DATA_ROOT = Path(__file__).resolve().parents[2] / "data"


class TriageOutput(BaseModel):
    category: str
    severity: Literal["P1", "P2", "P3", "P4"]
    confidence: float
    rationale: str


def _load_taxonomy(domain: str) -> dict:
    path = _DATA_ROOT / domain / "taxonomy.yaml"
    if not path.exists():
        return {"categories": [{"name": "other", "description": "Fallback"}], "severities": ["P1", "P2", "P3", "P4"]}
    return yaml.safe_load(path.read_text()) or {}


def triager_node(state: TicketState) -> dict:
    domain = state["domain"]
    taxonomy = _load_taxonomy(domain)
    categories = taxonomy.get("categories", [])
    category_names = [c["name"] for c in categories if isinstance(c, dict) and "name" in c]
    taxonomy_text = ", ".join(
        f"{c['name']} ({c.get('description', '')})" for c in categories if isinstance(c, dict)
    )

    ticket = state["raw"]
    # TODO: episodic memory examples
    system = (
        f"You are a {domain} triage analyst. Available categories: [{taxonomy_text}]. "
        f"Given this ticket, choose the best category and severity. "
        f"Provide a brief rationale. Be conservative on severity."
    )
    human = f"Ticket: {ticket}"

    model = get_chat_model()
    structured = model.with_structured_output(TriageOutput)
    step_log = list(state.get("step_log", []))

    try:
        out: TriageOutput = structured.invoke(
            [SystemMessage(content=system), HumanMessage(content=human)]
        )
    except Exception as e:
        step_log.append(f"Triager: ERROR — {e!s:.120}")
        return {
            "classification": {
                "category": "unknown",
                "confidence": 0.0,
                "rationale": f"triager error: {e!s:.80}",
            },
            "severity": "P3",
            "step_log": step_log,
        }

    category = out.category
    severity = out.severity
    if category not in category_names:
        category = "unknown"
        severity = "P3"
        step_log.append(f"Triager: invalid category {out.category!r}; defaulted to unknown/P3")
    else:
        step_log.append(f"Triager: category={category} severity={severity} conf={out.confidence:.2f}")

    return {
        "classification": {
            "category": category,
            "confidence": out.confidence,
            "rationale": out.rationale,
        },
        "severity": severity,
        "step_log": step_log,
    }
