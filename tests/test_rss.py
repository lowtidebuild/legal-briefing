from unittest.mock import MagicMock, patch

from pipeline.config import SourceEntry
from pipeline.sources.rss import RawArticle, fetch_all_feeds, fetch_feed


def test_fetch_feed_parses_entries():
    with patch("pipeline.sources.rss.feedparser.parse") as mock_parse:
        mock_parse.return_value = MagicMock(
            entries=[
                MagicMock(
                    title="EU Loot Box Regulation Update",
                    link="https://example.com/eu-lootbox",
                    get=lambda key, default="": {"summary": "The EU has updated..."}.get(key, default),
                    published_parsed=(2026, 3, 23, 10, 0, 0, 0, 82, 0),
                ),
            ]
        )
        articles = fetch_feed(SourceEntry(name="Test Feed", url="https://example.com/feed"))
        assert len(articles) == 1
        assert articles[0].source == "Test Feed"


def test_fetch_all_feeds_combines_tiers():
    source_a = SourceEntry(name="FeedA", url="https://a.com/feed")
    source_b = SourceEntry(name="FeedB", url="https://b.com/feed")

    def mock_fetch(source):
        return [
            RawArticle(
                title=f"Article from {source.name}",
                url=f"https://{source.name}",
                source=source.name,
                description="",
                pub_date="2026-03-23",
            )
        ]

    with patch("pipeline.sources.rss.fetch_feed", side_effect=mock_fetch):
        articles = fetch_all_feeds(tier_a=[source_a], tier_b=[source_b])
        assert len(articles) == 2

