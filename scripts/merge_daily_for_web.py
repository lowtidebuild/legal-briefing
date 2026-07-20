"""Merge a recovery run into saved daily data without any delivery side effects."""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.intelligence.dedup import DedupEntry, url_hash
from pipeline.quality import validate_briefing_quality
from pipeline.store.daily import load_daily, save_daily
from pipeline.store.dedup_index import load_dedup_index, save_dedup_index

logger = logging.getLogger(__name__)
DATE_PATTERN = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")


@dataclass(frozen=True)
class MergeResult:
    previous_count: int
    incoming_count: int
    added_count: int
    final_count: int


def merge_daily_for_web(
    *,
    date: str,
    source_output_dir: str,
    target_output_dir: str = "output",
    max_items: int = 10,
) -> MergeResult:
    """Preserve published nodes and append unique recovery nodes up to max_items."""
    if not DATE_PATTERN.fullmatch(date):
        raise ValueError("date must use YYYY-MM-DD format")
    if max_items <= 0:
        raise ValueError("max_items must be positive")

    source_data_dir = os.path.join(source_output_dir, "data", "daily")
    target_data_dir = os.path.join(target_output_dir, "data", "daily")
    existing = load_daily(date, data_dir=target_data_dir)
    incoming = load_daily(date, data_dir=source_data_dir)
    if not existing:
        raise ValueError(f"No existing published briefing found for {date}")
    if not incoming:
        raise ValueError(f"No recovery briefing found for {date}")
    if len(existing) > max_items:
        raise ValueError("Existing briefing already exceeds max_items")

    seen_urls = {url_hash(node.url) for node in existing}
    seen_event_keys = {node.event_key for node in existing if node.event_key}
    additions = []
    for node in incoming:
        node_url_hash = url_hash(node.url)
        if node_url_hash in seen_urls or (node.event_key and node.event_key in seen_event_keys):
            continue
        additions.append(node)
        seen_urls.add(node_url_hash)
        if node.event_key:
            seen_event_keys.add(node.event_key)
        if len(existing) + len(additions) >= max_items:
            break

    merged = [*existing, *additions]
    quality_report = validate_briefing_quality(merged)
    if not quality_report.ok:
        raise ValueError(f"Merged briefing failed quality check: {quality_report.describe()}")

    target_dedup_path = os.path.join(target_output_dir, "data", "dedup_index.json")
    source_dedup_path = os.path.join(source_output_dir, "data", "dedup_index.json")
    target_index = load_dedup_index(target_dedup_path)
    source_index = load_dedup_index(source_dedup_path)
    source_entries = {entry.url_hash: entry for entry in source_index.entries}
    indexed_urls = {entry.url_hash for entry in target_index.entries}

    for node in additions:
        node_url_hash = url_hash(node.url)
        if node_url_hash in indexed_urls:
            continue
        source_entry = source_entries.get(node_url_hash)
        target_index.entries.append(
            DedupEntry(
                event_key=node.event_key,
                url_hash=node_url_hash,
                date=date,
                event_fingerprint=source_entry.event_fingerprint if source_entry else "",
            )
        )
        indexed_urls.add(node_url_hash)

    save_daily(merged, date, data_dir=target_data_dir)
    save_dedup_index(target_index, target_dedup_path)

    audit_dir = os.path.join(target_output_dir, "data", "web_repairs")
    os.makedirs(audit_dir, exist_ok=True)
    audit_path = os.path.join(audit_dir, f"{date}.json")
    with open(audit_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "schema_version": 1,
                "briefing_date": date,
                "delivery": "not_run",
                "previous_count": len(existing),
                "incoming_count": len(incoming),
                "added_count": len(additions),
                "final_count": len(merged),
                "added_event_keys": [node.event_key for node in additions],
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )
        handle.write("\n")

    logger.info(
        "Merged %d recovery nodes into %s (%d -> %d); delivery was not run",
        len(additions),
        date,
        len(existing),
        len(merged),
    )
    return MergeResult(
        previous_count=len(existing),
        incoming_count=len(incoming),
        added_count=len(additions),
        final_count=len(merged),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge recovery data into an existing briefing without email or Sheets"
    )
    parser.add_argument("--date", required=True)
    parser.add_argument("--source-output", required=True)
    parser.add_argument("--target-output", default="output")
    parser.add_argument("--max-items", type=int, default=10)
    args = parser.parse_args()
    merge_daily_for_web(
        date=args.date,
        source_output_dir=args.source_output,
        target_output_dir=args.target_output,
        max_items=args.max_items,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
