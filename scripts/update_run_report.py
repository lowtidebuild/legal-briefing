"""Update workflow-owned run stages after git and Pages operations."""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.run_report import RunStatus, update_run_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Update allowlisted run report stages")
    parser.add_argument("--date", required=True)
    parser.add_argument("--output", default="output")
    parser.add_argument("--stage", action="append", default=[], metavar="NAME=STATUS")
    parser.add_argument("--status", choices=[status.value for status in RunStatus])
    parser.add_argument("--action")
    args = parser.parse_args()

    stages: dict[str, str] = {}
    for item in args.stage:
        if "=" not in item:
            parser.error("--stage must use NAME=STATUS")
        name, value = item.split("=", 1)
        if not name or not value:
            parser.error("--stage must use NAME=STATUS")
        stages[name] = value

    path = update_run_report(
        output_dir=args.output,
        date=args.date,
        stage_updates=stages,
        status=RunStatus(args.status) if args.status else None,
        action=args.action,
    )
    if path is None:
        raise SystemExit(f"Run report not found for {args.date}")


if __name__ == "__main__":
    main()
