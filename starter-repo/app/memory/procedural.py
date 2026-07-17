"""Procedural memory: versioned responder style prompts stored as JSON on disk."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "data" / "prompts"

_DEFAULT_PROMPT = (
    "You are a helpful, professional support agent for Monk Technologies. "
    "Write a clear, empathetic response that addresses the customer's issue. "
    "Be concise but thorough. Always suggest a concrete next step."
)


def _prompt_path(domain: str) -> Path:
    safe = domain.replace("-", "_")
    return _PROMPTS_DIR / f"responder_{safe}.json"


def _load_history(domain: str) -> list[dict]:
    path = _prompt_path(domain)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def get_responder_prompt(domain: str, version: str = "latest") -> str:
    """Return the responder style prompt for a domain.

    ``version`` can be ``"latest"`` (default) or a 0-based index string like ``"0"``.
    Falls back to a built-in default if no prompt file exists.
    """
    history = _load_history(domain)
    if not history:
        return _DEFAULT_PROMPT

    if version == "latest":
        return history[-1].get("prompt", _DEFAULT_PROMPT)

    try:
        idx = int(version)
        return history[idx].get("prompt", _DEFAULT_PROMPT)
    except (ValueError, IndexError):
        return history[-1].get("prompt", _DEFAULT_PROMPT)


def set_responder_prompt(domain: str, prompt: str) -> None:
    """Append a new version of the responder prompt for a domain."""
    history = _load_history(domain)
    history.append({
        "version": len(history),
        "prompt": prompt,
        "created_at": datetime.now(UTC).isoformat(),
    })
    path = _prompt_path(domain)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2, ensure_ascii=False) + "\n")
