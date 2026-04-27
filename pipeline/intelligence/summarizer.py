from __future__ import annotations

import logging
from dataclasses import dataclass

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


@dataclass
class SummaryResult:
    title_ko: str
    summary_ko: list[str]


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

        title_ko = article.title if is_korean_source else str(payload.get("title_ko", "")).strip()
        summary = payload.get("summary_ko", [])
        if isinstance(summary, str):
            summary = [summary]
        summary = [line.strip() for line in summary if str(line).strip()]
        return SummaryResult(
            title_ko=title_ko,
            summary_ko=summary[:3] or [article.title],
        )
    except Exception as exc:
        logger.warning("Summarization failed for '%s': %s", article.title, exc)
        return SummaryResult(title_ko=article.title if is_korean_source else "", summary_ko=[article.title])
