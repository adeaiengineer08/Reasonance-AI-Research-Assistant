#!/usr/bin/env bash
# Monk Technologies — deploy Research Assistant to Google Cloud Run.
# Idempotent: safe to re-run at any time.

set -euo pipefail

# ── Helpers ──────────────────────────────────────────────────────────────────
bold() { printf "\n\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m✔\033[0m %s\n" "$*"; }
skip() { printf "  \033[33m⊘\033[0m %s\n" "$*"; }

# ── Project / defaults ───────────────────────────────────────────────────────
PROJECT=$(gcloud config get-value project 2>/dev/null || true)
if [[ -z "$PROJECT" || "$PROJECT" == "(unset)" ]]; then
    echo "ERROR: No GCP project configured. Run:  gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

SERVICE="${SERVICE:-monk-research-assistant}"
REGION="${REGION:-asia-south1}"
INSTANCE="${CLOUDSQL_INSTANCE:-monk-postgres}"
CONNECTION_NAME="${PROJECT}:${REGION}:${INSTANCE}"

bold "Monk Technologies — deploy $SERVICE to Cloud Run"
echo "  project=$PROJECT  region=$REGION  sql=$CONNECTION_NAME"

# ── Load .env (line-by-line, source-safe) ────────────────────────────────────
if [[ -f .env ]]; then
    while IFS= read -r line; do
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$line" || ! "$line" == *=* ]] && continue
        key="${line%%=*}"
        value="${line#*=}"
        export "$key=$value"
    done < .env
    ok "loaded .env"
fi

# ── Step 1 — Enable APIs ────────────────────────────────────────────────────
bold "1. Enable required APIs"
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    secretmanager.googleapis.com \
    sqladmin.googleapis.com \
    aiplatform.googleapis.com \
    --project "$PROJECT" --quiet
ok "APIs enabled"

# ── Step 2 — Push secrets ───────────────────────────────────────────────────
push_secret() {
    local name="$1" value="$2"
    if [[ -z "$value" ]]; then
        echo "ERROR: $name value is empty. Set the matching variable in .env and re-run."
        exit 1
    fi
    if gcloud secrets describe "$name" --project "$PROJECT" &>/dev/null; then
        skip "secret $name already exists"
    else
        printf "%s" "$value" | gcloud secrets create "$name" \
            --replication-policy=automatic --data-file=- --project "$PROJECT" --quiet
        ok "created secret $name"
    fi
}

bold "2. Create secrets from .env"
push_secret monk-postgres-dsn "${POSTGRES_DSN:-}"
push_secret monk-tavily       "${TAVILY_API_KEY:-}"
push_secret monk-langsmith    "${LANGSMITH_API_KEY:-}"

# ── Step 3 — IAM bindings ───────────────────────────────────────────────────
bold "3. Grant IAM roles to default Compute Engine SA"
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for secret in monk-postgres-dsn monk-tavily monk-langsmith; do
    gcloud secrets add-iam-policy-binding "$secret" \
        --member="serviceAccount:${SA}" \
        --role="roles/secretmanager.secretAccessor" \
        --project "$PROJECT" &>/dev/null || true
done
ok "secretmanager.secretAccessor on secrets"

for role in roles/storage.objectViewer roles/cloudbuild.builds.builder \
            roles/artifactregistry.writer roles/aiplatform.user; do
    gcloud projects add-iam-policy-binding "$PROJECT" \
        --member="serviceAccount:${SA}" \
        --role="$role" &>/dev/null || true
done
ok "project-level roles granted"

# ── Step 4 — Deploy to Cloud Run ────────────────────────────────────────────
bold "4. Deploy $SERVICE"
gcloud run deploy "$SERVICE" \
    --source . \
    --project "$PROJECT" \
    --region "$REGION" \
    --add-cloudsql-instances "$CONNECTION_NAME" \
    --set-env-vars "MONK_MODEL=google_vertexai:gemini-2.5-pro,MONK_EMBEDDINGS=google_vertexai:text-embedding-005,LANGSMITH_PROJECT=$SERVICE,LANGSMITH_TRACING=true,GCP_PROJECT=$PROJECT,GCP_LOCATION=us-central1" \
    --set-secrets "POSTGRES_DSN=monk-postgres-dsn:latest,TAVILY_API_KEY=monk-tavily:latest,LANGSMITH_API_KEY=monk-langsmith:latest" \
    --memory 1Gi \
    --cpu 1 \
    --timeout 600 \
    --concurrency 4 \
    --allow-unauthenticated
echo

URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" --format='value(status.url)')
bold "Deployed!"
echo "  $URL"
