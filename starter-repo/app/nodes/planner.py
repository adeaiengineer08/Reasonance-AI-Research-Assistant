"""Planner node: decomposes a question into 3-7 sub-questions with source tags."""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.state import ResearchState
from app.llm import get_chat_model

SYSTEM_PROMPT = (
    "You are a research planner. Given a user question, decompose it into 3-7 focused "
    "sub-questions that together would provide a comprehensive answer. "
    "Ensure every key entity, concept, and aspect mentioned in the question is explicitly "
    "addressed by at least one sub-question — do not leave any topic implied or assumed. "
    "For each sub-question, tag it with a source: 'web' for current events or general "
    "knowledge, 'local' for internal documentation, or 'both' if unsure. "
    "Return structured output."
)


class SubQuestion(BaseModel):
    text: str = Field(description="The sub-question to research")
    source: str = Field(description="One of: web, local, both")


class PlannerOutput(BaseModel):
    sub_questions: list[SubQuestion] = Field(min_length=3, max_length=7)


def _format_memories(memories: list[dict]) -> str:
    """Format recalled memories into a prompt-friendly block."""
    if not memories:
        return ""
    lines = ["Memories:"]
    for m in memories:
        val = m.get("value", {})
        lines.append(f"- [{val.get('kind', '?')}] {val.get('content', '')}")
    return "\n".join(lines)


def planner_node(state: ResearchState) -> dict:
    import json as _json

    model = get_chat_model()

    system = SYSTEM_PROMPT
    memories = state.get("memories") or []
    mem_block = _format_memories(memories)
    if mem_block:
        system = f"{system}\n\n{mem_block}"

    messages = [
        SystemMessage(content=system),
        HumanMessage(content=state["question"]),
    ]

    # Try structured output first; fall back to manual JSON parsing
    try:
        structured = model.with_structured_output(PlannerOutput)
        result = structured.invoke(messages)
        if result is not None:
            sub_questions = [{"text": sq.text, "source": sq.source} for sq in result.sub_questions]
            return {
                "sub_questions": sub_questions,
                "step_log": [f"Planner: generated {len(sub_questions)} sub-questions"],
            }
    except Exception:
        pass

    # Fallback: invoke without structured output and parse JSON from response
    ai_msg = model.invoke(messages)
    content = ai_msg.content
    if isinstance(content, list):
        content = "".join(
            block.get("text", "") if isinstance(block, dict) and block.get("type") == "text"
            else block if isinstance(block, str)
            else ""
            for block in content
        )

    # Extract JSON array from response
    start = content.find("[")
    end = content.rfind("]")
    if start != -1 and end != -1:
        try:
            items = _json.loads(content[start : end + 1])
            sub_questions = [
                {"text": item.get("text", item.get("question", "")), "source": item.get("source", "both")}
                for item in items
                if isinstance(item, dict)
            ][:7]
            if sub_questions:
                return {
                    "sub_questions": sub_questions,
                    "step_log": [f"Planner: generated {len(sub_questions)} sub-questions (fallback parse)"],
                }
        except _json.JSONDecodeError:
            pass

    # Last resort: treat the whole question as a single sub-question
    return {
        "sub_questions": [{"text": state["question"], "source": "both"}],
        "step_log": ["Planner: could not decompose question, using original as single sub-question"],
    }
