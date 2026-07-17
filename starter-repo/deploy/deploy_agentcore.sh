#!/usr/bin/env bash
set -euo pipefail

if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

AGENTCORE_BIN="agentcore"
if ! command -v agentcore >/dev/null 2>&1; then
    AGENTCORE_BIN=".venv/bin/agentcore"
fi

"$AGENTCORE_BIN" configure \
    --name monk_ticket_triage \
    --entrypoint deploy/agentcore_entrypoint.py \
    --runtime PYTHON_3_11 \
    --deployment-type direct_code_deploy \
    --requirements-file deploy/requirements.txt \
    --region "${AWS_REGION:-us-east-1}" \
    --non-interactive \
    --idle-timeout 600 \
    --max-lifetime 28800
ENV_ARGS=()
if [[ -n "${POSTGRES_DSN:-}" ]]; then ENV_ARGS+=(--env "POSTGRES_DSN=$POSTGRES_DSN"); fi
if [[ -n "${MONK_MODEL:-}" ]]; then ENV_ARGS+=(--env "MONK_MODEL=$MONK_MODEL"); fi
if [[ -n "${MONK_EMBEDDINGS:-}" ]]; then ENV_ARGS+=(--env "MONK_EMBEDDINGS=$MONK_EMBEDDINGS"); fi
ENV_ARGS+=(--env "LANGCHAIN_TRACING_V2=false")
"$AGENTCORE_BIN" launch --agent monk_ticket_triage --auto-update-on-conflict "${ENV_ARGS[@]}"
echo "Done. $AGENTCORE_BIN logs monk_ticket_triage --follow"
