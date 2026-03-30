from __future__ import annotations

import json
import logging
import os

from pipeline.models import BriefingNode, briefing_node_to_dict, dict_to_briefing_node

logger = logging.getLogger(__name__)


def save_daily(
    nodes: list[BriefingNode],
    date: str,
    data_dir: str = "output/data/daily",
) -> str:
    """Persist a day's briefing nodes to JSON."""
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, f"{date}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump([briefing_node_to_dict(node) for node in nodes], handle, ensure_ascii=False, indent=2)
    logger.info("Saved %d nodes to %s", len(nodes), path)
    return path


def load_daily(
    date: str,
    data_dir: str = "output/data/daily",
) -> list[BriefingNode]:
    """Load one day's briefing JSON, returning an empty list if absent."""
    path = os.path.join(data_dir, f"{date}.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    return [dict_to_briefing_node(item) for item in payload]

