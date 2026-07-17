"""Query mock service metrics for the Investigator agent."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from langchain_core.tools import InjectedToolArg, tool

_DATA_ROOT = Path(__file__).resolve().parents[2] / "data"


@tool
def query_metrics(
    service: str,
    metric: str,
    since: str = "1h",
    *,
    domain: Annotated[str, InjectedToolArg] = "support",
) -> dict:
    """Fetch current metrics for a service (e.g. error_rate, latency_p99, cpu). Use this to check whether a service is healthy or degraded."""
    path = _DATA_ROOT / domain / "mock_metrics.json"
    if not path.exists():
        return {"error": f"no metrics data for domain {domain!r}"}

    data: dict = json.loads(path.read_text())

    svc_data = data.get(service, {})
    entry = svc_data.get(metric) if isinstance(svc_data, dict) else None
    if entry and isinstance(entry, dict):
        return {
            "service": service,
            "metric": metric,
            **{k: entry[k] for k in ("current", "avg", "p95", "trend") if k in entry},
        }

    # Flat structure fallback: top-level keyed by service with a single metric block
    if isinstance(svc_data, dict) and "metric" in svc_data:
        return {
            "service": svc_data.get("service", service),
            "metric": svc_data.get("metric", metric),
            "current": svc_data.get("current"),
            "avg": svc_data.get("avg"),
            "p95": svc_data.get("p95"),
            "trend": svc_data.get("trend"),
        }

    return {"service": service, "metric": metric, "error": "metric not found"}


if __name__ == "__main__":
    print(
        query_metrics.invoke(
            {"service": "auth-service", "metric": "error_rate", "since": "1h", "domain": "support"}
        )
    )
