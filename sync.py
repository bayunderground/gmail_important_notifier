from __future__ import annotations

import logging
from datetime import datetime, timezone

from googleapiclient.errors import HttpError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from config import Settings
from db import SessionLocal
from models import NotifiedMessage, SyncState

log = logging.getLogger(__name__)


def _get_or_create_sync_state(session) -> SyncState:
    row = session.execute(select(SyncState).limit(1)).scalar_one_or_none()
    if row is None:
        row = SyncState()
        session.add(row)
        session.flush()
    return row


def _extract_header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def process_history_since(
    service,
    history_id: str,
    *,
    notify_fn=None,
    settings: Settings | None = None,
) -> int:
    """Process history records since the last known historyId.

    Args:
        service: Gmail API service instance.
        history_id: The new historyId from the Pub/Sub push.
        notify_fn: Callable(message_id, sender, subject, date) for sending notifications.
                   If None, logs a stub message instead.
        settings: Required if notify_fn is provided.

    Returns:
        Number of messages processed.
    """
    from gmail_client import get_message, history_list

    with SessionLocal() as session:
        sync_state = _get_or_create_sync_state(session)
        last_id = sync_state.last_history_id

        if last_id is None:
            log.warning("No last_history_id in sync_state; storing current as baseline")
            sync_state.last_history_id = history_id
            session.commit()
            return 0

        try:
            records = history_list(service, last_id)
        except HttpError as exc:
            if exc.resp.status == 400:
                raise
            if exc.resp.status == 404:
                log.warning(
                    "History list 404 (startHistoryId=%s stale); "
                    "re-watching to reset baseline",
                    last_id,
                )
                from gmail_client import watch as gmail_watch

                try:
                    resp = gmail_watch(service, settings)
                except Exception:
                    log.exception("Re-watch after 404 failed")
                    return 0
                expiration_ms = int(resp.get("expiration", 0))
                sync_state.watch_expiration = datetime.fromtimestamp(
                    expiration_ms / 1000, tz=timezone.utc
                )
                sync_state.last_history_id = str(resp.get("historyId", last_id))
                sync_state.updated_at = datetime.now(timezone.utc)
                session.commit()
                log.info(
                    "Re-baselined historyId to %s after stale cursor",
                    sync_state.last_history_id,
                )
                return 0
            raise
        processed = 0
        newest_history_id = int(history_id)

        for record in records:
            messages = record.get("messages", [])
            for msg_summary in messages:
                msg_id = msg_summary.get("id")
                if not msg_id:
                    continue

                label_ids = msg_summary.get("labelIds", [])
                if "IMPORTANT" not in label_ids:
                    continue

                # Claim the message — unique constraint prevents double-processing
                notified_row = NotifiedMessage(message_id=msg_id)
                try:
                    session.add(notified_row)
                    session.flush()
                except IntegrityError:
                    session.rollback()
                    existing = session.execute(
                        select(NotifiedMessage).where(
                            NotifiedMessage.message_id == msg_id
                        )
                    ).scalar_one_or_none()
                    if existing and existing.notified_at is not None:
                        log.debug("Already notified for %s, skipping", msg_id)
                    else:
                        log.debug("Message %s already claimed, skipping", msg_id)
                    continue

                # Fetch full metadata for the surviving message
                try:
                    msg_data = get_message(service, msg_id)
                except Exception:
                    log.exception("Failed to fetch message %s", msg_id)
                    continue

                headers = msg_data.get("payload", {}).get("headers", [])
                sender = _extract_header(headers, "From")
                subject = _extract_header(headers, "Subject")
                date = _extract_header(headers, "Date")

                if notify_fn:
                    try:
                        notify_fn(msg_id, sender, subject, date)
                        notified_row.notified_at = datetime.now(timezone.utc)
                        log.info("Notified: %s", subject)
                    except Exception:
                        log.exception("Notification failed for %s", msg_id)
                else:
                    log.info("Would notify: %s", subject)
                    # Stub mode — mark as notified for testing
                    notified_row.notified_at = datetime.now(timezone.utc)

                notified_row.attempted_at = datetime.now(timezone.utc)
                processed += 1

            # Track the highest historyId seen
            hist_id = record.get("id")
            if hist_id:
                newest_history_id = max(newest_history_id, int(hist_id))

        # Advance the cursor
        sync_state.last_history_id = str(newest_history_id)
        session.commit()

    log.info("Processed %d messages, advanced historyId to %s", processed, newest_history_id)
    return processed
