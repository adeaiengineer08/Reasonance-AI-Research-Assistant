"""Project 1 research-graph memory: store helpers + recall/extract nodes.

Uses InMemoryStore (default) or PostgresStore depending on the MONK_MEMORY env var.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.store.memory import InMemoryStore

from app.llm import get_chat_model
from app.state import ResearchState

logger = logging.getLogger(__name__)


def get_memory_store():
    """Return the configured memory store based on MONK_MEMORY env var."""
    backend = os.getenv("MONK_MEMORY", "memory").strip().lower()
    if backend == "postgres":
        from langgraph.store.postgres import PostgresStore

        dsn = os.getenv("POSTGRES_DSN", "")
        store = PostgresStore.from_conn_string(dsn)
        store.setup()
        return store

    return InMemoryStore()


def recall(store, namespace: tuple[str, ...], query: str, k: int = 3) -> list[dict]:
    """Search the store for memories. Returns list of {key, value, score}."""
    try:
        results = store.search(namespace, query=query, limit=k)
    except Exception:
        try:
            results = store.search(namespace, limit=k)
        except Exception:
            return []
    return [
        {"key": item.key, "value": item.value, "score": getattr(item, "score", 0.0)}
        for item in results
    ]


def remember(
    store,
    namespace: tuple[str, ...],
    content: str,
    kind: Literal["preference", "fact"],
) -> None:
    """Write a memory to the store with an auto-generated key."""
    key = str(uuid.uuid4())[:8]
    store.put(namespace, key, {"content": content, "kind": kind})


_store = None


def _get_store():
    global _store
    if _store is None:
        _store = get_memory_store()
    return _store


def recall_node(state: ResearchState) -> dict:
    """Pull top-3 memories for the current user and inject into state."""
    store = _get_store()
    user_id = state.get("user_id", "default")
    namespace = ("user_memory", user_id)
    memories = recall(store, namespace, state["question"], k=3)
    step_log: list[str] = []
    if memories:
        step_log.append(f"Recall: found {len(memories)} memories")
    else:
        step_log.append("Recall: no memories found")
    return {"memories": memories, "step_log": step_log}


_EXTRACT_SYSTEM_PROMPT = (
    "Looking at the user's question and the report, is there any preference or stable fact "
    "about this user worth remembering for future interactions? "
    'Return JSON with "worth_remembering": bool and "content": str.'
)


def _parse_content(raw) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) and block.get("type") == "text"
            else block if isinstance(block, str)
            else ""
            for block in raw
        )
    return str(raw)


def extract_node(state: ResearchState) -> dict:
    """Ask the LLM if anything from this interaction is worth remembering."""
    store = _get_store()
    user_id = state.get("user_id", "default")
    namespace = ("user_memory", user_id)

    model = get_chat_model()
    messages = [
        SystemMessage(content=_EXTRACT_SYSTEM_PROMPT),
        HumanMessage(
            content=f"Question: {state['question']}\n\nReport:\n{state['report'][:2000]}"
        ),
    ]

    step_log: list[str] = []
    try:
        ai_msg = model.invoke(messages)
        content = _parse_content(ai_msg.content)

        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1:
            result = json.loads(content[start : end + 1])
            if result.get("worth_remembering") and result.get("content"):
                kind: Literal["preference", "fact"] = (
                    "preference" if "prefer" in result["content"].lower() else "fact"
                )
                remember(store, namespace, result["content"], kind)
                step_log.append(f"Extract: remembered as {kind}")
            else:
                step_log.append("Extract: nothing worth remembering")
        else:
            step_log.append("Extract: could not parse LLM response")
    except Exception as e:
        step_log.append(f"Extract: error — {e!s:.80}")

    return {"step_log": step_log}
