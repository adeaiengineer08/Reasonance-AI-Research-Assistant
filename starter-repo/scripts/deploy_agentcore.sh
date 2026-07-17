#!/usr/bin/env bash
# Monk Technologies - deploy Project 2 (Ticket Triage) to AWS Bedrock AgentCore.
# Day 7. Requires bedrock-agentcore-starter-toolkit installed.

set -euo pipefail

bold() { printf "\033[1m%s\033[0m\n" "$*"; }

# Load .env if present
if [[ -f .env ]]; then
    # shellcheck disable=SC2046
    export $(grep -v '^#' .env | xargs -0 2>/dev/null || true)
fi

NAME="${AGENT_NAME:-monk_ticket_triage}"
ENTRYPOINT="${ENTRYPOINT:-agentcore_entrypoint.py}"
REPO_ROOT="$(pwd)"
ENTRYPOINT_ABS="$REPO_ROOT/$(basename "$ENTRYPOINT")"
REGION="${AWS_REGION:-us-east-1}"

export AGENTCORE_SUPPRESS_RECOMMENDATION=1
bold "Monk Technologies - deploy $NAME to AWS Bedrock AgentCore"
echo

AGENTCORE_BIN="agentcore"
if ! command -v agentcore >/dev/null 2>&1; then
    if [[ -x .venv/bin/agentcore ]]; then
        AGENTCORE_BIN=".venv/bin/agentcore"
    else
        echo "agentcore CLI not found. Installing..."
        uv pip install bedrock-agentcore-starter-toolkit
        AGENTCORE_BIN=".venv/bin/agentcore"
    fi
fi

bold "1. Configure"
if ! "$AGENTCORE_BIN" configure list 2>/dev/null | grep -q "$NAME"; then
    "$AGENTCORE_BIN" configure \
        --name "$NAME" \
        --entrypoint "$ENTRYPOINT_ABS" \
        --runtime PYTHON_3_11 \
        --deployment-type direct_code_deploy \
        --requirements-file deploy/requirements.txt \
        --region "$REGION" \
        --non-interactive \
        --disable-otel \
        --idle-timeout 600 \
        --max-lifetime 28800
else
    "$AGENTCORE_BIN" configure \
        --name "$NAME" \
        --entrypoint "$ENTRYPOINT_ABS" \
        --runtime PYTHON_3_11 \
        --deployment-type direct_code_deploy \
        --requirements-file deploy/requirements.txt \
        --region "$REGION" \
        --non-interactive \
        --disable-otel \
        --idle-timeout 600 \
        --max-lifetime 28800
fi

# configure may set source_path to the entrypoint directory; keep the full repo root.
.venv/bin/python - <<'PY'
import pathlib
import yaml

repo = pathlib.Path(".").resolve()
cfg_path = repo / ".bedrock_agentcore.yaml"
data = yaml.safe_load(cfg_path.read_text())
agent = data["agents"][data["default_agent"]]
agent["source_path"] = str(repo)
agent["entrypoint"] = str(repo / "agentcore_entrypoint.py")
cfg_path.write_text(yaml.safe_dump(data, sort_keys=False))
print("source_path pinned to repo root")
PY

bold "2. Launch"
# AgentCore resolves dependencies from project root (pyproject.toml wins unless
# requirements.txt exists at repo root). Stage deploy-specific requirements.
if [[ -f requirements.txt ]]; then
    cp requirements.txt requirements.txt.bak.agentcore
    RESTORE_REQ=1
else
    RESTORE_REQ=0
fi
cp deploy/requirements.txt requirements.txt

ENV_ARGS=()
if [[ -n "${POSTGRES_DSN:-}" ]]; then
    ENV_ARGS+=(--env "POSTGRES_DSN=$POSTGRES_DSN")
fi
if [[ -n "${MONK_MODEL:-}" ]]; then
    ENV_ARGS+=(--env "MONK_MODEL=$MONK_MODEL")
fi
if [[ -n "${MONK_EMBEDDINGS:-}" ]]; then
    ENV_ARGS+=(--env "MONK_EMBEDDINGS=$MONK_EMBEDDINGS")
fi
if [[ -n "${AWS_REGION:-}" ]]; then
    ENV_ARGS+=(--env "AWS_REGION=$AWS_REGION")
fi
ENV_ARGS+=(--env "LANGCHAIN_TRACING_V2=false")
ENV_ARGS+=(--env "MONK_CHECKPOINTER=${MONK_CHECKPOINTER:-memory}")

# Build dependency bundle (macOS uv embeds local venv paths in bin/* — fix before upload).
"$AGENTCORE_BIN" launch --agent "$NAME" --auto-update-on-conflict --force-rebuild-deps "${ENV_ARGS[@]}"
LAUNCH_BUILD_EXIT=$?
.venv/bin/python deploy/fix_agentcore_deps_zip.py
"$AGENTCORE_BIN" launch --agent "$NAME" --auto-update-on-conflict "${ENV_ARGS[@]}"
LAUNCH_EXIT=$?
if [[ "$RESTORE_REQ" == 1 ]]; then
    mv requirements.txt.bak.agentcore requirements.txt
else
    rm -f requirements.txt
fi
if [[ "$LAUNCH_BUILD_EXIT" -ne 0 || "$LAUNCH_EXIT" -ne 0 ]]; then
    exit 1
fi

bold "Done."
echo "Tail logs with: $AGENTCORE_BIN logs $NAME --follow"

bold "3. Verify"
SESSION_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
PAYLOAD='{"ticket_id":"deploy-verify","raw":{"subject":"Cannot log in - MFA loop","body":"Every time I enter my MFA code it just asks me again.","sender":"alice@example.com"},"domain":"support","classification":null,"severity":null,"findings":[],"investigated":false,"draft":null,"approval":"pending","sent":false,"next":"","step_log":[]}'
"$AGENTCORE_BIN" invoke "$PAYLOAD" --agent "$NAME" --session-id "$SESSION_ID" | head -c 2000
echo
