from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from pipeline.models import BriefingNode

_HANGUL_RE = re.compile(r"[가-힣]")


@dataclass(frozen=True)
class QualityIssue:
    code: str
    message: str


@dataclass(frozen=True)
class QualityReport:
    total: int
    fallback_summary_count: int
    etc_count: int
    duplicate_event_key_count: int
    duplicate_event_keys: list[str]
    issues: list[QualityIssue]

    @property
    def ok(self) -> bool:
        return not self.issues

    def describe(self) -> str:
        return "; ".join(issue.message for issue in self.issues)


def _has_hangul(value: str) -> bool:
    return bool(_HANGUL_RE.search(value))


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _looks_like_summary_fallback(node: BriefingNode) -> bool:
    if not node.summary_ko:
        return True

    summary_text = " ".join(line.strip() for line in node.summary_ko if line.strip())
    if not summary_text:
        return True

    if not _has_hangul(summary_text):
        return True

    return (
        len(node.summary_ko) == 1
        and _normalize_text(node.summary_ko[0]) == _normalize_text(node.title)
    )


def validate_briefing_quality(
    nodes: list[BriefingNode],
    max_fallback_summary_ratio: float = 0.3,
    max_etc_ratio: float = 0.8,
) -> QualityReport:
    """Catch degraded LLM output before it is published or emailed."""
    total = len(nodes)
    issues: list[QualityIssue] = []
    if total == 0:
        return QualityReport(
            total=0,
            fallback_summary_count=0,
            etc_count=0,
            duplicate_event_key_count=0,
            duplicate_event_keys=[],
            issues=issues,
        )

    fallback_summary_count = sum(1 for node in nodes if _looks_like_summary_fallback(node))
    if fallback_summary_count and (
        fallback_summary_count >= 3
        or fallback_summary_count / total > max_fallback_summary_ratio
    ):
        issues.append(
            QualityIssue(
                code="summary_fallback_rate",
                message=(
                    f"{fallback_summary_count}/{total} summaries look like fallback output "
                    "(missing Korean text or equal to the original title)"
                ),
            )
        )

    etc_count = sum(1 for node in nodes if node.category == "ETC")
    if total >= 5 and etc_count / total > max_etc_ratio:
        issues.append(
            QualityIssue(
                code="etc_rate",
                message=f"{etc_count}/{total} nodes are categorized as ETC",
            )
        )

    event_key_counts = Counter(node.event_key for node in nodes if node.event_key)
    duplicate_event_keys = sorted(key for key, count in event_key_counts.items() if count > 1)
    duplicate_event_key_count = sum(event_key_counts[key] - 1 for key in duplicate_event_keys)
    if duplicate_event_key_count:
        preview = ", ".join(duplicate_event_keys[:3])
        if len(duplicate_event_keys) > 3:
            preview += ", ..."
        issues.append(
            QualityIssue(
                code="duplicate_event_keys",
                message=f"{duplicate_event_key_count} duplicate event_key collision(s): {preview}",
            )
        )

    return QualityReport(
        total=total,
        fallback_summary_count=fallback_summary_count,
        etc_count=etc_count,
        duplicate_event_key_count=duplicate_event_key_count,
        duplicate_event_keys=duplicate_event_keys,
        issues=issues,
    )
