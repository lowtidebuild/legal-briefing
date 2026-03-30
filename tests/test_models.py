import json

from pipeline.models import (
    BriefingNode,
    EventType,
    Jurisdiction,
    LegalEvent,
    RegulatoryPhase,
    VALID_CATEGORIES,
    briefing_node_to_dict,
    dict_to_briefing_node,
)


def _sample_event() -> LegalEvent:
    return LegalEvent(
        jurisdiction=Jurisdiction.EU,
        event_type=EventType.LEGISLATION,
        regulatory_phase=RegulatoryPhase.ENACTED,
        actors=["EU Commission"],
        object="loot box regulation",
        action="enacted directive",
        game_mechanic="loot_box",
        time_hint="2026 Q2",
    )


def _sample_node() -> BriefingNode:
    return BriefingNode(
        title="EU Enacts Loot Box Regulation",
        url="https://example.com/article",
        source="GamesIndustry.biz",
        pub_date="2026-03-28",
        category="CONSUMER_MONETIZATION",
        summary_ko=["EU가 루트박스 규제를 확정했다.", "2026년 2분기부터 시행.", "게임사 영향 불가피."],
        event=_sample_event(),
        event_key="eu_lootbox_enacted_2026",
        is_primary=True,
    )


def test_enums_and_categories():
    assert Jurisdiction.KR == "KR"
    assert RegulatoryPhase.ENACTED == "enacted"
    assert EventType.ENFORCEMENT == "enforcement"
    assert "IP" in VALID_CATEGORIES


def test_briefing_node_roundtrip():
    node = _sample_node()
    data = briefing_node_to_dict(node)
    payload = json.loads(json.dumps(data, ensure_ascii=False))
    restored = dict_to_briefing_node(payload)

    assert restored.title == node.title
    assert restored.event.jurisdiction == Jurisdiction.EU
    assert restored.summary_ko == node.summary_ko

