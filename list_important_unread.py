#!/usr/bin/env python3
"""List subjects of all important+unread messages (Gmail: is:important is:unread).

Local-only utility — not deployed. Equivalent to the Gmail search query, but
implemented with labelIds since the gmail.metadata scope rejects `q=`.

Usage:
    source .venv/bin/activate
    python list_important_unread.py
"""

from __future__ import annotations

from config import load_settings
from gmail_client import _build_service, extract_header, get_message, list_messages


def main() -> None:
    settings = load_settings()
    service = _build_service(settings)

    summaries = list_messages(service, ["IMPORTANT", "UNREAD"])
    if not summaries:
        print("No important+unread messages.")
        return

    for i, summary in enumerate(summaries, start=1):
        msg = get_message(service, summary["id"])
        headers = msg.get("payload", {}).get("headers", [])
        subject = extract_header(headers, "Subject") or "(no subject)"
        sender = extract_header(headers, "From")
        date = extract_header(headers, "Date")
        print(f"{i}. {subject}")
        print(f"   From: {sender}")
        print(f"   Date: {date}")
        print()


if __name__ == "__main__":
    main()
