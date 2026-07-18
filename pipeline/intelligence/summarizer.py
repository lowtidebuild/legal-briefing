from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from pipeline.intelligence.batch import run_validated_batch
from pipeline.intelligence.dedup import url_hash
from pipeline.llm.base import LLMProvider
from pipeline.sources.rss import RawArticle

logger = logging.getLogger(__name__)

SUMMARIZER_SYSTEM = "You are a legal analyst specializing in the game industry. Summarize in Korean."

SUMMARIZER_PROMPT = """다음 기사를 게임 산업 규제 브리핑용으로 한국어 3줄 요약해주세요.
또한 기사 제목을 자연스러운 한국어로 번역해주세요.

규칙:
- 인명, 회사명, 기관명은 한글(원문) 병기 (예: 밸브(Valve), 닌텐도(Nintendo), 연방거래위원회(FTC))
- 널리 알려진 영문 약어는 영어만 표기해도 됨 (예: EU, GDPR, COPPA)
- 제목과 요약 모두 이 규칙 적용
- 1줄: 무슨 일인지, 2줄: 왜 중요한지, 3줄: 게임 산업 실무 시사점

제목: {title}
출처: {source}
내용: {description}

JSON만 반환하세요:
{{"title_ko": "한국어 제목", "summary_ko": ["첫째 줄", "둘째 줄", "셋째 줄"]}}"""

SUMMARIZER_PROMPT_KO_ONLY = """다음 한국어 기사를 게임 산업 규제 브리핑용으로 한국어 3줄 요약해주세요.

규칙:
- 인명, 회사명, 기관명은 한글(원문) 병기 (예: 밸브(Valve), 닌텐도(Nintendo), 연방거래위원회(FTC))
- 널리 알려진 영문 약어는 영어만 표기해도 됨 (예: EU, GDPR, COPPA)
- 1줄: 무슨 일인지, 2줄: 왜 중요한지, 3줄: 게임 산업 실무 시사점

제목: {title}
출처: {source}
내용: {description}

JSON만 반환하세요:
{{"summary_ko": ["첫째 줄", "둘째 줄", "셋째 줄"]}}"""

KOREAN_SOURCES = {
    "IT Chosun",
    "ZDNet Korea",
    "ETNews",
    "게임메카",
    "디스이즈게임",
    "인벤",
    "게임톡",
    "DDaily",
    "GameChosun",
    "문화체육관광부",
    "게임물관리위원회",
    "공정거래위원회",
}

SUMMARY_BATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "title_ko": {"type": "string"},
                    "summary_ko": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["item_id", "title_ko", "summary_ko"],
            },
        }
    },
    "required": ["results"],
}

SUMMARY_BATCH_PROMPT = """다음 모든 기사를 게임 산업 규제 브리핑용으로 한국어 요약하세요.
각 item_id를 빠짐없이 그대로 반환하고, 입력 순서에 의존하지 마세요.

규칙:
- 기사마다 자연스러운 한국어 제목과 정확히 3줄 이내의 요약을 작성
- 인명, 회사명, 기관명은 한글(원문) 병기
- 1줄: 무슨 일인지, 2줄: 왜 중요한지, 3줄: 게임 산업 실무 시사점
- is_korean_source가 true이면 title_ko에 원래 제목을 그대로 사용

Items JSON:
{items_json}

JSON만 반환하세요: {{"results": [...]}}"""


@dataclass
class SummaryResult:
    title_ko: str
    summary_ko: list[str]


def _summary_from_payload(article: RawArticle, payload: dict) -> SummaryResult:
    is_korean_source = article.source in KOREAN_SOURCES
    title_ko = article.title if is_korean_source else str(payload.get("title_ko", "")).strip()
    summary = payload.get("summary_ko", [])
    if isinstance(summary, str):
        summary = [summary]
    if not isinstance(summary, list):
        summary = []
    summary = [str(line).strip() for line in summary if str(line).strip()]
    return SummaryResult(
        title_ko=title_ko,
        summary_ko=summary[:3] or [article.title],
    )


def summarize_article(article: RawArticle, llm: LLMProvider) -> SummaryResult:
    """Summarize one article in Korean with a translated title."""
    is_korean_source = article.source in KOREAN_SOURCES
    prompt_template = SUMMARIZER_PROMPT_KO_ONLY if is_korean_source else SUMMARIZER_PROMPT
    prompt = prompt_template.format(
        title=article.title,
        source=article.source,
        description=article.description[:3000],
    )

    try:
        payload = llm.generate_json(prompt, system=SUMMARIZER_SYSTEM)
        if not isinstance(payload, dict):
            return SummaryResult(title_ko=article.title if is_korean_source else "", summary_ko=[article.title])

        return _summary_from_payload(article, payload)
    except Exception as exc:
        logger.warning("Summarization failed for '%s': %s", article.title, exc)
        return SummaryResult(title_ko=article.title if is_korean_source else "", summary_ko=[article.title])


def summarize_articles(
    articles: list[RawArticle],
    llm: LLMProvider,
    batch_size: int = 10,
) -> list[SummaryResult]:
    """Summarize articles in validated batches while preserving input order."""
    if not articles:
        return []
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    from pipeline.llm.offline import OfflineLLMProvider

    if isinstance(llm, OfflineLLMProvider):
        return [summarize_article(article, llm) for article in articles]

    results: list[SummaryResult] = []
    for start in range(0, len(articles), batch_size):
        batch = articles[start : start + batch_size]

        def build_prompt(prompt_items: list[RawArticle]) -> str:
            items = [
                {
                    "item_id": url_hash(article.url),
                    "title": article.title,
                    "source": article.source,
                    "is_korean_source": article.source in KOREAN_SOURCES,
                    "description": article.description[:3000],
                }
                for article in prompt_items
            ]
            return SUMMARY_BATCH_PROMPT.format(
                items_json=json.dumps(items, ensure_ascii=False),
            )

        results.extend(
            run_validated_batch(
                items=batch,
                llm=llm,
                item_id=lambda article: url_hash(article.url),
                build_prompt=build_prompt,
                schema=SUMMARY_BATCH_SCHEMA,
                parse_item=_summary_from_payload,
                system=SUMMARIZER_SYSTEM,
            )
        )
    return results
