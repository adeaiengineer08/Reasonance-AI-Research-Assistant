# Reasonance AI Research Assistant

Project 1 — AI Research Assistant (LangGraph planner → researcher → writer).

Ticket triage (Project 2) lives in a separate repo:
https://github.com/adeaiengineer08/Reasonance-AI-ticket-triage-agent

## What's already in here

- `pyproject.toml` - pinned Python dependencies.
- `docker-compose.yml` - a local pgvector database.
- `scripts/setup_aws.sh`, `scripts/setup_gcp.sh` - guided cloud setup.
- `scripts/deploy_cloudrun.sh` - deploy to Cloud Run.
- `app/smoke.py` - smoke test.
- `app/llm.py` - model-provider abstraction.
- `data/sample-corpus/` - sample doc corpora.
- `.cursor/rules/` - house style + Project 1 rules.

## Quick start

```bash
# 1. Install deps
uv sync

# 2. Start the local vector DB
docker compose up -d postgres

# 3. Verify cloud access (one-time)
./scripts/setup_aws.sh
./scripts/setup_gcp.sh

# 4. Smoke test
uv run python -m app.smoke
```

## Common make targets

```bash
make help
make smoke
make ingest CORPUS=aws-docs
make dev
make eval
make deploy-cloudrun
```
