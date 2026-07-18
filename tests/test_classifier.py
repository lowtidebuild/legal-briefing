from unittest.mock import MagicMock

import pytest

from pipeline.intelligence.classifier import classify_article
from pipeline.intelligence.dedup import compute_event_key, is_safe_event_key, url_hash
from pipeline.llm.base import LLMProvider
from pipeline.models import EventType, Jurisdiction, RegulatoryPhase
from pipeline.sources.rss import RawArticle


def _article() -> RawArticle:
    return RawArticle(
        title="EU Enacts Loot Box Regulation",
        url="https://example.com/eu-lootbox",
        source="GamesIndustry.biz",
        description="The EU has enacted new regulations requiring disclosure of loot box mechanics.",
        pub_date="2026-03-23",
    )


def test_classify_article_returns_legal_event():
    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.generate_json_schema.return_value = {
        "category": "CONSUMER_MONETIZATION",
        "jurisdiction": "EU",
        "event_type": "legislation",
        "regulatory_phase": "enacted",
        "actors": ["EU Commission"],
        "object": "loot box mechanics in games",
        "action": "enacted regulation",
        "game_mechanic": "loot_box",
        "time_hint": "effective 2026 Q3",
        "event_key": "eu_lootbox_regulation_2024",
    }
    result = classify_article(_article(), mock_llm)
    assert result.category == "CONSUMER_MONETIZATION"
    assert result.event.jurisdiction == Jurisdiction.EU
    assert result.event.event_type == EventType.LEGISLATION
    assert result.event.regulatory_phase == RegulatoryPhase.ENACTED
    assert result.event_key == "eu_lootbox_regulation_2026q1"
    call = mock_llm.generate_json_schema.call_args
    assert call.kwargs["schema"]["properties"]["category"]["enum"]
    assert "event_key" in call.kwargs["schema"]["required"]
    assert "Publication date: 2026-03-23" in call.args[0]


def test_classify_article_fallback_on_failure():
    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.generate_json_schema.side_effect = Exception("LLM failed")
    result = classify_article(_article(), mock_llm)
    assert result.category == "ETC"
    assert result.event.jurisdiction == Jurisdiction.GLOBAL
    assert result.event_key == f"{url_hash(_article().url)}_2026q1"


@pytest.mark.parametrize(
    "unsafe_key",
    [
        "../escape",
        "/tmp/escape",
        r"C:\tmp\escape",
        "safe\x00bad",
        "eu／../../escape",
        "a" * 121,
    ],
)
def test_classify_article_hash_fallback_for_unsafe_event_key(unsafe_key):
    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.generate_json_schema.return_value = {
        "category": "CONSUMER_MONETIZATION",
        "jurisdiction": "EU",
        "event_type": "legislation",
        "regulatory_phase": "enacted",
        "actors": ["EU Commission"],
        "object": "loot box mechanics in games",
        "action": "enacted regulation",
        "game_mechanic": "loot_box",
        "time_hint": "",
        "event_key": unsafe_key,
    }

    result = classify_article(_article(), mock_llm)

    fallback = compute_event_key(
        "EU",
        ["EU Commission"],
        "loot box mechanics in games",
        "enacted regulation",
    )
    assert result.event_key == f"{fallback}_2026q1"
    assert is_safe_event_key(result.event_key)
