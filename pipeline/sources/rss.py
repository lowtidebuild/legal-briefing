from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from types import SimpleNamespace

try:  # pragma: no cover - import availability depends on environment
    import feedparser
except ImportError:  # pragma: no cover - handled at runtime
    feedparser = SimpleNamespace(parse=None)

from pipeline.config import SourceEntry

logger = logging.getLogger(__name__)


@dataclass
class RawArticle:
    title: str
    url: str
    source: str
    description: str
    pub_date: str


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
        feed = feedparser.parse(source.url)
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", source.name, exc)
        return []

    articles: list[RawArticle] = []
    for entry in getattr(feed, "entries", []):
        articles.append(
            RawArticle(
                title=getattr(entry, "title", "").strip(),
                url=getattr(entry, "link", "").strip(),
                source=source.name,
                description=(entry.get("summary", "") if hasattr(entry, "get") else ""),
                pub_date=_format_date(getattr(entry, "published_parsed", None)),
            )
        )
    logger.info("Fetched %d articles from %s", len(articles), source.name)
    return articles


def fetch_all_feeds(tier_a: list[SourceEntry], tier_b: list[SourceEntry]) -> list[RawArticle]:
    """Fetch all configured RSS feeds."""
    articles: list[RawArticle] = []
    for source in tier_a:
        result = fetch_feed(source)
        if not result:
            logger.warning("tier_a source %s returned no articles", source.name)
        articles.extend(result)
    for source in tier_b:
        articles.extend(fetch_feed(source))
    logger.info("Collected %d raw articles total", len(articles))
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

