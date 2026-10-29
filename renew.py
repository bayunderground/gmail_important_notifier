from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from config import Settings
from db import SessionLocal
from gmail_client import extract_header, get_message, watch
from models import NotifiedMessage, SyncState
from telegram_client import format_notification, send_message

log = logging.getLogger(__name__)


def _get_sync_state(session) -> SyncState | None:
    return session.execute(select(SyncState).limit(1)).scalar_one_or_none()


def _as_utc(dt: datetime | None) -> datetime | None:
    """Coerce a DB datetime to aware UTC (legacy rows may be naive)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def renew_watch_if_needed(service, settings: Settings) -> None:
    """Re-watch if the current expiration is inside the safety window."""
    with SessionLocal() as session:
        sync_state = _get_sync_state(session)
        if sync_state is None:
            log.warning("No sync_state row; cannot renew")
            return

        now = datetime.now(timezone.utc)
        safety_window = timedelta(seconds=settings.watch_renewal_safety_window_seconds)
        expiration = _as_utc(sync_state.watch_expiration)

        if expiration and expiration - now > safety_window:
            log.info(
                "Watch still valid until %s, skipping renewal",
                expiration,
            )
            return

        log.info("Renewing Gmail watch...")
        try:
            resp = watch(service, settings)
        except Exception:
            log.exception("Failed to renew watch")
            return

        # Parse the expiration (milliseconds since epoch)
        expiration_ms = int(resp.get("expiration", 0))
        sync_state.watch_expiration = datetime.fromtimestamp(
            expiration_ms / 1000, tz=timezone.utc
        )
        sync_state.last_history_id = str(resp.get("historyId", sync_state.last_history_id))
        sync_state.updated_at = now
        session.commit()
        log.info("Watch renewed, expires %s", sync_state.watch_expiration)


def retry_pending_notifications(service, settings: Settings) -> None:
    """Sweep NotifiedMessage rows that haven't been sent yet."""
    with SessionLocal() as session:
        pending = session.execute(
            select(NotifiedMessage).where(
                NotifiedMessage.notified_at.is_(None),
                NotifiedMessage.attempted_at.isnot(None),
                NotifiedMessage.attempted_at
                < datetime.now(timezone.utc)
                - timedelta(seconds=settings.notification_retry_after_seconds),
            )
        ).scalars().all()

        if not pending:
            return

        log.info("Retrying %d pending notifications", len(pending))

        for row in pending:
            try:
                msg_data = get_message(service, row.message_id)
                headers = msg_data.get("payload", {}).get("headers", [])

                sender = extract_header(headers, "From")
                subject = extract_header(headers, "Subject")
                date = extract_header(headers, "Date")

                text = format_notification(sender, subject, date)
                send_message(settings, text)

                row.notified_at = datetime.now(timezone.utc)
                log.info("Retry succeeded for %s", row.message_id)
            except Exception:
                log.exception("Retry failed for %s", row.message_id)

        session.commit()
