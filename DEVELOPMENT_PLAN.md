# DEVELOPMENT_PLAN.md

Staged build order. Nothing here gets implemented until this plan is approved.

## Stage 1 — GCP + Pub/Sub setup (manual, one-time)

- Enable the Gmail API and Pub/Sub API on the GCP project.
- Create the Pub/Sub topic; grant `gmail-api-push@system.gserviceaccount.com` the `roles/pubsub.publisher` role on it (this is the fixed system account Gmail itself publishes as — separate from any service account we create).
- Create a dedicated service account for **push authentication** (distinct purpose from the account above): this one generates the OIDC token Pub/Sub attaches to every push request to `/tasks/gmail-push`.
- Create the push subscription: topic → `/tasks/gmail-push`, OIDC auth configured with that service account and an `audience` matching the endpoint URL. App Engine URLs are deterministic from the project ID, so the audience can be set correctly before the first real deploy — no chicken-and-egg problem, just needs to be gotten right once.
- All of the above as a documented `gcloud` block — same category as the reference project's one-off `init-job` scheduler line in `depl.sh`: written down, run once, not re-executed by routine deploys.
- **Output needed downstream:** topic name, subscription name, push-auth service account email, audience URL → become `PUBSUB_TOPIC_NAME` / `PUBSUB_PUSH_AUDIENCE` env vars.

## Stage 2 — OAuth script

- `get_refresh_token.py`: local, installed-app OAuth consent flow, `gmail.metadata` scope, requests offline access, prints a refresh token to paste into `.env`.
- Requires an OAuth consent screen + OAuth client ID/secret created in the GCP console first (this is OAuth-specific GCP config, separate from Stage 1's Pub/Sub config).
- Not deployed — excluded via `.gcloudignore`, same treatment as the reference project's `test.py`/`.venv`.
- **Output needed downstream:** `GMAIL_OAUTH_CLIENT_ID`, `GMAIL_OAUTH_CLIENT_SECRET`, `GMAIL_OAUTH_REFRESH_TOKEN`.

## Stage 3 — Postgres schema/models

- `models.py`: `SyncState` (single row — `last_history_id`, `watch_expiration`, `updated_at`), `NotifiedMessage` (`message_id` unique, `attempted_at`, `notified_at` nullable).
- `db_schema.sql`, mirroring the reference project's reference-schema file.
- `db.py`: identical `pool_pre_ping=True` engine setup.
- `config.py`: `Settings` dataclass, all env vars from CLAUDE.md's Configuration section.
- Decision: no separate seed script for the single `sync_state` row — code does get-or-create on first access (simpler than a migration-adjacent seed step for a single-row table).

## Stage 4 — Watch + history sync logic

- `gmail_client.py`: wraps `users.watch`, `users.history.list`, `users.messages.get`.
- `sync.py`: `process_history_since()` — load cursor, page through `history.list(startHistoryId=..., labelId="IMPORTANT")`, check inline `labelIds` per record, claim `NotifiedMessage` rows, fetch metadata for survivors. Telegram send itself is stubbed (logs "would notify: <subject>") — kept decoupled from Stage 5 so this stage is independently testable.
- `/tasks/gmail-push` route in `main.py`, OIDC verification wired in for real (Stage 1's subscription already exists by this point).
- **Verify precisely during this stage, don't assume from the plan alone:**
  - Exact `historyTypes` values to request — needs to cover both a brand-new message arriving already-`IMPORTANT` (`messageAdded`) and an existing message getting `IMPORTANT` applied later, e.g. by Gmail's own classifier after initial delivery (`labelAdded`). Missing the second case would silently under-notify.
  - Confirm `history.list`'s inline `labelIds` are present on `labelsAdded`-type records the same way they are on `messagesAdded` — the mechanism is documented for the general case but worth a direct check against a real response before relying on it to skip a `messages.get` call.
  - The `users.watch`-level label filter (`labelFilterAction` vs. a possibly-renamed `labelFilterBehavior`) is a nice-to-have on top of the `history.list`-level filter, not a dependency — resolve the current field name against the live API docs when this stage starts, and skip it entirely rather than guess if it's still ambiguous. The `history.list(labelId=...)` filter and the app-level label check both stay regardless.

## Stage 5 — Telegram send

- `telegram_client.py`: thin `sendMessage` wrapper, `📧` prefix, formats sender/subject/date only.
- Wire into `sync.py`'s claim-then-notify loop, replacing Stage 4's stub.
- Two distinct retry layers, not one — worth keeping separate in the code, not conflating:
  1. **In-request retry**: a few bounded attempts with backoff on the Telegram call itself, same shape as the reference project's `retry_call` for Instapaper.
  2. **Cross-request retry** (Stage 6): anything still unsent after (1) exhausts becomes a job for the daily renewal sweep.
- `notified_at` set only on confirmed success; left `NULL` otherwise, matching the reference project's `processed_at` semantics.

## Stage 6 — Renewal job

- `renew.py`: `renew_watch_if_needed()` (re-`watch` inside the safety window, update `sync_state`), `retry_pending_notifications()` (sweep `NotifiedMessage` rows past the retry window, resend via `messages.get(id)` directly — no `history.list`).
- Same function handles the `history.list` 404 fallback path from Stage 4: catch it there, re-`watch`, store the fresh `historyId` as the new baseline.
- `/tasks/renew` route, `X-Appengine-Cron: true` check identical to the reference project's `/tasks/fetch`.
- `cron.yaml` entry, daily.
- **Verify precisely during this stage:** the exact exception/status shape the Gmail client library raises for a 404 on `history.list` (e.g. `HttpError` with `.resp.status`, depending on which client library gets used) — needs to be caught specifically, not swallowed by a broad `except Exception`.

## Stage 7 — Deploy scripts

- `app.template.yaml`: add the new env vars listed in CLAUDE.md.
- `depl.sh`: same `envsubst` + `gcloud app deploy app.yaml cron.yaml` pattern as the reference project. Stage 1's one-time GCP block stays inline but clearly delimited as "run once," matching how the reference project keeps its `init-job` line inline rather than in a separate script.
- `test.py`: end-to-end smoke test — Gmail API connectivity (a lightweight call, not a full sync) and a real Telegram send to confirm the token/chat_id combination works before relying on the cron/push paths.

---

Each stage produces working, reviewable code before the next one starts — nothing downstream is blocked on guessing at an earlier stage's output. Say go-ahead (all stages, or start with Stage 1 and check in as we go) and I'll start implementing.
