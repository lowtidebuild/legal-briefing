from unittest.mock import MagicMock

from pipeline.intelligence.summarizer import summarize_article
from pipeline.llm.base import LLMProvider
from pipeline.sources.rss import RawArticle


def _article() -> RawArticle:
    return RawArticle(
        title="EU Enacts Loot Box Regulation",
        url="https://example.com/eu-lootbox",
        source="GamesIndustry.biz",
        description="The European Union has enacted new regulations.",
        pub_date="2026-03-23",
    )


def test_summarize_returns_list():
    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.generate_json.return_value = {
        "summary_ko": ["EU가 루트박스 규제를 확정했다.", "2026년 3분기부터 시행 예정.", "게임사 공시 의무화."]
    }
    result = summarize_article(_article(), mock_llm)
    assert len(result) == 3


def test_summarize_fallback_on_failure():
    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.generate_json.side_effect = Exception("LLM failed")
    assert summarize_article(_article(), mock_llm) == ["EU Enacts Loot Box Regulation"]

