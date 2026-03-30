from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta

from pipeline.intelligence.dedup import DedupEntry, DedupIndex

logger = logging.getLogger(__name__)


def load_dedup_index(path: str) -> DedupIndex:
    """Load the rolling dedup index from disk."""
    if not os.path.exists(path):
        return DedupIndex()

    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)

    return DedupIndex(
        entries=[
            DedupEntry(
                event_key=entry["event_key"],
                url_hash=entry["url_hash"],
                date=entry["date"],
            )
            for entry in payload.get("entries", [])
        ],
        schema_version=payload.get("schema_version", 1),
        retention_days=payload.get("retention_days", 30),
    )


def save_dedup_index(index: DedupIndex, path: str) -> None:
    """Write the rolling dedup index back to disk."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload = {
        "schema_version": index.schema_version,
        "retention_days": index.retention_days,
        "entries": [
            {
                "event_key": entry.event_key,
                "url_hash": entry.url_hash,
                "date": entry.date,
            }
            for entry in index.entries
        ],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    logger.info("Saved dedup index with %d entries", len(index.entries))


def prune_old_entries(index: DedupIndex, today: str | None = None) -> DedupIndex:
    """Drop dedup entries outside the retention window."""
    today_str = today or datetime.now().strftime("%Y-%m-%d")
    cutoff = datetime.strptime(today_str, "%Y-%m-%d") - timedelta(days=index.retention_days)
    retained = [
        entry
        for entry in index.entries
        if datetime.strptime(entry.date, "%Y-%m-%d") >= cutoff
    ]
    return DedupIndex(
        entries=retained,
        schema_version=index.schema_version,
        retention_days=index.retention_days,
    )

