from pipeline.intelligence.dedup import (
    DedupEntry,
    DedupIndex,
    compute_event_key,
    compute_event_fingerprint,
    deduplicate_articles,
    topic_tokens_hash,
    url_hash,
)
from pipeline.sources.rss import RawArticle


def _article(title: str, url: str, description: str = "") -> RawArticle:
    return RawArticle(
        title=title,
        url=url,
        source="Test",
        description=description,
        pub_date="2026-03-23",
    )


def test_hashes_are_stable():
    assert url_hash("https://example.com/article") == url_hash("https://example.com/article")
    assert topic_tokens_hash("EU Loot Box Regulation Update") == topic_tokens_hash("Update: EU Loot Box Regulation")


def test_compute_event_key_shape():
    assert len(compute_event_key("EU", ["EU Commission"], "loot box", "regulation")) == 16


def test_compute_event_fingerprint_normalizes_inputs():
    first = compute_event_fingerprint(
        "EU",
        ["EU Commission", "Apple"],
        "Loot Box Rules!",
        "Issued guidance",
        "2026q2",
    )
    second = compute_event_fingerprint(
        "eu",
        ["apple", "eu commission"],
        "loot box rules",
        "issued   guidance",
        "2026Q2",
    )
    assert len(first) == 16
    assert first == second


def test_deduplicate_articles_filters_url_and_existing_index():
    existing = DedupIndex(
        entries=[DedupEntry(event_key="", url_hash=url_hash("https://old.com/article"), date="2026-03-20")]
    )
    articles = [
        _article("Old Article", "https://old.com/article"),
        _article("EU Loot Box Regulation", "https://a.com/1"),
        _article("Loot Box Regulation EU", "https://b.com/2"),
    ]
    result = deduplicate_articles(articles, existing)
    assert len(result) == 1
    assert result[0].title == "EU Loot Box Regulation"
