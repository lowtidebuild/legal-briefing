from __future__ import annotations

import logging
import time
import urllib.request
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from types import SimpleNamespace

try:  # pragma: no cover - import availability depends on environment
    import feedparser
except ImportError:  # pragma: no cover - handled at runtime
    feedparser = SimpleNamespace(parse=None)

from pipeline.config import SourceEntry

FEED_TIMEOUT_SECONDS = 30

logger = logging.getLogger(__name__)


@dataclass
class RawArticle:
    title: str
    url: str
    source: str
    description: str
    pub_date: str


@dataclass
class FeedFetchReport:
    articles: list[RawArticle]
    tier_a_total: int
    tier_a_empty: int

    @property
    def tier_a_failure_rate(self) -> float:
        if self.tier_a_total == 0:
            return 0.0
        return self.tier_a_empty / self.tier_a_total


def _format_date(parsed_time) -> str:
    if parsed_time:
        return time.strftime("%Y-%m-%d", parsed_time)
    return ""


def fetch_feed(source: SourceEntry) -> list[RawArticle]:
    """Fetch and parse one RSS feed, returning an empty list on failure."""
    if getattr(feedparser, "parse", None) is None:
        logger.warning("feedparser is not installed; skipping %s", source.name)
        return []

    try:
        response = urllib.request.urlopen(source.url, timeout=FEED_TIMEOUT_SECONDS)
        feed = feedparser.parse(BytesIO(response.read()))
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", source.name, exc)
        return []

    articles: list[RawArticle] = []
    for entry in getattr(feed, "entries", []):
        url = getattr(entry, "link", "").strip()
        if not url:
            continue
        articles.append(
            RawArticle(
                title=getattr(entry, "title", "").strip(),
                url=url,
                source=source.name,
                description=(entry.get("summary", "") if hasattr(entry, "get") else ""),
                pub_date=_format_date(getattr(entry, "published_parsed", None)),
            )
        )
    logger.info("Fetched %d articles from %s", len(articles), source.name)
    return articles


def fetch_all_feeds_with_report(
    tier_a: list[SourceEntry],
    tier_b: list[SourceEntry],
    max_workers: int = 8,
) -> FeedFetchReport:
    """Fetch all configured RSS feeds and return basic health stats."""
    sources = [(source, "tier_a") for source in tier_a] + [(source, "tier_b") for source in tier_b]
    if not sources:
        logger.info("Collected 0 raw articles total")
        return FeedFetchReport(articles=[], tier_a_total=0, tier_a_empty=0)

    if max_workers <= 1:
        results = [fetch_feed(source) for source, _ in sources]
    else:
        results: list[list[RawArticle]] = [[] for _ in sources]
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(fetch_feed, source): index
                for index, (source, _) in enumerate(sources)
            }
            for future in as_completed(futures):
                index = futures[future]
                source, _ = sources[index]
                try:
                    results[index] = future.result()
                except Exception as exc:  # pragma: no cover - fetch_feed is defensive
                    logger.warning("Feed worker failed for %s: %s", source.name, exc)

    articles: list[RawArticle] = []
    tier_a_empty = 0
    for (source, tier), result in zip(sources, results):
        if tier == "tier_a" and not result:
            tier_a_empty += 1
            logger.warning("tier_a source %s returned no articles", source.name)
        articles.extend(result)
    logger.info("Collected %d raw articles total", len(articles))
    return FeedFetchReport(
        articles=articles,
        tier_a_total=len(tier_a),
        tier_a_empty=tier_a_empty,
    )


def fetch_all_feeds(
    tier_a: list[SourceEntry],
    tier_b: list[SourceEntry],
    max_workers: int = 8,
) -> list[RawArticle]:
    """Fetch all configured RSS feeds."""
    report = fetch_all_feeds_with_report(tier_a=tier_a, tier_b=tier_b, max_workers=max_workers)
    articles = report.articles
    return articles


def sample_articles() -> list[RawArticle]:
    """Local seed data for dry runs and first-time UI development."""
    return [
        RawArticle(
            title="EU lawmakers advance transparency rules for loot boxes",
            url="https://example.com/eu-loot-box",
            source="Sample Feed",
            description="European lawmakers moved a disclosure-focused proposal forward for loot box mechanics in video games.",
            pub_date="2026-03-30",
        ),
        RawArticle(
            title="Korea updates mobile game age-rating guidance",
            url="https://example.com/kr-age-rating",
            source="Sample Feed",
            description="South Korean regulators published updated age-rating expectations for mobile games and in-app content.",
            pub_date="2026-03-30",
        ),
        RawArticle(
            title="FTC settlement highlights children's privacy issues in gaming",
            url="https://example.com/us-privacy",
            source="Sample Feed",
            description="A new U.S. enforcement action puts COPPA-style data collection and design choices under scrutiny for game services.",
            pub_date="2026-03-30",
        ),
    ]
