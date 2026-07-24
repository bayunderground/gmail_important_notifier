#!/bin/bash
set -euo pipefail

gcloud config set project gmail-important-notifier

# ── One-time Pub/Sub setup (run once, not on every deploy) ──────────────
# gcloud pubsub topics create gmail-important-notifications
# gcloud pubsub topics add-iam-policy-binding gmail-important-notifications \
#   --member="serviceAccount:gmail-api-push@system.gserviceaccount.com" \
#   --role="roles/pubsub.publisher"
# gcloud pubsub subscriptions create gmail-important-notifications-sub \
#   --topic=gmail-important-notifications \
#   --push-endpoint="https://gmail-important-notifier.appspot.com/tasks/gmail-push" \
#   --push-auth-service-account="push-auth@ gmail-important-notifier.iam.gserviceaccount.com" \
#   --push-audience="https://gmail-important-notifier.appspot.com/tasks/gmail-push"
# ────────────────────────────────────────────────────────────────────────

set -a && source .env && set +a
envsubst < app.template.yaml > app.yaml
gcloud app deploy app.yaml cron.yaml
