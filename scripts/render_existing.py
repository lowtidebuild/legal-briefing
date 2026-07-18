"""Re-render the site from an existing daily JSON file without external delivery."""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.config import load_config
from pipeline.quality import validate_briefing_quality
from pipeline.render.manifest import write_manifest
from pipeline.render.site import copy_static, render_archive, render_article_pages, render_index
from pipeline.store.daily import load_daily
from pipeline.store.query import list_briefing_dates

logger = logging.getLogger(__name__)


def render_existing(
    date: str,
    config_path: str = "config.yaml",
    output_dir: str = "output",
    template_dir: str = "templates",
    static_dir: str = "static",
) -> None:
    """Render one saved briefing as the latest page, without LLM, email, or Sheets."""
    cfg = load_config(config_path)
    data_dir = os.path.join(output_dir, "data", "daily")
    daily_path = os.path.join(data_dir, f"{date}.json")
    if not os.path.isfile(daily_path):
        raise SystemExit(f"No saved briefing data found for {date}")
    nodes = load_daily(date, data_dir=data_dir)

    quality_report = validate_briefing_quality(nodes)
    if not quality_report.ok:
        raise SystemExit(f"Saved briefing failed quality check: {quality_report.describe()}")

    render_index(
        nodes=nodes,
        date=date,
        output_dir=output_dir,
        template_dir=template_dir,
        base_url=cfg.site.base_url,
    )

    dates = list_briefing_dates(data_dir=data_dir)
    daily_nodes = {saved_date: load_daily(saved_date, data_dir=data_dir) for saved_date in dates}
    render_archive(
        entries=[{"date": saved_date, "count": len(daily_nodes[saved_date])} for saved_date in dates],
        output_dir=output_dir,
        template_dir=template_dir,
        base_url=cfg.site.base_url,
        all_daily_nodes=daily_nodes,
    )
    render_article_pages(
        nodes=[node for saved_nodes in daily_nodes.values() for node in saved_nodes],
        output_dir=output_dir,
        template_dir=template_dir,
        base_url=cfg.site.base_url,
    )
    copy_static(output_dir=output_dir, static_dir=static_dir)
    write_manifest(output_dir=output_dir)
    logger.info("Re-rendered saved briefing %s without email or Sheets delivery", date)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a saved briefing without external delivery")
    parser.add_argument("--date", required=True, help="Saved briefing date in YYYY-MM-DD format")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--output", default="output")
    parser.add_argument("--templates", default="templates")
    parser.add_argument("--static", default="static")
    args = parser.parse_args()

    render_existing(
        date=args.date,
        config_path=args.config,
        output_dir=args.output,
        template_dir=args.templates,
        static_dir=args.static,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
