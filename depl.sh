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

python -c "
from dotenv import dotenv_values
vals = dotenv_values('.env')
lines = ['runtime: python311', '', 'entrypoint: gunicorn -b :\$PORT main:app', '', 'env_variables:']
for key in ['DATABASE_URL','GMAIL_OAUTH_CLIENT_ID','GMAIL_OAUTH_CLIENT_SECRET',
            'GMAIL_OAUTH_REFRESH_TOKEN','TELEGRAM_BOT_TOKEN','TELEGRAM_CHAT_ID',
            'PUBSUB_PROJECT_ID','PUBSUB_TOPIC_NAME','PUBSUB_PUSH_AUDIENCE',
            'NOTIFICATION_RETRY_AFTER_SECONDS','WATCH_RENEWAL_SAFETY_WINDOW_SECONDS','LOG_LEVEL']:
    val = vals.get(key, '')
    lines.append(f'  {key}: \"{val}\"')
with open('app.yaml', 'w') as f:
    f.write('\n'.join(lines) + '\n')
"
gcloud app deploy app.yaml cron.yaml
