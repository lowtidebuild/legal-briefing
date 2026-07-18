from __future__ import annotations

import logging
import socket
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from io import BytesIO
from types import SimpleNamespace

try:  # pragma: no cover - import availability depends on environment
    import feedparser
except ImportError:  # pragma: no cover - handled at runtime
    feedparser = SimpleNamespace(parse=None)

from pipeline.config import SourceEntry

FEED_TIMEOUT_SECONDS = 12
USER_AGENT = "game-legal-briefing/1.0 (+https://github.com/lowtidebuild/legal-briefing)"

logger = logging.getLogger(__name__)


@dataclass
class RawArticle:
    title: str
    url: str
    source: str
    description: str
    pub_date: str


class SourceStatus(str, Enum):
    OK = "ok"
    EMPTY = "empty"
    HTTP_403 = "http_403"
    HTTP_404 = "http_404"
    HTTP_OTHER = "http_other"
    TIMEOUT = "timeout"
    PARSE_ERROR = "parse_error"
    WORKER_ERROR = "worker_error"


@dataclass
class SourceFetchResult:
    source_name: str
    tier: str
    status: SourceStatus
    article_count: int
    articles: list[RawArticle]


@dataclass
class FeedFetchReport:
    articles: list[RawArticle]
    tier_a_total: int
    tier_a_empty: int
    source_results: list[SourceFetchResult] = field(default_factory=list)

    @property
    def tier_a_failure_rate(self) -> float:
        if self.tier_a_total == 0:
            return 0.0
        return self.tier_a_empty / self.tier_a_total


def _format_date(parsed_time) -> str:
    if parsed_time:
        return time.strftime("%Y-%m-%d", parsed_time)
    return ""


def _source_error_status(exc: Exception) -> SourceStatus:
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 403:
            return SourceStatus.HTTP_403
        if exc.code == 404:
            return SourceStatus.HTTP_404
        return SourceStatus.HTTP_OTHER
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return SourceStatus.TIMEOUT
    if isinstance(exc, urllib.error.URLError):
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            return SourceStatus.TIMEOUT
        return SourceStatus.HTTP_OTHER
    return SourceStatus.WORKER_ERROR


def _result(
    source: SourceEntry,
    tier: str,
    status: SourceStatus,
    articles: list[RawArticle] | None = None,
) -> SourceFetchResult:
    safe_articles = articles or []
    return SourceFetchResult(
        source_name=source.name,
        tier=tier,
        status=status,
        article_count=len(safe_articles),
        articles=safe_articles,
    )


def fetch_feed_result(source: SourceEntry, tier: str = "unknown") -> SourceFetchResult:
    """Fetch one RSS feed and return a sanitized, source-level result."""
    if getattr(feedparser, "parse", None) is None:
        logger.warning("feedparser is not installed; skipping %s", source.name)
        return _result(source, tier, SourceStatus.PARSE_ERROR)

    try:
        request = urllib.request.Request(source.url, headers={"User-Agent": USER_AGENT})
        response = urllib.request.urlopen(request, timeout=FEED_TIMEOUT_SECONDS)
        feed = feedparser.parse(BytesIO(response.read()))
    except Exception as exc:
        status = _source_error_status(exc)
        logger.warning("Feed fetch failed for %s [%s]", source.name, status.value)
        return _result(source, tier, status)

    entries = list(getattr(feed, "entries", []))
    if getattr(feed, "bozo", False) and not entries:
        logger.warning("Feed parse failed for %s [PARSE_ERROR]", source.name)
        return _result(source, tier, SourceStatus.PARSE_ERROR)

    articles: list[RawArticle] = []
    for entry in entries:
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
    status = SourceStatus.OK if articles else SourceStatus.EMPTY
    logger.info("Fetched %d articles from %s [%s]", len(articles), source.name, status.value)
    return _result(source, tier, status, articles)


def fetch_feed(source: SourceEntry) -> list[RawArticle]:
    """Compatibility wrapper returning only articles for one RSS feed."""
    return fetch_feed_result(source).articles


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
        results = [fetch_feed_result(source, tier) for source, tier in sources]
    else:
        results: list[SourceFetchResult | None] = [None for _ in sources]
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(fetch_feed_result, source, tier): index
                for index, (source, tier) in enumerate(sources)
            }
            for future in as_completed(futures):
                index = futures[future]
                source, tier = sources[index]
                try:
                    results[index] = future.result()
                except Exception:  # pragma: no cover - fetch_feed_result is defensive
                    logger.warning("Feed worker failed for %s [WORKER_ERROR]", source.name)
                    results[index] = _result(source, tier, SourceStatus.WORKER_ERROR)

    articles: list[RawArticle] = []
    tier_a_empty = 0
    source_results: list[SourceFetchResult] = []
    for (source, tier), maybe_result in zip(sources, results):
        result = maybe_result or _result(source, tier, SourceStatus.WORKER_ERROR)
        source_results.append(result)
        if tier == "tier_a" and result.status != SourceStatus.OK:
            tier_a_empty += 1
            logger.warning("tier_a source %s unhealthy [%s]", source.name, result.status.value)
        articles.extend(result.articles)
    logger.info("Collected %d raw articles total", len(articles))
    return FeedFetchReport(
        articles=articles,
        tier_a_total=len(tier_a),
        tier_a_empty=tier_a_empty,
        source_results=source_results,
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
