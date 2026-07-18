from __future__ import annotations

import hashlib
import logging
import ntpath
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

from pipeline.sources.rss import RawArticle

logger = logging.getLogger(__name__)

EVENT_KEY_PATTERN = re.compile(r"\A[a-z0-9_]{1,120}\Z")
_EVENT_TIME_SUFFIX = re.compile(r"_(?:20\d{2}(?:q[1-4])?|ongoing)\Z")

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
    event_fingerprint: str = ""


@dataclass
class DedupIndex:
    entries: list[DedupEntry] = field(default_factory=list)
    schema_version: int = 2
    retention_days: int = 30


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def topic_tokens_hash(title: str) -> str:
    words = re.findall(r"\w+", title.lower())
    meaningful = sorted(set(words) - STOP_WORDS)
    raw = " ".join(meaningful) if meaningful else title.strip().lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _normalize_token(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", "", s)
    return re.sub(r"\s+", "_", s)


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


def event_year_bucket(pub_date: str) -> str:
    """Return the publication quarter used in newly generated event keys."""
    try:
        parsed = datetime.strptime(pub_date, "%Y-%m-%d")
    except (TypeError, ValueError):
        return ""
    quarter = ((parsed.month - 1) // 3) + 1
    return f"{parsed.year}q{quarter}"


def is_safe_event_key(event_key: object) -> bool:
    """Return whether a stored key is safe to use as a single filename stem."""
    return isinstance(event_key, str) and EVENT_KEY_PATTERN.fullmatch(event_key) is not None


def _has_path_control(value: str) -> bool:
    return (
        "/" in value
        or "\\" in value
        or "\x00" in value
        or ".." in value
        or ntpath.isabs(value)
    )


def canonicalize_event_key(
    raw_event_key: object,
    pub_date: str,
    fallback_event_key: str,
) -> str:
    """Convert an LLM event key into a bounded, path-safe canonical key.

    The LLM-provided time suffix is discarded. A publication quarter is added
    from trusted article metadata so the model cannot invent the key's date.
    Path-control input and malformed values use the deterministic hash fallback.
    """
    bucket = event_year_bucket(pub_date)
    suffix = f"_{bucket}" if bucket else ""

    fallback = str(fallback_event_key).strip().lower()
    if not is_safe_event_key(fallback) or len(fallback) + len(suffix) > 120:
        fallback = hashlib.sha256(fallback.encode("utf-8")).hexdigest()[:16]
    fallback_candidate = f"{fallback}{suffix}"
    if not is_safe_event_key(fallback_candidate):
        raise ValueError("Unable to construct a safe fallback event_key")

    raw = "" if raw_event_key is None else str(raw_event_key).strip()
    normalized = unicodedata.normalize("NFKC", raw)
    if not raw or _has_path_control(raw) or _has_path_control(normalized):
        return fallback_candidate

    base = normalized.lower()
    base = re.sub(r"[^a-z0-9_]+", "_", base)
    base = re.sub(r"_+", "_", base).strip("_")
    base = _EVENT_TIME_SUFFIX.sub("", base).strip("_")
    candidate = f"{base}{suffix}"
    if not base or not is_safe_event_key(candidate):
        return fallback_candidate
    return candidate


def compute_event_fingerprint(
    jurisdiction: str,
    actors: list[str],
    object_: str,
    action: str,
    year_bucket: str,
) -> str:
    """Compute a deterministic event fingerprint for cross-source dedup."""
    parts = [
        jurisdiction.lower(),
        ",".join(sorted(_normalize_token(actor) for actor in actors if actor)),
        _normalize_token(object_),
        _normalize_token(action),
        year_bucket.lower(),
    ]
    raw = "|".join(parts)
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
