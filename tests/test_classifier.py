from unittest.mock import MagicMock

from pipeline.intelligence.classifier import classify_article
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
    }
    result = classify_article(_article(), mock_llm)
    assert result.category == "CONSUMER_MONETIZATION"
    assert result.event.jurisdiction == Jurisdiction.EU
    assert result.event.event_type == EventType.LEGISLATION
    assert result.event.regulatory_phase == RegulatoryPhase.ENACTED
    assert mock_llm.generate_json_schema.call_args.kwargs["schema"]["properties"]["category"]["enum"]


def test_classify_article_fallback_on_failure():
    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.generate_json_schema.side_effect = Exception("LLM failed")
    result = classify_article(_article(), mock_llm)
    assert result.category == "ETC"
    assert result.event.jurisdiction == Jurisdiction.GLOBAL
