#!/bin/bash
# Disable the App Engine app for this project: stop cron + stop all serving versions.
# Run locally with gcloud authenticated for project gmail-important-notifier.
#
#   bash disable_gae.sh
set -euo pipefail

PROJECT="${GCP_PROJECT:-gmail-important-notifier}"
SERVICE="${GAE_SERVICE:-default}"
# App Engine app location (from prior deploys); override if needed.
LOCATION="${GCP_LOCATION:-europe-central2}"

log() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

command -v gcloud >/dev/null 2>&1 || die "gcloud not found in PATH"

gcloud config set project "$PROJECT" >/dev/null

# ── 1. Remove App Engine cron (deletes the linked Cloud Scheduler job) ──
log "Removing App Engine cron jobs (empty cron.yaml)…"
EMPTY_CRON_DIR="$(mktemp -d)"
trap 'rm -rf "$EMPTY_CRON_DIR"' EXIT
printf 'cron: []\n' > "$EMPTY_CRON_DIR/cron.yaml"
gcloud app deploy "$EMPTY_CRON_DIR/cron.yaml" --quiet

# Belt-and-suspenders: pause any leftover scheduler jobs targeting this app.
log "Pausing leftover Cloud Scheduler jobs (if any)…"
mapfile -t SCHED_JOBS < <(gcloud scheduler jobs list \
    --location="$LOCATION" \
    --format='value(name)' 2>/dev/null || true)
for job in "${SCHED_JOBS[@]:-}"; do
    [ -n "$job" ] || continue
    # Job names are locations/…/jobs/… — pause only appengine-http ones when filterable;
    # pause all in this location is acceptable for a single-app project.
    log "  pausing $job"
    gcloud scheduler jobs pause "$job" --quiet || true
done

# ── 2. Stop all versions of the service (no traffic, no instances) ──
log "Stopping all versions of service '$SERVICE'…"
mapfile -t VERSIONS < <(gcloud app versions list \
    --service="$SERVICE" \
    --format='value(version.id)' 2>/dev/null || true)

if [ "${#VERSIONS[@]}" -eq 0 ]; then
    log "  no versions found (already stopped or deleted)"
else
    for ver in "${VERSIONS[@]}"; do
        log "  stopping $SERVICE/$ver"
        gcloud app versions stop "$ver" \
            --service="$SERVICE" \
            --quiet || true
    done
fi

# ── 3. Summary ──
log "Current versions:"
gcloud app versions list --service="$SERVICE" --format='table(version.id,version.servingStatus)' || true

log "App Engine disable complete."
cat <<'EOF'

Notes:
  • Cron is gone; versions are stopped — https://gmail-important-notifier.appspot.com should 404 / not serve.
  • Re-enable later:  gcloud app deploy app.yaml cron.yaml
  • Point the Pub/Sub push subscription at your VPS before relying on push there:
      gcloud pubsub subscriptions update gmail-important-notifications-sub \
        --push-endpoint=http://<VPS>:/tasks/gmail-push
    and set PUBSUB_PUSH_AUDIENCE in .env to the same URL.
EOF
