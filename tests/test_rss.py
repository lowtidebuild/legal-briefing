import socket
import urllib.error
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from pipeline.config import SourceEntry
from pipeline.sources.rss import (
    RawArticle,
    SourceFetchResult,
    SourceStatus,
    fetch_all_feeds,
    fetch_all_feeds_with_report,
    fetch_feed,
    fetch_feed_result,
)


def test_fetch_feed_parses_entries():
    mock_response = MagicMock()
    mock_response.read.return_value = b"<rss>mock</rss>"

    with patch("pipeline.sources.rss.urllib.request.urlopen", return_value=mock_response) as urlopen_mock, \
         patch("pipeline.sources.rss.feedparser.parse") as mock_parse:
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
        request = urlopen_mock.call_args.args[0]
        assert request.get_header("User-agent").startswith("game-legal-briefing/")


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (urllib.error.HTTPError("https://example.com", 403, "forbidden", {}, None), SourceStatus.HTTP_403),
        (urllib.error.HTTPError("https://example.com", 404, "missing", {}, None), SourceStatus.HTTP_404),
        (socket.timeout("slow"), SourceStatus.TIMEOUT),
    ],
)
def test_fetch_feed_distinguishes_transport_failures(error, expected):
    source = SourceEntry(name="Test Feed", url="https://example.com/feed")
    with patch("pipeline.sources.rss.urllib.request.urlopen", side_effect=error):
        result = fetch_feed_result(source, "tier_a")
    assert result.status == expected
    assert result.article_count == 0


@pytest.mark.parametrize(
    ("feed", "expected"),
    [
        (SimpleNamespace(entries=[], bozo=False), SourceStatus.EMPTY),
        (SimpleNamespace(entries=[], bozo=True), SourceStatus.PARSE_ERROR),
    ],
)
def test_fetch_feed_distinguishes_empty_from_parse_error(feed, expected):
    response = MagicMock()
    response.read.return_value = b"<rss/>"
    source = SourceEntry(name="Test Feed", url="https://example.com/feed")
    with (
        patch("pipeline.sources.rss.urllib.request.urlopen", return_value=response),
        patch("pipeline.sources.rss.feedparser.parse", return_value=feed),
    ):
        result = fetch_feed_result(source, "tier_a")
    assert result.status == expected


def test_fetch_all_feeds_combines_tiers():
    source_a = SourceEntry(name="FeedA", url="https://a.com/feed")
    source_b = SourceEntry(name="FeedB", url="https://b.com/feed")

    def mock_fetch(source, tier):
        articles = [
            RawArticle(
                title=f"Article from {source.name}",
                url=f"https://{source.name}",
                source=source.name,
                description="",
                pub_date="2026-03-23",
            )
        ]
        return SourceFetchResult(source.name, tier, SourceStatus.OK, 1, articles)

    with patch("pipeline.sources.rss.fetch_feed_result", side_effect=mock_fetch):
        articles = fetch_all_feeds(tier_a=[source_a], tier_b=[source_b])
        assert len(articles) == 2


def test_fetch_all_feeds_with_report_tracks_empty_tier_a():
    source_a = SourceEntry(name="FeedA", url="https://a.com/feed")
    source_b = SourceEntry(name="FeedB", url="https://b.com/feed")

    def mock_fetch(source, tier):
        if source.name == "FeedA":
            return SourceFetchResult(source.name, tier, SourceStatus.EMPTY, 0, [])
        articles = [
            RawArticle(
                title=f"Article from {source.name}",
                url=f"https://{source.name}",
                source=source.name,
                description="",
                pub_date="2026-03-23",
            )
        ]
        return SourceFetchResult(source.name, tier, SourceStatus.OK, 1, articles)

    with patch("pipeline.sources.rss.fetch_feed_result", side_effect=mock_fetch):
        report = fetch_all_feeds_with_report(tier_a=[source_a], tier_b=[source_b], max_workers=1)
        assert len(report.articles) == 1
        assert report.tier_a_total == 1
        assert report.tier_a_empty == 1
        assert report.tier_a_failure_rate == 1.0


def test_one_worker_failure_does_not_discard_other_sources():
    source_a = SourceEntry(name="FeedA", url="https://a.com/feed")
    source_b = SourceEntry(name="FeedB", url="https://b.com/feed")
    article = RawArticle("Healthy", "https://b.com/1", "FeedB", "", "2026-03-23")

    def mock_fetch(source, tier):
        if source.name == "FeedA":
            raise RuntimeError("private worker detail")
        return SourceFetchResult(source.name, tier, SourceStatus.OK, 1, [article])

    with patch("pipeline.sources.rss.fetch_feed_result", side_effect=mock_fetch):
        report = fetch_all_feeds_with_report([source_a], [source_b], max_workers=2)

    assert report.articles == [article]
    assert [result.status for result in report.source_results] == [
        SourceStatus.WORKER_ERROR,
        SourceStatus.OK,
    ]
