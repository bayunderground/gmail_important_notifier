from __future__ import annotations

import logging
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from config import Settings

log = logging.getLogger(__name__)


def _build_service(settings: Settings):
    creds = Credentials(
        token=None,
        refresh_token=settings.gmail_oauth_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.gmail_oauth_client_id,
        client_secret=settings.gmail_oauth_client_secret,
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def watch(service, settings: Settings) -> dict:
    """Call users.watch. Returns the API response (historyId, expiration)."""
    topic_name = f"projects/{settings.pubsub_project_id}/topics/{settings.pubsub_topic_name}"
    resp = service.users().watch(
        userId="me",
        body={
            "topicName": topic_name,
            "labelIds": ["IMPORTANT"],
        },
    ).execute()
    log.info("users.watch response: historyId=%s, expiration=%s",
             resp.get("historyId"), resp.get("expiration"))
    return resp


def history_list(service, start_history_id: str) -> list[dict]:
    """Page through users.history.list, returning all history records.

    Filters to messages with the IMPORTANT label at the history.list level.
    The caller should still verify labelIds on each record inline, since the
    label filter is a server-side hint and the record itself is the ground truth.
    """
    all_records = []
    page_token = None
    while True:
        kwargs = {
            "userId": "me",
            "startHistoryId": start_history_id,
            "labelId": "IMPORTANT",
            "historyTypes": ["messageAdded", "labelAdded"],
        }
        if page_token:
            kwargs["pageToken"] = page_token

        resp = service.users().history().list(**kwargs).execute()
        records = resp.get("history", [])
        all_records.extend(records)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return all_records


def get_message(service, message_id: str) -> dict:
    """Call users.messages.get with metadata format."""
    return service.users().messages().get(
        userId="me",
        id=message_id,
        format="metadata",
        metadataHeaders=["From", "Subject", "Date"],
    ).execute()


def list_messages(
    service, label_ids: list[str], *, max_results: int = 100
) -> list[dict]:
    """Page through users.messages.list, returning all message summaries.

    Multiple label_ids are AND-ed by the API (equivalent to Gmail search
    combining terms with spaces). The gmail.metadata scope rejects the
    `q` parameter, so label filtering must use labelIds.
    """
    all_messages = []
    page_token = None
    while True:
        kwargs = {
            "userId": "me",
            "labelIds": label_ids,
            "maxResults": max_results,
        }
        if page_token:
            kwargs["pageToken"] = page_token

        resp = service.users().messages().list(**kwargs).execute()
        all_messages.extend(resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return all_messages


def extract_header(headers: list[dict], name: str) -> str:
    """Return a header value by case-insensitive name, or empty string."""
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""
