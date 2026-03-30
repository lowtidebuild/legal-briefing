from __future__ import annotations

import glob
import os

from pipeline.models import BriefingNode, Jurisdiction, RegulatoryPhase
from pipeline.store.daily import load_daily


def list_briefing_dates(data_dir: str = "output/data/daily") -> list[str]:
    """Return available briefing dates sorted newest-first."""
    paths = glob.glob(os.path.join(data_dir, "*.json"))
    dates = [os.path.splitext(os.path.basename(path))[0] for path in paths]
    return sorted(dates, reverse=True)


def query_nodes(
    data_dir: str = "output/data/daily",
    jurisdiction: Jurisdiction | None = None,
    category: str | None = None,
    phase: RegulatoryPhase | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[BriefingNode]:
    """Load and filter stored briefing nodes."""
    result: list[BriefingNode] = []
    for date in list_briefing_dates(data_dir):
        if date_from and date < date_from:
            continue
        if date_to and date > date_to:
            continue
        for node in load_daily(date, data_dir=data_dir):
            if jurisdiction and node.event.jurisdiction != jurisdiction:
                continue
            if category and node.category != category:
                continue
            if phase and node.event.regulatory_phase != phase:
                continue
            result.append(node)
    return result

