from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from pipeline.sources.rss import SourceFetchResult, SourceStatus


class RunStatus(str, Enum):
    SUCCESS = "SUCCESS"
    DEGRADED = "DEGRADED"
    NO_UPDATES = "NO_UPDATES"
    FAIL = "FAIL"


@dataclass(frozen=True)
class RunReport:
    run_id: str
    briefing_date: str
    status: RunStatus
    source_statuses: dict[str, dict[str, object]]
    counts: dict[str, int]
    llm_models: list[dict[str, object]]
    fallback_batches: int
    quality_gate: dict[str, object]
    stages: dict[str, str]
    duration_seconds: float
    action_required: list[str]

    def to_dict(self) -> dict[str, object]:
        """Return only fields approved for the machine-readable public report."""
        return {
            "schema_version": 1,
            "run_id": self.run_id,
            "briefing_date": self.briefing_date,
            "status": self.status.value,
            "source_statuses": self.source_statuses,
            "counts": self.counts,
            "llm_models": self.llm_models,
            "fallback_batches": self.fallback_batches,
            "quality_gate": self.quality_gate,
            "stages": self.stages,
            "duration_seconds": round(self.duration_seconds, 3),
            "action_required": self.action_required,
        }


def make_run_id(briefing_date: str) -> str:
    return f"briefing-{briefing_date}"


def summarize_sources(results: Iterable[SourceFetchResult]) -> dict[str, dict[str, object]]:
    summary: dict[str, dict[str, object]] = {}
    for status in SourceStatus:
        names = sorted(result.source_name for result in results if result.status == status)
        if names:
            summary[status.value] = {"count": len(names), "sources": names}
    return summary


def source_actions(results: Iterable[SourceFetchResult]) -> list[str]:
    actions = []
    for result in results:
        if result.status not in {SourceStatus.OK, SourceStatus.EMPTY}:
            actions.append(f"{result.source_name}: {result.status.value}")
    return sorted(actions)


def collect_llm_metrics(providers: Iterable[object]) -> tuple[list[dict[str, object]], int]:
    """Collect counters without prompts, model responses, or provider exceptions."""
    unique_wrappers: set[int] = set()
    fallback_batches = 0
    leaf_providers: list[object] = []
    for provider in providers:
        if id(provider) in unique_wrappers:
            continue
        unique_wrappers.add(id(provider))
        fallback_batches += int(getattr(provider, "fallback_calls", 0) or 0)
        primary = getattr(provider, "primary", None)
        secondary = getattr(provider, "secondary", None)
        if primary is not None and secondary is not None:
            leaf_providers.extend([primary, secondary])
        else:
            leaf_providers.append(provider)

    models: list[dict[str, object]] = []
    seen: set[int] = set()
    for provider in leaf_providers:
        if id(provider) in seen:
            continue
        seen.add(id(provider))
        metrics = getattr(provider, "metrics", None)
        if metrics is None:
            continue
        models.append(
            {
                "model": str(getattr(provider, "model_name", provider.__class__.__name__)),
                "attempts": int(getattr(metrics, "attempts", 0)),
                "successes": int(getattr(metrics, "successes", 0)),
                "rate_limits": int(getattr(metrics, "rate_limits", 0)),
                "failures": int(getattr(metrics, "failures", 0)),
            }
        )
    return models, fallback_batches


def llm_was_degraded(models: Iterable[dict[str, object]], fallback_batches: int) -> bool:
    return fallback_batches > 0 or any(int(model.get("rate_limits", 0)) > 0 for model in models)


def determine_run_status(
    *,
    source_has_data: bool,
    selector_completed: bool,
    published_count: int,
    tier_a_total: int,
    tier_a_unhealthy: int,
    llm_degraded: bool,
    selector_degraded: bool,
    quality_ok: bool,
    mandatory_stages_ok: bool = True,
) -> RunStatus:
    if not source_has_data or not selector_completed or not quality_ok or not mandatory_stages_ok:
        return RunStatus.FAIL

    source_degraded = tier_a_total > 0 and tier_a_unhealthy / tier_a_total >= 0.5
    degraded = source_degraded or llm_degraded or selector_degraded
    if published_count == 0 and not degraded:
        return RunStatus.NO_UPDATES
    if degraded:
        return RunStatus.DEGRADED
    return RunStatus.SUCCESS


def render_step_summary(report: RunReport) -> str:
    lines = [
        f"## Game Legal Briefing — {report.status.value}",
        "",
        f"- Run: `{report.run_id}`",
        f"- Briefing date: `{report.briefing_date}`",
        f"- Duration: `{report.duration_seconds:.1f}s`",
        "",
        "### Pipeline counts",
        "",
        "| Stage | Count |",
        "|---|---:|",
    ]
    lines.extend(f"| {name} | {count} |" for name, count in report.counts.items())
    lines.extend(["", "### Source health", "", "| Status | Count | Sources |", "|---|---:|---|"])
    if report.source_statuses:
        for status, values in report.source_statuses.items():
            names = ", ".join(str(name) for name in values["sources"])
            lines.append(f"| {status} | {values['count']} | {names} |")
    else:
        lines.append("| not_recorded | 0 | — |")

    lines.extend(["", "### Delivery stages", "", "| Stage | Status |", "|---|---|"])
    lines.extend(f"| {name} | {status} |" for name, status in report.stages.items())
    lines.extend(["", "### Action required", ""])
    if report.action_required:
        lines.extend(f"- {action}" for action in report.action_required)
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def write_run_report(
    report: RunReport,
    output_dir: str,
    step_summary_path: str | None = None,
) -> str:
    report_dir = os.path.join(output_dir, "data", "runs")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, f"{report.briefing_date}.json")
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report.to_dict(), handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    summary_path = step_summary_path or os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(render_step_summary(report))
    return report_path


def update_run_report(
    *,
    output_dir: str,
    date: str,
    stage_updates: dict[str, str],
    status: RunStatus | None = None,
    action: str | None = None,
) -> str | None:
    """Update workflow-owned stages without adding non-allowlisted data."""
    allowed_stages = {"generate", "git", "pages", "email", "sheets"}
    unknown = set(stage_updates) - allowed_stages
    if unknown:
        raise ValueError(f"Unknown run report stage: {sorted(unknown)[0]}")

    path = os.path.join(output_dir, "data", "runs", f"{date}.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Run report is unreadable") from exc
    if payload.get("schema_version") != 1 or not isinstance(payload.get("stages"), dict):
        raise RuntimeError("Unsupported run report schema")

    payload["stages"].update(stage_updates)
    if status is not None:
        payload["status"] = status.value
    if action:
        actions = payload.setdefault("action_required", [])
        if not isinstance(actions, list):
            raise RuntimeError("Run report action list is invalid")
        if action not in actions:
            actions.append(action)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path
