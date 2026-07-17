"""Researcher node: runs tool-calling loops per sub-question to gather findings."""
from __future__ import annotations

import json

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.state import ResearchState
from app.llm import get_chat_model
from app.tools.fetch_url import fetch_url
from app.tools.search_local_docs import search_local_docs
from app.tools.summarize import summarize
from app.tools.web_search import web_search

MAX_TOOL_CALLS_PER_SUB = 4

SYSTEM_PROMPT = (
    "You are a focused researcher. Use tools to find 1-3 supporting facts with real "
    "source URLs for the given sub-question. When you have enough, reply with a JSON "
    "list of findings."
)

TOOLS = [web_search, fetch_url, search_local_docs, summarize]
TOOL_BY_NAME = {t.name: t for t in TOOLS}


def _extract_urls_from_messages(messages: list[BaseMessage]) -> set[str]:
    """Collect all URLs that appeared in tool-message content."""
    urls: set[str] = set()
    for msg in messages:
        if isinstance(msg, ToolMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            for token in content.split():
                if token.startswith("http://") or token.startswith("https://"):
                    urls.add(token.rstrip(".,;)\"'"))
            # Also look inside JSON-like list results
            try:
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict):
                            for v in item.values():
                                if isinstance(v, str) and v.startswith("http"):
                                    urls.add(v)
            except (json.JSONDecodeError, TypeError):
                pass
    return urls


def researcher_node(state: ResearchState) -> dict:
    base_model = get_chat_model()
    model = base_model.bind_tools(TOOLS)
    sub_questions: list[dict] = state["sub_questions"]
    total = len(sub_questions)
    all_findings: list[dict] = []
    step_log: list[str] = []

    for idx, sub_q in enumerate(sub_questions):
        messages: list[BaseMessage] = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=sub_q["text"]),
        ]
        tool_calls_used = 0

        for _ in range(MAX_TOOL_CALLS_PER_SUB):
            try:
                ai_msg = model.invoke(messages)
            except Exception as e:
                step_log.append(f"[sub {idx + 1}/{total}] ERROR invoking model: {e!s:.100}")
                break
            messages.append(ai_msg)

            if not ai_msg.tool_calls:
                break

            # Only process tool calls with valid names (Bedrock rejects invalid chars)
            valid_calls = [tc for tc in ai_msg.tool_calls if tc["name"] in TOOL_BY_NAME]
            invalid_calls = [tc for tc in ai_msg.tool_calls if tc["name"] not in TOOL_BY_NAME]

            # Replace the AI message in history with one containing only valid tool calls
            # so Bedrock won't reject the conversation on the next turn
            if invalid_calls:
                messages.pop()  # remove the original ai_msg
                cleaned_msg = AIMessage(
                    content=ai_msg.content,
                    tool_calls=valid_calls,
                )
                messages.append(cleaned_msg)
                for tc in invalid_calls:
                    step_log.append(f"[sub {idx + 1}/{total}] SKIPPED unknown tool: {tc['name']}")

            if not valid_calls:
                break

            for tc in valid_calls:
                tool_calls_used += 1
                tool_fn = TOOL_BY_NAME[tc["name"]]
                try:
                    result = tool_fn.invoke(tc["args"])
                except Exception as e:
                    result = f"Error running {tc['name']}: {e}"
                messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
                step_log.append(f"[sub {idx + 1}/{total}] {tc['name']}({next(iter(tc['args'].values()), '')!r})")

                if tool_calls_used >= MAX_TOOL_CALLS_PER_SUB:
                    break

            if tool_calls_used >= MAX_TOOL_CALLS_PER_SUB:
                break

        # Force the model to output findings JSON by invoking WITHOUT tools
        messages.append(HumanMessage(content=(
            "Now output ONLY a JSON list of findings. Each finding: "
            '{"claim": "...", "evidence_url": "...", "evidence_text": "..."}. '
            "Use only URLs from the tool results above. Output the raw JSON array, nothing else."
        )))
        try:
            ai_msg = base_model.invoke(messages)
        except Exception:
            ai_msg = messages[-2] if len(messages) > 2 else ai_msg  # fallback

        # Parse the final AI message for findings JSON
        seen_urls = _extract_urls_from_messages(messages)
        raw_content = ai_msg.content
        if isinstance(raw_content, str):
            content = raw_content
        elif isinstance(raw_content, list):
            content = "".join(
                block.get("text", "") if isinstance(block, dict) and block.get("type") == "text"
                else block if isinstance(block, str)
                else ""
                for block in raw_content
            )
        else:
            content = str(raw_content)

        findings: list[dict] = []
        try:
            parsed = json.loads(content)
            if isinstance(parsed, list):
                findings = parsed
        except (json.JSONDecodeError, TypeError):
            pass

        if not findings:
            start = content.find("[")
            end = content.rfind("]")
            if start != -1 and end != -1:
                try:
                    parsed = json.loads(content[start : end + 1])
                    if isinstance(parsed, list):
                        findings = parsed
                except (json.JSONDecodeError, TypeError):
                    pass

        for f in findings:
            if not isinstance(f, dict):
                continue
            f["sub_question_index"] = idx
            url = f.get("evidence_url", "")
            if not url:
                continue
            # Check if URL (or its domain) appeared in tool messages
            url_found = url in seen_urls or any(url in s or s in url for s in seen_urls)
            if url_found:
                all_findings.append(f)
            else:
                step_log.append(f"[sub {idx + 1}/{total}] DROPPED finding (URL not in tool results): {url!r}")

        # If no findings parsed but tools returned data, create findings from tool results
        if not findings and seen_urls:
            for msg in messages:
                if isinstance(msg, ToolMessage):
                    msg_content = msg.content if isinstance(msg.content, str) else str(msg.content)
                    try:
                        tool_data = json.loads(msg_content)
                        if isinstance(tool_data, list):
                            for item in tool_data:
                                if isinstance(item, dict) and item.get("url"):
                                    all_findings.append({
                                        "sub_question_index": idx,
                                        "claim": item.get("content", item.get("title", ""))[:200],
                                        "evidence_url": item["url"],
                                        "evidence_text": item.get("content", "")[:500],
                                    })
                    except (json.JSONDecodeError, TypeError):
                        pass

    return {"findings": all_findings, "step_log": step_log}
