#!/usr/bin/env python3
"""One-time local OAuth consent flow to obtain a Gmail refresh token.

Run locally only — NOT deployed. Requires an OAuth consent screen and
OAuth client ID/secret created in the GCP Console beforehand.

Usage:
    python get_refresh_token.py

The script opens a browser for Google consent, then prints the refresh
token to stdout. Paste it into .env as GMAIL_OAUTH_REFRESH_TOKEN.
"""

from __future__ import annotations

import json
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.metadata"]
CLIENT_SECRETS_FILE = "client_secret.json"


def main() -> None:
    if not os.path.exists(CLIENT_SECRETS_FILE):
        print(
            f"Error: {CLIENT_SECRETS_FILE} not found.\n"
            "Create an OAuth client ID (Desktop app type) in the GCP Console,\n"
            "download the JSON, and save it as client_secret.json in this directory.",
            file=sys.stderr,
        )
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
    creds = flow.run_local_server(port=8080)

    print("\n--- Refresh Token ---\n")
    print(f"GMAIL_OAUTH_REFRESH_TOKEN={creds.refresh_token}")
    print("\nPaste the above into .env\n")


if __name__ == "__main__":
    main()
