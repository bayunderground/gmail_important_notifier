from __future__ import annotations

import logging
import time

import requests

from config import Settings

log = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_message(settings: Settings, message: str, retries: int = 3, backoff: float = 1.0) -> None:
    """Send a Telegram message with retry + exponential backoff.

    Raises the last exception if all retries fail.
    """
    url = _TELEGRAM_API.format(token=settings.telegram_bot_token)
    payload = {"chat_id": settings.telegram_chat_id, "text": message, "parse_mode": "HTML"}

    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            result = resp.json()
            if not result.get("ok"):
                raise RuntimeError(f"Telegram API error: {result}")
            return
        except Exception as exc:
            last_exc = exc
            log.warning("Telegram send attempt %d/%d failed: %s", attempt, retries, exc)
            if attempt < retries:
                time.sleep(backoff * (2 ** (attempt - 1)))

    raise last_exc


def format_notification(sender: str, subject: str, date: str) -> str:
    """Format an email notification with the 📧 prefix."""
    parts = []
    if sender:
        parts.append(f"From: {sender}")
    if subject:
        parts.append(f"Subject: {subject}")
    if date:
        parts.append(f"Date: {date}")
    body = "\n".join(parts) or "(no details)"
    return f"📧 New important email\n\n{body}"
