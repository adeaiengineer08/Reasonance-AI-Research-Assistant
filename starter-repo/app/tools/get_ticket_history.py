"""Retrieve a user's past ticket history for the Investigator agent."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from langchain_core.tools import InjectedToolArg, tool

_DATA_ROOT = Path(__file__).resolve().parents[2] / "data"


@tool
def get_ticket_history(
    user_id: str,
    k: int = 5,
    *,
    domain: Annotated[str, InjectedToolArg] = "support",
) -> list[dict]:
    """Fetch the most recent tickets from a user. Use this to check if a user has reported similar issues before."""
    path = _DATA_ROOT / domain / "historical_tickets.jsonl"
    if not path.exists():
        return [{"error": f"no ticket history for domain {domain!r}"}]

    matches: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        ticket = json.loads(line)
        if ticket.get("sender") == user_id or ticket.get("user_id") == user_id:
            matches.append(ticket)

    return matches[-k:]


if __name__ == "__main__":
    print(
        get_ticket_history.invoke(
            {"user_id": "priya.s@example.com", "k": 5, "domain": "support"}
        )
    )
