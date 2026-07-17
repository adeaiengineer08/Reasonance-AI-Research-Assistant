"""Investigator agent: tool-calling loop that gathers context for a classified ticket."""
from __future__ import annotations

import json

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.llm import get_chat_model
from app.state import TicketState
from app.tools.get_ticket_history import get_ticket_history
from app.tools.query_logs import query_logs
from app.tools.query_metrics import query_metrics
from app.tools.search_runbooks import search_runbooks

MAX_TOOL_CALLS = 8

SYSTEM_PROMPT = (
    "You are an investigator. Given a classified ticket, gather enough context "
    "to write an informed response. Use tools to fetch logs, metrics, runbooks, "
    "and the user's ticket history. Stop calling tools when you can clearly "
    "explain what happened and what should be done. Budget: 8 tool calls max."
)

TOOLS = [query_logs, query_metrics, search_runbooks, get_ticket_history]
TOOL_BY_NAME = {t.name: t for t in TOOLS}

SUMMARISE_PROMPT = (
    "Based on the tool results above, output ONLY a JSON list of findings. "
    'Each finding must be: {"claim": "...", "source": "...", "tool": "..."}. '
    "Output the raw JSON array, nothing else."
)


def _truncate(value: object, max_len: int = 80) -> str:
    s = str(value)
    return s if len(s) <= max_len else s[:max_len] + "…"


def _build_ticket_context(state: TicketState) -> str:
    raw = state["raw"]
    parts = [
        f"Subject: {raw.get('subject', 'N/A')}",
        f"Body: {raw.get('body', 'N/A')}",
        f"Sender: {raw.get('sender', 'N/A')}",
    ]
    cls = state.get("classification")
    if cls:
        parts.append(f"Classification: {cls.get('category', '?')} (confidence={cls.get('confidence', '?')})")
    sev = state.get("severity")
    if sev:
        parts.append(f"Severity: {sev}")
    return "\n".join(parts)


def _parse_findings(content: str) -> list[dict]:
    """Best-effort extraction of a JSON list from LLM output."""
    try:
        parsed = json.loads(content)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass

    start = content.find("[")
    end = content.rfind("]")
    if start != -1 and end != -1:
        try:
            parsed = json.loads(content[start : end + 1])
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def investigator_node(state: TicketState) -> dict:
    domain = state["domain"]
    base_model = get_chat_model()
    model = base_model.bind_tools(TOOLS)

    messages: list[BaseMessage] = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=_build_ticket_context(state)),
    ]

    step_log: list[str] = []
    tool_calls_used = 0

    for _ in range(MAX_TOOL_CALLS):
        try:
            ai_msg = model.invoke(messages)
        except Exception as e:
            step_log.append(f"Investigator: ERROR invoking model: {e!s:.120}")
            break
        messages.append(ai_msg)

        if not ai_msg.tool_calls:
            break

        valid_calls = [tc for tc in ai_msg.tool_calls if tc["name"] in TOOL_BY_NAME]
        invalid_calls = [tc for tc in ai_msg.tool_calls if tc["name"] not in TOOL_BY_NAME]

        if invalid_calls:
            messages.pop()
            messages.append(AIMessage(content=ai_msg.content, tool_calls=valid_calls))
            for tc in invalid_calls:
                step_log.append(f"Investigator: SKIPPED unknown tool: {tc['name']}")

        if not valid_calls:
            break

        for tc in valid_calls:
            tool_calls_used += 1
            tool_fn = TOOL_BY_NAME[tc["name"]]
            args_with_domain = {**tc["args"], "domain": domain}
            try:
                result = tool_fn.invoke(args_with_domain)
            except Exception as e:
                result = f"Error running {tc['name']}: {e}"

            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"], name=tc["name"]))
            step_log.append(
                f"Investigator: {tc['name']}({_truncate(tc['args'])})"
            )

            if tool_calls_used >= MAX_TOOL_CALLS:
                break

        if tool_calls_used >= MAX_TOOL_CALLS:
            break

    # Final structured-output pass (no tools) to produce findings JSON
    messages.append(HumanMessage(content=SUMMARISE_PROMPT))
    try:
        summary_msg = base_model.invoke(messages)
    except Exception:
        summary_msg = messages[-2] if len(messages) > 2 else AIMessage(content="[]")

    raw_content = summary_msg.content
    if isinstance(raw_content, list):
        raw_content = "".join(
            block.get("text", "") if isinstance(block, dict) and block.get("type") == "text"
            else block if isinstance(block, str)
            else ""
            for block in raw_content
        )
    elif not isinstance(raw_content, str):
        raw_content = str(raw_content)

    findings = _parse_findings(raw_content)

    step_log.append(f"Investigator: produced {len(findings)} findings from {tool_calls_used} tool calls")

    return {"findings": findings, "investigated": True, "step_log": state.get("step_log", []) + step_log}
