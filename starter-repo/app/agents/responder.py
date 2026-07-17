"""Responder agent: drafts a customer-facing reply using all three memory layers."""
from __future__ import annotations

import json
import re
from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from app.llm import get_chat_model
from app.memory.episodic import similar_past_cases
from app.memory.procedural import get_responder_prompt
from app.memory.semantic import recall_user
from app.state import TicketState


class ResponderOutput(BaseModel):
    subject: str
    body: str
    recommended_action: Literal["send", "escalate"]
    confidence: float
    risk_flags: list[str]


_PII_PATTERNS: list[tuple[str, str]] = [
    ("email", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ("phone", r"(?:(?:\+?\d{1,3}[-.\s])?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})"),
    ("credit_card", r"\b(?:\d[ -]*?){13,16}\b"),
]

_ESCALATION_KEYWORDS = ("refund", "credit", "guarantee", "tomorrow", "by eod", "by end of day")


def _check_escalation_triggers(body: str) -> list[str]:
    """Return a list of risk flags that force escalation."""
    flags: list[str] = []
    low = body.lower()

    for kw in _ESCALATION_KEYWORDS:
        if kw in low:
            flags.append(f"keyword:{kw}")

    for name, pattern in _PII_PATTERNS:
        if re.search(pattern, body):
            flags.append(f"pii:{name}")

    return flags


def _build_prompt_messages(
    state: TicketState,
    style_prompt: str,
    episodes: list[dict],
    user_memories: list[dict],
) -> list[BaseMessage]:
    """Assemble the full message list for the LLM."""
    messages: list[BaseMessage] = [SystemMessage(content=style_prompt)]

    # Few-shot pairs from episodic memory
    for ep in episodes:
        messages.append(HumanMessage(content=ep.get("ticket_text", "")))
        messages.append(AIMessage(content=ep.get("resolution_text", "")))

    # Build the actual user message
    raw = state["raw"]
    sections = []

    if user_memories:
        mem_lines = [m.get("value", {}).get("content", str(m.get("value", ""))) for m in user_memories]
        sections.append("What we know about this user:\n" + "\n".join(f"- {line}" for line in mem_lines))

    sections.append(f"Subject: {raw.get('subject', 'N/A')}")
    sections.append(f"Body: {raw.get('body', 'N/A')}")
    sections.append(f"Sender: {raw.get('sender', 'N/A')}")

    cls = state.get("classification")
    if cls:
        sections.append(
            f"Classification: {cls.get('category', '?')} "
            f"(confidence={cls.get('confidence', '?')}, rationale={cls.get('rationale', '?')})"
        )
    sev = state.get("severity")
    if sev:
        sections.append(f"Severity: {sev}")

    findings = state.get("findings") or []
    if findings:
        sections.append("Investigation findings:\n" + json.dumps(findings, indent=2, ensure_ascii=False))

    messages.append(HumanMessage(content="\n\n".join(sections)))
    return messages


def responder_node(state: TicketState) -> dict:
    domain = state["domain"]
    step_log: list[str] = []

    # 1. Procedural memory — style prompt
    style_prompt = get_responder_prompt(domain)
    step_log.append(f"Responder: loaded style prompt for domain={domain}")

    # 2. Episodic memory — similar past cases
    episodes = similar_past_cases(state["raw"]["body"], domain, k=3)
    step_log.append(f"Responder: found {len(episodes)} episodic examples")

    # 3. Semantic memory — user-specific facts
    user_memories = recall_user(state["raw"]["sender"], k=3)
    step_log.append(f"Responder: found {len(user_memories)} user memories")

    # 4. Build prompt and invoke with structured output
    messages = _build_prompt_messages(state, style_prompt, episodes, user_memories)

    model = get_chat_model()
    structured_model = model.with_structured_output(ResponderOutput)

    try:
        out: ResponderOutput = structured_model.invoke(messages)
    except Exception as e:
        step_log.append(f"Responder: ERROR — {e!s:.120}")
        fallback = ResponderOutput(
            subject=f"Re: {state['raw'].get('subject', 'your request')}",
            body="We have received your request and are looking into it. A team member will follow up shortly.",
            recommended_action="escalate",
            confidence=0.0,
            risk_flags=["llm_error"],
        )
        return {
            "draft": fallback.model_dump(),
            "approval": "pending",
            "step_log": state.get("step_log", []) + step_log,
        }

    # 5. Post-process: forced escalation checks
    triggers = _check_escalation_triggers(out.body)

    if out.confidence < 0.6:
        triggers.append("low_confidence")

    if triggers:
        out.recommended_action = "escalate"
        out.risk_flags = list({*out.risk_flags, *triggers})

    step_log.append(
        f"Responder: action={out.recommended_action} confidence={out.confidence:.2f} "
        f"flags={out.risk_flags}"
    )

    return {
        "draft": out.model_dump(),
        "approval": "pending",
        "step_log": state.get("step_log", []) + step_log,
    }
