"""Semantic memory: per-user facts and preferences backed by a LangGraph Store."""
from __future__ import annotations

import os
import re
import uuid

from langgraph.store.memory import InMemoryStore


def _safe_label(value: str) -> str:
    """Sanitize a string for use as a LangGraph Store namespace label (no dots allowed)."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", value)


def _get_store():
    backend = os.getenv("MONK_MEMORY", "memory").strip().lower()
    if backend == "postgres":
        from langgraph.store.postgres import PostgresStore

        dsn = os.getenv("POSTGRES_DSN", "")
        store = PostgresStore.from_conn_string(dsn)
        store.setup()
        return store
    return InMemoryStore()


_store = None


def _store_instance():
    global _store
    if _store is None:
        _store = _get_store()
    return _store


def recall_user(user_id: str, k: int = 3) -> list[dict]:
    """Retrieve the top-k semantic memories for a user."""
    store = _store_instance()
    namespace = ("user_memory", _safe_label(user_id))
    try:
        results = store.search(namespace, query=user_id, limit=k)
    except Exception:
        try:
            results = store.search(namespace, limit=k)
        except Exception:
            return []
    return [
        {"key": item.key, "value": item.value, "score": getattr(item, "score", 0.0)}
        for item in results
    ]


def remember_user(user_id: str, content: str) -> None:
    """Store a fact or preference about a user."""
    store = _store_instance()
    namespace = ("user_memory", _safe_label(user_id))
    key = str(uuid.uuid4())[:8]
    store.put(namespace, key, {"content": content})
