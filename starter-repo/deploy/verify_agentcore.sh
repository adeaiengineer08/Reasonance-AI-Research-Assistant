#!/usr/bin/env bash
# Local smoke test for AgentCore entrypoint + production graph compile path.
set -euo pipefail

cd "$(dirname "$0")/.."

export PYTHONPATH=.
export LANGCHAIN_TRACING_V2=false
export LANGSMITH_TRACING=false
export MONK_MODEL="${MONK_MODEL:-fake}"
export MONK_EMBEDDINGS="${MONK_EMBEDDINGS:-fake}"

echo "==> Import entrypoint"
.venv/bin/python -c "from agentcore_entrypoint import app, handler; print('  entrypoint ok:', type(app).__name__)"

echo "==> Compile graph via build_graph_with_backends"
.venv/bin/python - <<'PY'
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from app.ticket_graph import build_graph_with_backends

graph = build_graph_with_backends(saver=MemorySaver(), store=None)
payload = {
    "ticket_id": "verify-1",
    "raw": {
        "subject": "Cannot log in - MFA loop",
        "body": "Every time I enter my MFA code it just asks me again.",
        "sender": "alice@example.com",
    },
    "domain": "support",
    "classification": None,
    "severity": None,
    "findings": [],
    "investigated": False,
    "draft": None,
    "approval": "pending",
    "sent": False,
    "next": "",
    "step_log": [],
}
cfg = {"configurable": {"thread_id": "verify-agentcore"}, "recursion_limit": 50}
graph.invoke(payload, cfg)
snap = graph.get_state(cfg)
pending = any(t.interrupts for t in snap.tasks)
if not pending:
    raise SystemExit("expected HITL interrupt; graph did not pause")
print("  graph paused at HITL ok")
graph.invoke(Command(resume={"action": "approve", "edited_body": None}), cfg)
final = graph.get_state(cfg).values
if not final.get("sent"):
    raise SystemExit("expected sent=True after approve")
print("  approve + send ok")
PY

echo "==> All local checks passed"
