from __future__ import annotations

import logging

from pipeline.llm.base import LLMProvider
from pipeline.sources.rss import RawArticle

logger = logging.getLogger(__name__)

SUMMARIZER_SYSTEM = "You are a legal analyst specializing in the game industry. Summarize in Korean."

SUMMARIZER_PROMPT = """다음 기사를 게임 산업 규제 브리핑용으로 한국어 3줄 요약해주세요.

제목: {title}
출처: {source}
내용: {description}

JSON만 반환하세요:
{{"summary_ko": ["첫째 줄", "둘째 줄", "셋째 줄"]}}"""


def summarize_article(article: RawArticle, llm: LLMProvider) -> list[str]:
    """Summarize one article in Korean, or fall back to the title."""
    prompt = SUMMARIZER_PROMPT.format(
        title=article.title,
        source=article.source,
        description=article.description[:3000],
    )

    try:
        payload = llm.generate_json(prompt, system=SUMMARIZER_SYSTEM)
        summary = payload.get("summary_ko", []) if isinstance(payload, dict) else []
        if isinstance(summary, str):
            summary = [summary]
        summary = [line.strip() for line in summary if str(line).strip()]
        return summary[:3] or [article.title]
    except Exception as exc:
        logger.warning("Summarization failed for '%s': %s", article.title, exc)
        return [article.title]
