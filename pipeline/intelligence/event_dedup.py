from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from pipeline.intelligence.classifier import ClassificationResult
from pipeline.intelligence.dedup import compute_event_fingerprint, topic_tokens_hash
from pipeline.sources.rss import RawArticle

logger = logging.getLogger(__name__)


@dataclass
class ClassifiedArticle:
    article: RawArticle
    classification: ClassificationResult
    event_fingerprint: str


def _year_bucket(pub_date: str) -> str:
    try:
        parsed = datetime.strptime(pub_date, "%Y-%m-%d")
    except (TypeError, ValueError):
        return ""
    quarter = ((parsed.month - 1) // 3) + 1
    return f"{parsed.year}q{quarter}"


def _normalized_event_key(classification: ClassificationResult) -> str:
    return classification.event_key.strip().lower()


def build_classified_article(
    article: RawArticle,
    classification: ClassificationResult,
) -> ClassifiedArticle:
    event = classification.event
    if not event.actors and not event.object and not event.action:
        fingerprint = f"title:{topic_tokens_hash(article.title)}:{_year_bucket(article.pub_date)}"
    else:
        fingerprint = compute_event_fingerprint(
            jurisdiction=event.jurisdiction.value,
            actors=event.actors,
            object_=event.object,
            action=event.action,
            year_bucket=_year_bucket(article.pub_date),
        )
    return ClassifiedArticle(
        article=article,
        classification=classification,
        event_fingerprint=fingerprint,
    )


def dedup_classified_articles(
    items: list[ClassifiedArticle],
    existing_event_keys: set[str],
    existing_event_fingerprints: set[str],
) -> list[ClassifiedArticle]:
    """Drop already-seen events before running expensive summarization."""
    normalized_existing_keys = {key.strip().lower() for key in existing_event_keys if key}
    normalized_existing_fingerprints = {
        fingerprint.strip().lower()
        for fingerprint in existing_event_fingerprints
        if fingerprint
    }
    seen_keys: set[str] = set()
    seen_fingerprints: set[str] = set()
    survivors: list[ClassifiedArticle] = []

    for item in items:
        event_key = _normalized_event_key(item.classification)
        fingerprint = item.event_fingerprint.strip().lower()

        if event_key and (event_key in normalized_existing_keys or event_key in seen_keys):
            logger.info(
                "EventKey dedup: skipping '%s' (key: %s)",
                item.article.title[:50],
                event_key,
            )
            continue

        if fingerprint and (
            fingerprint in normalized_existing_fingerprints
            or fingerprint in seen_fingerprints
        ):
            logger.info(
                "Event fingerprint dedup: skipping '%s' (fingerprint: %s)",
                item.article.title[:50],
                fingerprint,
            )
            continue

        if event_key:
            seen_keys.add(event_key)
        if fingerprint:
            seen_fingerprints.add(fingerprint)
        survivors.append(item)

    if len(items) != len(survivors):
        logger.info("Event dedup removed %d duplicate events", len(items) - len(survivors))
    return survivors
