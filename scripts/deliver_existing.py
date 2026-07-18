"""Deliver one already-generated run after its Pages deployment succeeds."""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.config import load_config
from pipeline.delivery import deliver_existing


def main() -> None:
    parser = argparse.ArgumentParser(description="Deliver an immutable generated briefing")
    parser.add_argument("--date", required=True, help="Generated briefing date in YYYY-MM-DD format")
    parser.add_argument("--run-id", help="Expected run ID; mismatch aborts delivery")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--output", default="output")
    parser.add_argument("--templates", default="templates")
    parser.add_argument("--force-delivery", action="store_true")
    args = parser.parse_args()

    outcome = deliver_existing(
        date=args.date,
        cfg=load_config(args.config),
        output_dir=args.output,
        template_dir=args.templates,
        expected_run_id=args.run_id,
        force_delivery=args.force_delivery,
    )
    if outcome.already_completed:
        logging.info("Delivery already completed; no external calls were made")
    else:
        logging.info("Delivery completed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
