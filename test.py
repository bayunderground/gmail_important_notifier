#!/usr/bin/env python3
"""End-to-end smoke test.

Verifies:
1. Gmail API connectivity (users.getProfile)
2. Telegram bot connectivity (getMe)
3. Telegram send (sends a test message)

Usage:
    source .venv/bin/activate
    python test.py
"""

from __future__ import annotations

import sys

from config import load_settings


def test_gmail(settings):
    print("Testing Gmail API connectivity...", end=" ")
    from gmail_client import _build_service

    service = _build_service(settings)
    profile = service.users().getProfile(userId="me").execute()
    print(f"OK — {profile.get('emailAddress')}")


def test_telegram_get_me(settings):
    print("Testing Telegram bot...", end=" ")
    import requests

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getMe"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("ok"):
        bot = data["result"]
        print(f"OK — @{bot.get('username')}")
    else:
        print(f"FAIL — {data}")
        sys.exit(1)


def test_telegram_send(settings):
    print("Sending test message...", end=" ")
    from telegram_client import send_message

    send_message(settings, "📧 GmailImportantNotifier test — if you see this, it works!")
    print("OK")


def main():
    settings = load_settings()

    test_gmail(settings)
    test_telegram_get_me(settings)
    test_telegram_send(settings)

    print("\nAll tests passed.")


if __name__ == "__main__":
    main()
