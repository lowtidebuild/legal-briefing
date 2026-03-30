from __future__ import annotations

import logging

from pipeline.sources.rss import RawArticle

logger = logging.getLogger(__name__)


def keyword_filter(articles: list[RawArticle], keywords: list[str]) -> list[RawArticle]:
    """Keep only articles matching one of the configured keywords."""
    if not keywords:
        return articles

    lowered_keywords = [keyword.lower() for keyword in keywords]
    filtered = [
        article
        for article in articles
        if any(keyword in f"{article.title} {article.description}".lower() for keyword in lowered_keywords)
    ]
    logger.info("Keyword filter reduced %d articles to %d", len(articles), len(filtered))
    return filtered

