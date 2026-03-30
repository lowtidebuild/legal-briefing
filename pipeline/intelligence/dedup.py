from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field

from pipeline.sources.rss import RawArticle

logger = logging.getLogger(__name__)

STOP_WORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "for",
    "of",
    "to",
    "in",
    "on",
    "with",
    "by",
    "new",
    "update",
    "latest",
    "games",
    "game",
    "gaming",
}


@dataclass
class DedupEntry:
    event_key: str
    url_hash: str
    date: str


@dataclass
class DedupIndex:
    entries: list[DedupEntry] = field(default_factory=list)
    schema_version: int = 1
    retention_days: int = 30


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def topic_tokens_hash(title: str) -> str:
    words = re.findall(r"\w+", title.lower())
    meaningful = sorted(set(words) - STOP_WORDS)
    raw = " ".join(meaningful) if meaningful else title.strip().lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def compute_event_key(jurisdiction: str, actors: list[str], object_: str, action: str) -> str:
    raw = "|".join(
        [
            jurisdiction.lower(),
            ",".join(sorted(actor.lower() for actor in actors)),
            object_.lower(),
            action.lower(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def deduplicate_articles(articles: list[RawArticle], index: DedupIndex) -> list[RawArticle]:
    """Deduplicate by URL and headline topic token fingerprint."""
    existing_url_hashes = {entry.url_hash for entry in index.entries}
    seen_url_hashes: set[str] = set()
    url_stage: list[RawArticle] = []
    for article in articles:
        fingerprint = url_hash(article.url)
        if fingerprint in existing_url_hashes or fingerprint in seen_url_hashes:
            continue
        seen_url_hashes.add(fingerprint)
        url_stage.append(article)

    seen_topic_hashes: set[str] = set()
    topic_stage: list[RawArticle] = []
    for article in url_stage:
        fingerprint = topic_tokens_hash(article.title)
        if fingerprint in seen_topic_hashes:
            continue
        seen_topic_hashes.add(fingerprint)
        topic_stage.append(article)

    logger.info("Dedup reduced %d articles to %d", len(articles), len(topic_stage))
    return topic_stage

