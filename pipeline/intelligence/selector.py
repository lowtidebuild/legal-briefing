from __future__ import annotations

import logging

from pipeline.llm.base import LLMProvider
from pipeline.sources.rss import RawArticle

logger = logging.getLogger(__name__)

SELECTOR_PROMPT = """You are a legal analyst specializing in the game industry.

From the article list below, select the {top_n} entries most relevant to game law,
regulation, platform rules, privacy, antitrust, consumer protection, or policy.

Articles:
{articles_text}

Return JSON only:
{{"selected_indices": [0, 2, 4]}}"""


def select_top_articles(
    articles: list[RawArticle],
    llm: LLMProvider,
    top_n: int = 10,
    max_input_chars: int = 8000,
) -> list[RawArticle]:
    """Use the LLM to narrow the article list, with a deterministic fallback."""
    if len(articles) <= top_n:
        return articles

    lines: list[str] = []
    total_chars = 0
    for index, article in enumerate(articles):
        line = f"[{index}] {article.title} | {article.source} | {article.description[:180]}"
        if total_chars + len(line) > max_input_chars and lines:
            break
        lines.append(line)
        total_chars += len(line) + 1

    articles_text = "\n".join(lines)
    prompt = SELECTOR_PROMPT.format(top_n=top_n, articles_text=articles_text)

    try:
        result = llm.generate_json(prompt)
        indices = result.get("selected_indices", []) if isinstance(result, dict) else []
        selected = [articles[index] for index in indices if 0 <= index < len(articles)]
        if selected:
            logger.info("Selector kept %d of %d articles", len(selected), len(articles))
            return selected[:top_n]
    except Exception as exc:
        logger.warning("Selector failed, falling back to first %d articles: %s", top_n, exc)

    return articles[:top_n]

