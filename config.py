from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

_ON_APP_ENGINE = os.environ.get("GAE_ENV", "").startswith("standard")


@dataclass(frozen=True)
class Settings:
    database_url: str

    gmail_oauth_client_id: str
    gmail_oauth_client_secret: str
    gmail_oauth_refresh_token: str

    telegram_bot_token: str
    telegram_chat_id: str

    pubsub_topic_name: str
    pubsub_push_audience: str

    notification_retry_after_seconds: int = 300
    watch_renewal_safety_window_seconds: int = 86400

    @property
    def on_app_engine(self) -> bool:
        return _ON_APP_ENGINE


def load_settings() -> Settings:
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        gmail_oauth_client_id=os.environ["GMAIL_OAUTH_CLIENT_ID"],
        gmail_oauth_client_secret=os.environ["GMAIL_OAUTH_CLIENT_SECRET"],
        gmail_oauth_refresh_token=os.environ["GMAIL_OAUTH_REFRESH_TOKEN"],
        telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        telegram_chat_id=os.environ["TELEGRAM_CHAT_ID"],
        pubsub_topic_name=os.environ["PUBSUB_TOPIC_NAME"],
        pubsub_push_audience=os.environ["PUBSUB_PUSH_AUDIENCE"],
        notification_retry_after_seconds=int(
            os.environ.get("NOTIFICATION_RETRY_AFTER_SECONDS", "300")
        ),
        watch_renewal_safety_window_seconds=int(
            os.environ.get("WATCH_RENEWAL_SAFETY_WINDOW_SECONDS", "86400")
        ),
    )
