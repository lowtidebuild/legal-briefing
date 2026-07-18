from __future__ import annotations

import json

import pytest

from pipeline.run_manifest import (
    RunManifestError,
    create_run_manifest,
    load_run_manifest,
    verify_run_manifest,
)


def _write_daily(tmp_path, date: str, payload: list[dict]) -> None:
    path = tmp_path / "data" / "daily" / f"{date}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_run_manifest_hashes_and_verifies_daily_content(tmp_path):
    date = "2026-07-20"
    _write_daily(tmp_path, date, [{"event_key": "one"}])
    created = create_run_manifest(
        date=date,
        run_id=f"briefing-{date}",
        item_count=1,
        output_dir=str(tmp_path),
    )

    loaded = load_run_manifest(str(tmp_path), date)
    assert loaded == created
    assert len(created.content_sha256) == 64
    assert verify_run_manifest(output_dir=str(tmp_path), date=date) == created


def test_run_manifest_rejects_changed_daily_content(tmp_path):
    date = "2026-07-20"
    _write_daily(tmp_path, date, [{"event_key": "one"}])
    create_run_manifest(
        date=date,
        run_id=f"briefing-{date}",
        item_count=1,
        output_dir=str(tmp_path),
    )
    _write_daily(tmp_path, date, [{"event_key": "changed"}])

    with pytest.raises(RunManifestError, match="hash"):
        verify_run_manifest(output_dir=str(tmp_path), date=date)


def test_run_manifest_rejects_wrong_run_id(tmp_path):
    date = "2026-07-20"
    _write_daily(tmp_path, date, [])
    create_run_manifest(
        date=date,
        run_id=f"briefing-{date}",
        item_count=0,
        output_dir=str(tmp_path),
    )
    with pytest.raises(RunManifestError, match="Run ID"):
        verify_run_manifest(
            output_dir=str(tmp_path),
            date=date,
            expected_run_id="wrong-run",
        )
