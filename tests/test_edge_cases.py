"""Tests for edge cases identified in eng review."""
from unittest.mock import MagicMock

from pipeline.intelligence.classifier import classify_article
from pipeline.intelligence.summarizer import summarize_article
from pipeline.intelligence.dedup import DedupEntry, DedupIndex
from pipeline.sources.rss import RawArticle
from pipeline.store.dedup_index import prune_old_entries


def _article() -> RawArticle:
    return RawArticle(
        title="Test Article",
        url="https://example.com/test",
        source="Test",
        description="Test description",
        pub_date="2026-04-01",
    )


def test_classifier_defaults_invalid_category_to_etc():
    llm = MagicMock()
    llm.generate_json.return_value = {
        "category": "INVALID_NONEXISTENT",
        "jurisdiction": "EU",
        "event_type": "legislation",
        "regulatory_phase": "enacted",
        "actors": ["EU Commission"],
        "object": "test",
        "action": "test action",
        "game_mechanic": None,
        "time_hint": "",
    }
    result = classify_article(_article(), llm)
    assert result.category == "ETC"


def test_summarizer_handles_string_instead_of_list():
    llm = MagicMock()
    llm.generate_json.return_value = {"summary_ko": "단일 문자열 요약입니다."}
    result = summarize_article(_article(), llm)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0] == "단일 문자열 요약입니다."


def test_prune_skips_malformed_dates():
    index = DedupIndex(entries=[
        DedupEntry(event_key="good", url_hash="abc", date="2026-04-01"),
        DedupEntry(event_key="bad_empty", url_hash="def", date=""),
        DedupEntry(event_key="bad_format", url_hash="ghi", date="not-a-date"),
        DedupEntry(event_key="old", url_hash="jkl", date="2020-01-01"),
    ])
    result = prune_old_entries(index, today="2026-04-01")
    event_keys = [e.event_key for e in result.entries]
    assert "good" in event_keys
    assert "bad_empty" not in event_keys
    assert "bad_format" not in event_keys
    assert "old" not in event_keys


def test_prune_uses_config_retention_days():
    index = DedupIndex(entries=[
        DedupEntry(event_key="recent", url_hash="abc", date="2026-03-25"),
    ], retention_days=30)
    # With retention_days=5 from config, the entry is outside the window
    result = prune_old_entries(index, today="2026-04-01", retention_days=5)
    assert len(result.entries) == 0
    assert result.retention_days == 5
    # With retention_days=30, the entry is inside the window
    result = prune_old_entries(index, today="2026-04-01", retention_days=30)
    assert len(result.entries) == 1
