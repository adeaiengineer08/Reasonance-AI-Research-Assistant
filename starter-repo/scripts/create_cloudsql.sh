#!/usr/bin/env bash
# Monk Technologies - provision a Cloud SQL PostgreSQL + pgvector instance.
# Idempotent: safe to re-run. Pass --delete to tear down.
#
# Env-var overrides:
#   CLOUDSQL_INSTANCE  (default: monk-postgres)
#   REGION             (default: asia-south1)
#   DB_NAME            (default: monk)
#   DB_PASS            (default: random)

set -euo pipefail

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "  \033[32mok\033[0m  %s\n" "$*"; }
warn() { printf "  \033[33m!!\033[0m  %s\n" "$*"; }
err()  { printf "  \033[31mERR\033[0m %s\n" "$*"; exit 1; }

INSTANCE="${CLOUDSQL_INSTANCE:-monk-postgres}"
REGION="${REGION:-asia-south1}"
DB_NAME="${DB_NAME:-monk}"
DB_USER="postgres"
DB_PASS="${DB_PASS:-$(openssl rand -base64 18)}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INIT_SQL="$SCRIPT_DIR/postgres-init.sql"
PROJECT="$(gcloud config get-value project 2>/dev/null)"

if [[ -z "$PROJECT" || "$PROJECT" == "(unset)" ]]; then
    err "No GCP project set. Run: gcloud config set project YOUR_PROJECT_ID"
fi

CONN_NAME="$PROJECT:$REGION:$INSTANCE"

# ── --delete flag ────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--delete" ]]; then
    bold "Deleting Cloud SQL instance: $INSTANCE"
    if gcloud sql instances describe "$INSTANCE" --project="$PROJECT" >/dev/null 2>&1; then
        gcloud sql instances delete "$INSTANCE" --project="$PROJECT" --quiet
        ok "Instance $INSTANCE deleted"
    else
        ok "Instance $INSTANCE does not exist — nothing to delete"
    fi
    exit 0
fi

bold "Monk Technologies - Cloud SQL PostgreSQL setup"
echo "  project  = $PROJECT"
echo "  instance = $INSTANCE"
echo "  region   = $REGION"
echo "  database = $DB_NAME"
echo

# ── Step 0: Enable Cloud SQL Admin API ───────────────────────────────────────
bold "Step 0: Cloud SQL Admin API"
if gcloud services list --enabled --format='value(name)' --project="$PROJECT" \
        | grep -q '^sqladmin.googleapis.com$'; then
    ok "sqladmin.googleapis.com already enabled"
else
    warn "Enabling sqladmin.googleapis.com (may take ~30s)..."
    gcloud services enable sqladmin.googleapis.com --project="$PROJECT"
    ok "sqladmin.googleapis.com enabled"
fi
echo

# ── Step 1: Create instance (or reset password) ─────────────────────────────
bold "Step 1: Cloud SQL instance"
if gcloud sql instances describe "$INSTANCE" --project="$PROJECT" >/dev/null 2>&1; then
    ok "Instance $INSTANCE already exists — resetting postgres password"
    gcloud sql users set-password "$DB_USER" \
        --instance="$INSTANCE" --project="$PROJECT" \
        --password="$DB_PASS" --quiet
else
    warn "Creating db-f1-micro Postgres 15 instance (takes 3-5 min)..."
    gcloud sql instances create "$INSTANCE" \
        --project="$PROJECT" \
        --region="$REGION" \
        --database-version=POSTGRES_15 \
        --tier=db-f1-micro \
        --storage-size=10GB \
        --storage-auto-increase \
        --root-password="$DB_PASS" \
        --quiet
    ok "Instance $INSTANCE created"
fi
echo

# ── Step 2: Create database ─────────────────────────────────────────────────
bold "Step 2: Database"
EXISTING_DBS=$(gcloud sql databases list --instance="$INSTANCE" --project="$PROJECT" \
    --format='value(name)' 2>/dev/null || true)
if echo "$EXISTING_DBS" | grep -qx "$DB_NAME"; then
    ok "Database $DB_NAME already exists"
else
    gcloud sql databases create "$DB_NAME" \
        --instance="$INSTANCE" --project="$PROJECT" --quiet
    ok "Database $DB_NAME created"
fi
echo

# ── Step 3: Run init SQL (pgvector + tables) ─────────────────────────────────
bold "Step 3: Initialize schema (pgvector + tables)"
if [[ ! -f "$INIT_SQL" ]]; then
    err "Init SQL not found at $INIT_SQL"
fi

MY_IP="$(curl -4 -s --max-time 10 ifconfig.me)"
if [[ -z "$MY_IP" ]]; then
    err "Could not determine public IPv4 address"
fi
ok "Current IP: $MY_IP"

INSTANCE_IP="$(gcloud sql instances describe "$INSTANCE" --project="$PROJECT" \
    --format='value(ipAddresses[0].ipAddress)' 2>/dev/null || true)"

# Temporarily authorise this machine's IP
warn "Authorising $MY_IP for temporary access..."
gcloud sql instances patch "$INSTANCE" --project="$PROJECT" \
    --authorized-networks="$MY_IP/32" --quiet 2>/dev/null || true

cleanup_ip() {
    warn "Removing temporary IP authorisation..."
    gcloud sql instances patch "$INSTANCE" --project="$PROJECT" \
        --clear-authorized-networks --quiet 2>/dev/null || true
}
trap cleanup_ip EXIT

sleep 3

if command -v psql >/dev/null 2>&1 && [[ -n "$INSTANCE_IP" ]]; then
    ok "Connecting via psql to $INSTANCE_IP..."
    PGPASSWORD="$DB_PASS" psql \
        -h "$INSTANCE_IP" -U "$DB_USER" -d "$DB_NAME" \
        -f "$INIT_SQL" --quiet
    ok "Schema initialised via psql"
else
    warn "psql not found or no public IP — falling back to gcloud sql connect"
    gcloud sql connect "$INSTANCE" --project="$PROJECT" \
        --user="$DB_USER" --database="$DB_NAME" --quiet \
        < "$INIT_SQL"
    ok "Schema initialised via gcloud sql connect"
fi
echo

# ── Summary ──────────────────────────────────────────────────────────────────
bold "Done. Add these to your .env:"
echo
echo "  # Cloud SQL socket DSN (for Cloud Run / App Engine)"
echo "  POSTGRES_DSN=postgresql://$DB_USER:$DB_PASS@/$DB_NAME?host=/cloudsql/$CONN_NAME"
echo
echo "  # Direct-connect DSN (for local debugging via public IP)"
echo "  POSTGRES_DSN=postgresql://$DB_USER:$DB_PASS@$INSTANCE_IP:5432/$DB_NAME"
echo
echo "  # Instance connection name (for --add-cloudsql-instances)"
echo "  CLOUDSQL_CONNECTION_NAME=$CONN_NAME"
echo
