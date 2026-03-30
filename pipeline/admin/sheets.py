from __future__ import annotations

import json
import logging
import os

from pipeline.models import BriefingNode

logger = logging.getLogger(__name__)

SHEET_HEADERS = [
    "date",
    "title",
    "url",
    "source",
    "category",
    "jurisdiction",
    "phase",
    "summary_ko",
    "event_key",
    "status",
]


def format_row(node: BriefingNode) -> list[str]:
    """Flatten a briefing node into a spreadsheet row."""
    return [
        node.pub_date,
        node.title,
        node.url,
        node.source,
        node.category,
        node.event.jurisdiction.value,
        node.event.regulatory_phase.value,
        " | ".join(node.summary_ko),
        node.event_key,
        "published",
    ]


def _load_credentials(credentials_value: str) -> dict:
    if credentials_value.strip().startswith("{"):
        return json.loads(credentials_value)
    if os.path.exists(credentials_value):
        with open(credentials_value, encoding="utf-8") as handle:
            return json.load(handle)
    raise FileNotFoundError(f"Could not find credentials file: {credentials_value}")


def _get_worksheet(credentials_value: str, spreadsheet_id: str):
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(_load_credentials(credentials_value), scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(spreadsheet_id).sheet1


def sync_to_sheets(
    nodes: list[BriefingNode],
    credentials_json: str | None,
    spreadsheet_id: str | None,
) -> None:
    """Append briefing rows to the admin spreadsheet when configured."""
    if not credentials_json or not spreadsheet_id:
        logger.info("Google Sheets not configured, skipping sync")
        return

    if not nodes:
        logger.info("No briefing nodes to sync")
        return

    try:
        worksheet = _get_worksheet(credentials_json, spreadsheet_id)
        worksheet.append_rows([format_row(node) for node in nodes])
        logger.info("Synced %d rows to Google Sheets", len(nodes))
    except Exception as exc:  # pragma: no cover - integration boundary
        logger.error("Google Sheets sync failed: %s", exc)

