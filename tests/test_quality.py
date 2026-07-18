from pipeline.models import BriefingNode, EventType, Jurisdiction, LegalEvent, RegulatoryPhase
from pipeline.quality import validate_briefing_quality


def _event() -> LegalEvent:
    return LegalEvent(
        jurisdiction=Jurisdiction.US,
        event_type=EventType.POLICY,
        regulatory_phase=RegulatoryPhase.PROPOSED,
        actors=["FTC"],
        object="gaming policy",
        action="updated guidance",
        game_mechanic=None,
        time_hint="2026",
    )


def _node(
    title: str = "FTC updates gaming policy",
    title_ko: str = "FTC, 게임 정책 업데이트",
    summary_ko: list[str] | None = None,
    category: str = "PRIVACY_SECURITY",
    event_key: str = "us_ftc_gaming_policy_2026",
) -> BriefingNode:
    return BriefingNode(
        title=title,
        url=f"https://example.com/{event_key}",
        source="Test Feed",
        pub_date="2026-06-22",
        category=category,
        summary_ko=summary_ko
        or ["FTC가 게임 정책을 업데이트했다.", "실무상 개인정보 점검이 필요하다.", "게임사는 고지 체계를 확인해야 한다."],
        event=_event(),
        event_key=event_key,
        is_primary=True,
        title_ko=title_ko,
    )


def test_quality_allows_normal_korean_briefing():
    nodes = [_node(event_key=f"key_{index}") for index in range(10)]

    report = validate_briefing_quality(nodes)

    assert report.ok


def test_quality_blocks_summary_fallback_batch():
    nodes = [
        _node(
            title=f"English title {index}",
            title_ko="",
            summary_ko=[f"English title {index}"],
            event_key=f"key_{index}",
        )
        for index in range(10)
    ]

    report = validate_briefing_quality(nodes)

    assert not report.ok
    assert "summary_fallback_rate" in [issue.code for issue in report.issues]


def test_quality_blocks_duplicate_event_keys():
    nodes = [_node(event_key="same_event_key") for _ in range(3)]

    report = validate_briefing_quality(nodes)

    assert not report.ok
    assert "duplicate_event_keys" in [issue.code for issue in report.issues]


def test_quality_blocks_etc_heavy_batch():
    nodes = [_node(category="ETC", event_key=f"key_{index}") for index in range(10)]

    report = validate_briefing_quality(nodes)

    assert not report.ok
    assert "etc_rate" in [issue.code for issue in report.issues]


def test_quality_blocks_selected_item_without_legal_hook():
    report = validate_briefing_quality([_node()], legal_hooks=[""])

    assert not report.ok
    assert "missing_legal_hook" in [issue.code for issue in report.issues]
