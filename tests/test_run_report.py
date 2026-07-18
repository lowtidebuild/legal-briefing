from __future__ import annotations

import json

import pytest

from pipeline.llm.base import LLMCallMetrics
from pipeline.run_report import (
    RunReport,
    RunStatus,
    collect_llm_metrics,
    determine_run_status,
    source_actions,
    summarize_sources,
    update_run_report,
    write_run_report,
)
from pipeline.sources.rss import SourceFetchResult, SourceStatus


def _source(name: str, status: SourceStatus, tier: str = "tier_a") -> SourceFetchResult:
    return SourceFetchResult(name, tier, status, 0, [])


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, RunStatus.SUCCESS),
        ({"published_count": 0}, RunStatus.NO_UPDATES),
        ({"llm_degraded": True}, RunStatus.DEGRADED),
        ({"selector_degraded": True}, RunStatus.DEGRADED),
        ({"tier_a_total": 4, "tier_a_unhealthy": 2}, RunStatus.DEGRADED),
        ({"source_has_data": False}, RunStatus.FAIL),
        ({"quality_ok": False}, RunStatus.FAIL),
        ({"mandatory_stages_ok": False}, RunStatus.FAIL),
    ],
)
def test_run_status_rules(overrides, expected):
    values = {
        "source_has_data": True,
        "selector_completed": True,
        "published_count": 5,
        "tier_a_total": 4,
        "tier_a_unhealthy": 0,
        "llm_degraded": False,
        "selector_degraded": False,
        "quality_ok": True,
        "mandatory_stages_ok": True,
    }
    values.update(overrides)
    assert determine_run_status(**values) == expected


def test_2026_07_17_health_fixture_is_degraded():
    assert determine_run_status(
        source_has_data=True,
        selector_completed=True,
        published_count=10,
        tier_a_total=44,
        tier_a_unhealthy=30,
        llm_degraded=True,
        selector_degraded=False,
        quality_ok=True,
    ) == RunStatus.DEGRADED


def test_source_summary_separates_actionable_statuses():
    results = [
        _source("Healthy", SourceStatus.OK),
        _source("Blocked", SourceStatus.HTTP_403),
        _source("Missing", SourceStatus.HTTP_404),
        _source("Slow", SourceStatus.TIMEOUT),
        _source("Quiet", SourceStatus.EMPTY),
    ]
    summary = summarize_sources(results)
    assert summary["ok"]["count"] == 1
    assert summary["empty"]["sources"] == ["Quiet"]
    assert source_actions(results) == [
        "Blocked: http_403",
        "Missing: http_404",
        "Slow: timeout",
    ]


def test_collect_llm_metrics_contains_counters_only():
    class Provider:
        model_name = "safe-model"
        metrics = LLMCallMetrics(attempts=3, successes=2, failures=1, rate_limits=1)

    models, fallback_batches = collect_llm_metrics([Provider()])
    assert models == [
        {
            "model": "safe-model",
            "attempts": 3,
            "successes": 2,
            "rate_limits": 1,
            "failures": 1,
        }
    ]
    assert fallback_batches == 0


def test_report_json_is_allowlisted_and_step_summary_is_actionable(tmp_path):
    report = RunReport(
        run_id="briefing-2026-07-17-safe",
        briefing_date="2026-07-17",
        status=RunStatus.DEGRADED,
        source_statuses={"http_403": {"count": 1, "sources": ["Blocked Feed"]}},
        counts={"raw": 20, "published": 5},
        llm_models=[
            {
                "model": "gemini-flash",
                "attempts": 3,
                "successes": 2,
                "rate_limits": 1,
                "failures": 1,
            }
        ],
        fallback_batches=1,
        quality_gate={"status": "passed", "issue_codes": []},
        stages={"generate": "completed", "email": "completed", "sheets": "completed"},
        duration_seconds=12.3456,
        action_required=["Blocked Feed: http_403"],
    )
    summary_path = tmp_path / "summary.md"
    report_path = write_run_report(report, str(tmp_path), str(summary_path))

    payload = json.loads(open(report_path, encoding="utf-8").read())
    serialized = json.dumps(payload).lower()
    for forbidden in ("credential", "prompt", "recipient", "sheet_id", "article_body", "exception"):
        assert forbidden not in serialized
    assert payload["duration_seconds"] == 12.346

    summary = summary_path.read_text(encoding="utf-8")
    assert "DEGRADED" in summary
    assert "Blocked Feed: http_403" in summary


def test_workflow_stage_update_preserves_allowlisted_report(tmp_path):
    report = RunReport(
        run_id="briefing-2026-07-17",
        briefing_date="2026-07-17",
        status=RunStatus.SUCCESS,
        source_statuses={},
        counts={"published": 1},
        llm_models=[],
        fallback_batches=0,
        quality_gate={"status": "passed", "issue_codes": []},
        stages={"generate": "completed", "git": "not_run", "pages": "not_run"},
        duration_seconds=1.0,
        action_required=[],
    )
    write_run_report(report, str(tmp_path))
    update_run_report(
        output_dir=str(tmp_path),
        date="2026-07-17",
        stage_updates={"git": "completed", "pages": "failed"},
        status=RunStatus.FAIL,
        action="pages: failed",
    )
    payload = json.loads(
        (tmp_path / "data" / "runs" / "2026-07-17.json").read_text(encoding="utf-8")
    )
    assert payload["status"] == "FAIL"
    assert payload["stages"]["git"] == "completed"
    assert payload["stages"]["pages"] == "failed"
    assert payload["action_required"] == ["pages: failed"]


def test_workflow_stage_update_rejects_unknown_fields(tmp_path):
    with pytest.raises(ValueError, match="Unknown run report stage"):
        update_run_report(
            output_dir=str(tmp_path),
            date="2026-07-17",
            stage_updates={"recipient": "leak"},
        )
