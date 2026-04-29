from __future__ import annotations

import logging
import re
from dataclasses import replace
from datetime import datetime, timedelta

from pipeline.sources.rss import RawArticle

logger = logging.getLogger(__name__)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def keyword_filter(articles: list[RawArticle], keywords: list[str]) -> list[RawArticle]:
    """
    Keep only articles matching at least one keyword as a whole word.

    Uses regex word boundaries for whole-word matching, case-insensitive.
    Returns the input list unchanged if keywords are empty.
    """
    if not keywords:
        return articles

    pattern = re.compile(
        "|".join(r"\b" + re.escape(keyword) + r"\b" for keyword in keywords),
        re.IGNORECASE,
    )
    filtered = [
        article
        for article in articles
        if pattern.search(f"{article.title} {article.description}")
    ]
    logger.info(
        "Keyword filter (%d keywords) reduced %d articles to %d",
        len(keywords),
        len(articles),
        len(filtered),
    )
    return filtered


def _is_valid_pub_date(pub_date: str) -> bool:
    if not DATE_RE.fullmatch(pub_date or ""):
        return False
    try:
        datetime.strptime(pub_date, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def normalize_pub_dates(articles: list[RawArticle], default_date: str) -> list[RawArticle]:
    """Fill missing or invalid publication dates for downstream rendering."""
    normalized: list[RawArticle] = []
    changed = 0
    for article in articles:
        if _is_valid_pub_date(article.pub_date):
            normalized.append(article)
            continue
        normalized.append(replace(article, pub_date=default_date))
        changed += 1

    if changed:
        logger.info("Normalized %d missing/invalid publication dates to %s", changed, default_date)
    return normalized


def recency_filter(articles: list[RawArticle], max_age_days: int = 7) -> list[RawArticle]:
    """Drop articles older than max_age_days."""
    cutoff = (datetime.now() - timedelta(days=max_age_days)).strftime("%Y-%m-%d")
    filtered = [
        article for article in articles
        if _is_valid_pub_date(article.pub_date) and article.pub_date >= cutoff
    ]
    logger.info("Recency filter (%d days) reduced %d articles to %d", max_age_days, len(articles), len(filtered))
    return filtered
