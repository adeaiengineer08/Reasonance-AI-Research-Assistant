"""Query mock service logs for the Investigator agent."""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from langchain_core.tools import InjectedToolArg, tool

_DATA_ROOT = Path(__file__).resolve().parents[2] / "data"

_DURATION_RE = re.compile(r"(\d+)\s*(h|m|s|d)")

_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _parse_since(since: str) -> timedelta:
    total = 0
    for amount, unit in _DURATION_RE.findall(since.lower()):
        total += int(amount) * _UNIT_SECONDS[unit]
    return timedelta(seconds=total) if total else timedelta(hours=1)


@tool
def query_logs(
    service: str,
    since: str = "1h",
    *,
    domain: Annotated[str, InjectedToolArg] = "support",
) -> list[dict]:
    """Fetch recent log entries for a service. Use this to look for errors, warnings, or unusual activity that might explain a support ticket."""
    path = _DATA_ROOT / domain / "mock_logs.json"
    if not path.exists():
        return [{"error": f"no log data for domain {domain!r}"}]

    logs_by_service: dict[str, list[dict]] = json.loads(path.read_text())
    entries = logs_by_service.get(service, [])
    if not entries:
        return []

    cutoff = datetime.now(UTC) - _parse_since(since)
    return [
        e
        for e in entries
        if datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")) >= cutoff
    ]


if __name__ == "__main__":
    print(query_logs.invoke({"service": "auth-service", "since": "24h", "domain": "support"}))
