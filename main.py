from __future__ import annotations

import logging
import os

from flask import Flask, abort, request

from config import load_settings
from db import SessionLocal
from gmail_client import _build_service

app = Flask(__name__)

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

settings = load_settings()
service = _build_service(settings)

_ON_APP_ENGINE = settings.on_app_engine


def _verify_pubsub_token(token: str | None) -> bool:
    """Verify the OIDC token Pub/Sub attaches to push requests."""
    if not token:
        return False
    try:
        import google.oauth2.id_token
        import google.auth.transport.requests

        claims = google.oauth2.id_token.verify_oauth2_token(
            token,
            google.auth.transport.requests.Request(),
            audience=settings.pubsub_push_audience,
        )
        expected_issuer = "https://accounts.google.com"
        expected_sa = "gmail-api-push@system.gserviceaccount.com"
        return (
            claims.get("iss") == expected_issuer
            and claims.get("azp") == expected_sa
        )
    except Exception:
        logging.exception("OIDC token verification failed")
        return False


@app.route("/")
def health():
    return "ok"


@app.route("/tasks/gmail-push", methods=["POST"])
def gmail_push():
    # Verify OIDC token from Pub/Sub
    if _ON_APP_ENGINE:
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else None
        if not _verify_pubsub_token(token):
            abort(403, "Invalid or missing OIDC token")
    else:
        logging.warning("OIDC verification skipped (not on App Engine)")

    envelope = request.get_json(silent=True)
    if not envelope:
        abort(400, "No JSON body")

    message = envelope.get("message")
    if not message:
        abort(400, "No message in envelope")

    data = message.get("data")
    if not data:
        abort(400, "No data in message")

    # Pub/Sub data is base64-encoded
    import base64, json

    try:
        payload = json.loads(base64.b64decode(data).decode())
    except Exception:
        abort(400, "Invalid base64/JSON in message data")

    history_id = payload.get("historyId")
    if not history_id:
        abort(400, "No historyId in payload")

    from sync import process_history_since

    count = process_history_since(service, history_id)
    return {"status": "ok", "processed": count}


@app.route("/tasks/renew", methods=["GET", "POST"])
def renew():
    if _ON_APP_ENGINE:
        if request.headers.get("X-Appengine-Cron") != "true":
            abort(403, "X-Appengine-Cron header required")
    else:
        logging.warning("Cron header check skipped (not on App Engine)")

    from renew import renew_watch_if_needed, retry_pending_notifications

    renew_watch_if_needed(service, settings)
    retry_pending_notifications(service)
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
