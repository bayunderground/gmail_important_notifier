# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

GmailImportantNotifier: a minimal Flask app on Google App Engine that watches a single Gmail inbox via the Gmail API's push notifications (`users.watch` + Cloud Pub/Sub) and sends a Telegram message whenever a new message is tagged with Gmail's own `IMPORTANT` label. No email body content is ever fetched, and no label-modifying Gmail endpoint is ever called. Single-user, single-purpose, reuses PriceMonitorBot's Telegram bot token — notifications land in the same chat as PriceMonitorBot's own messages, tagged with a `📧` prefix.

## Running Locally

```bash
source .venv/bin/activate

# Env vars loaded from .env automatically via python-dotenv
python main.py                    # starts Flask on :8080
python get_refresh_token.py       # one-time OAuth consent flow — NOT deployed, run manually and once
python test.py                    # smoke-tests Gmail API connectivity and a Telegram send
```

Two HTTP-triggered paths, neither meant to be hit manually in normal operation:
- `POST /tasks/gmail-push` — the Pub/Sub push endpoint. Authenticated by verifying the OIDC token Pub/Sub attaches to every push request (audience + issuer + service account email), not by an `X-Appengine-Cron`-style header — that header is specific to App Engine's own cron scheduler and doesn't apply to Pub/Sub push. Verification is skipped locally only behind the same `_ON_APP_ENGINE` gate the reference project uses for its cron check (a warning is logged when skipped).
- `GET|POST /tasks/renew` — the daily cron handler. Identical `X-Appengine-Cron: true` + `_ON_APP_ENGINE` check to the reference project's `/tasks/fetch`.

## Deploying

One-time setup (not part of `depl.sh`, done once before the first deploy):
1. Create the Pub/Sub topic, grant `gmail-api-push@system.gserviceaccount.com` publish rights on it, create the push subscription (OIDC-authenticated, pointed at `/tasks/gmail-push`) — documented as a manual `gcloud` block, same category as the reference project's one-off `init-job` scheduler line, not re-run on every deploy.
2. Run `python get_refresh_token.py` locally to get a Gmail OAuth refresh token; paste it into `.env`.

Routine deploy:
```bash
bash depl.sh
```
Loads env vars from `.env`, generates `app.yaml` from `app.template.yaml`, then `gcloud app deploy app.yaml cron.yaml`. `cron.yaml` carries the `/tasks/renew` schedule (daily) — Google's own guidance is to renew the watch about that often even though the hard expiration is 7 days, so daily leaves comfortable margin.

## Architecture

**Entry points:**
- `main.py` — Flask routes: `GET /` (health check), `POST /tasks/gmail-push` (Pub/Sub push handler), `GET|POST /tasks/renew` (cron handler)
- `sync.py` — `process_history_since()`, the push-triggered history sync, called by `/tasks/gmail-push`
- `renew.py` — `renew_watch_if_needed()` and `retry_pending_notifications()`, both called by `/tasks/renew`
- `get_refresh_token.py` — one-time local OAuth script, excluded from deploy via `.gcloudignore`

**Data flow — new mail (push path):**
1. Gmail mailbox changes → Pub/Sub delivers `{emailAddress, historyId}` to `POST /tasks/gmail-push`
2. OIDC token verified before anything else runs
3. Load `last_history_id` from the single-row `sync_state` table
4. `users.history.list(startHistoryId=last_history_id, labelId="IMPORTANT")`, paging via `nextPageToken`
5. `history.list` returns each affected message's current `labelIds` inline — no extra API call needed just to check for `IMPORTANT`; anything without it is skipped without fetching anything further
6. For each surviving message id: insert a `NotifiedMessage` row (`message_id` unique, `notified_at=NULL`) to claim it — an `IntegrityError` means it's already claimed by a redelivered Pub/Sub push or an overlapping history page; reload and skip
7. `messages.get(id, format=metadata, metadataHeaders=[From,Subject,Date])`, then send the Telegram message
8. Success → set `notified_at`. Failure → leave `notified_at=NULL`; this path does not retry — retry is `/tasks/renew`'s job
9. `sync_state.last_history_id` advances to the newest `historyId` in the page once the batch is done, regardless of individual send failures

**Data flow — renewal + retry sweep (cron path, `/tasks/renew`, daily):**
1. `X-Appengine-Cron: true` check
2. If `sync_state.watch_expiration` is inside its safety window, call `users.watch` again; update `watch_expiration` and `last_history_id` from the response
3. `NotifiedMessage` rows where `notified_at IS NULL AND attempted_at < now - retry_after`: resend via `messages.get(id, format=metadata)` directly — no `history.list` involved, since the id is already known
4. Same code path handles a `history.list` 404 from the push flow (stale `last_history_id`): re-`watch`, store its `historyId` as the new baseline. Anything that changed between the invalidated cursor and the new baseline can't be recovered — there's no diff to replay after a re-baseline

**Idempotency:**
- `message_id` is the `item_key` equivalent; unique constraint on `NotifiedMessage.message_id`
- Concurrent-insert races (overlapping history pages, at-least-once Pub/Sub redelivery) handled by catching `IntegrityError` and reloading — same pattern as the reference project's `ProcessedItem`
- Difference from the reference project: a pending row here is *not* naturally re-offered by the next sync, since historyId only moves forward. That's why retry is a dedicated `messages.get(id)` sweep in the renewal job rather than "wait for the next cycle to see it again"

**Database:**
- `sync_state` — single row: `last_history_id`, `watch_expiration`, `updated_at`
- `notified_messages` — one row per message that carried `IMPORTANT` at processing time; `notified_at=NULL` = pending/failed, set = sent
- Neon PostgreSQL, same setup as the reference project
- `db.py` — identical `pool_pre_ping=True` engine config, same reasoning (Neon drops idle connections)

**Gmail API:** `gmail.metadata` OAuth scope — narrower than `gmail.readonly`, and it also makes the API itself reject `format=full`/`raw`, not just this codebase's conventions. Only `users.watch`, `users.history.list`, `users.messages.get` are called anywhere — no `.modify` endpoint appears in the codebase, including error paths.

**Telegram:** reuses PriceMonitorBot's bot, via its own `TELEGRAM_BOT_TOKEN` env var (not shared or synced with PriceMonitorBot's copy — two independently deployed codebases, two copies of the same token). Posts to the same `TELEGRAM_CHAT_ID` as PriceMonitorBot, `📧` prefix on every message.

**Configuration** (`config.py`): all values from env vars — `DATABASE_URL`, `GMAIL_OAUTH_CLIENT_ID`, `GMAIL_OAUTH_CLIENT_SECRET`, `GMAIL_OAUTH_REFRESH_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `PUBSUB_TOPIC_NAME`, `PUBSUB_PUSH_AUDIENCE`; optional tuning vars (`NOTIFICATION_RETRY_AFTER_SECONDS`, `WATCH_RENEWAL_SAFETY_WINDOW_SECONDS`) documented in `config.py`.
