from __future__ import annotations

import logging
import re
from collections import Counter
from collections import OrderedDict
from urllib.parse import urlparse

from pipeline.llm.base import LLMProvider
from pipeline.sources.rss import RawArticle

logger = logging.getLogger(__name__)

SELECTOR_PROMPT = """You are a legal analyst specializing in the game industry.

From the article list below, select EXACTLY {top_n} entries most relevant to game law,
regulation, platform rules, privacy, antitrust, consumer protection, or policy.

Selection criteria, in priority order:
1. Direct game industry impact: games, esports, virtual goods, in-game purchases,
   age rating, game platforms, app stores, online safety, monetization, or player data.
2. Regulatory/legal substance over general news: enforcement actions, legislation,
   litigation, official guidance, platform policy, security incidents, or practitioner analysis.
3. Source diversity: use different outlets across trade press, practitioner publications,
   regulators, tech policy, and security press.
4. No single domain should account for more than {max_per_domain} of {top_n}
   unless there are not enough relevant alternatives.

Practitioner analysis and regulatory body announcements are HIGH VALUE when they tie
to the topics above. Generic law firm deal announcements, awards, hires, and marketing
posts are LOW VALUE unless they directly affect game industry regulation.

You MUST return exactly {top_n} indices.

Articles:
{articles_text}

Return JSON only:
{{"selected_indices": [0, 2, 4, ...]}}"""


def _domain_of(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def _enforce_domain_cap(
    selected: list[RawArticle],
    pool: list[RawArticle],
    top_n: int,
    max_per_domain: int,
) -> list[RawArticle]:
    """Prefer a domain cap, then relax it only if needed to keep top_n filled."""
    if max_per_domain <= 0:
        return selected[:top_n]

    capped: list[RawArticle] = []
    domain_counts: Counter[str] = Counter()
    selected_ids: set[int] = set()

    def add(article: RawArticle, enforce_cap: bool) -> bool:
        article_id = id(article)
        if article_id in selected_ids:
            return False
        domain = _domain_of(article.url)
        if enforce_cap and domain_counts[domain] >= max_per_domain:
            return False
        domain_counts[domain] += 1
        capped.append(article)
        selected_ids.add(article_id)
        return True

    for article in selected:
        add(article, enforce_cap=True)

    for article in pool:
        if len(capped) >= top_n:
            break
        add(article, enforce_cap=True)

    if len(capped) < top_n:
        before_relax = len(capped)
        for article in selected + pool:
            if len(capped) >= top_n:
                break
            add(article, enforce_cap=False)
        if len(capped) > before_relax:
            logger.info(
                "Selector domain cap relaxed to keep %d articles (strict cap kept %d)",
                len(capped),
                before_relax,
            )

    return capped[:top_n]


def _keyword_score(article: RawArticle, keywords: list[str]) -> int:
    if not keywords:
        return 0
    pattern = re.compile(
        "|".join(r"\b" + re.escape(keyword) + r"\b" for keyword in keywords),
        re.IGNORECASE,
    )
    return len(pattern.findall(f"{article.title} {article.description}"))


def _diversify_for_selector(
    articles: list[RawArticle],
    keywords: list[str] | None = None,
) -> list[RawArticle]:
    """Order selector input by keyword signal while round-robining domains."""
    if not articles:
        return []

    groups: OrderedDict[str, list[tuple[int, int, RawArticle]]] = OrderedDict()
    for index, article in enumerate(articles):
        domain = _domain_of(article.url)
        groups.setdefault(domain, []).append((_keyword_score(article, keywords or []), index, article))

    first_index = {
        domain: min(index for _, index, _ in scored_articles)
        for domain, scored_articles in groups.items()
    }
    for scored_articles in groups.values():
        scored_articles.sort(key=lambda item: (-item[0], item[1]))

    domains = sorted(
        groups,
        key=lambda domain: (-groups[domain][0][0], first_index[domain]),
    )
    ranked: list[RawArticle] = []
    while any(groups[domain] for domain in domains):
        for domain in domains:
            if groups[domain]:
                ranked.append(groups[domain].pop(0)[2])
    return ranked


def select_top_articles(
    articles: list[RawArticle],
    llm: LLMProvider,
    top_n: int = 10,
    max_input_chars: int = 8000,
    max_per_domain: int = 2,
    keywords: list[str] | None = None,
) -> list[RawArticle]:
    """Use the LLM to narrow the article list, with a deterministic fallback."""
    if len(articles) <= top_n:
        return articles

    selector_pool = _diversify_for_selector(articles, keywords)
    lines: list[str] = []
    total_chars = 0
    visible_count = 0
    for index, article in enumerate(selector_pool):
        line = f"[{index}] {article.title} | {article.source} | {article.description[:180]}"
        if total_chars + len(line) > max_input_chars and lines:
            break
        lines.append(line)
        total_chars += len(line) + 1
        visible_count += 1

    if visible_count < len(selector_pool):
        logger.info(
            "Selector input truncated: %d -> %d articles",
            len(selector_pool),
            visible_count,
        )

    articles_text = "\n".join(lines)
    prompt = SELECTOR_PROMPT.format(
        top_n=top_n,
        max_per_domain=max_per_domain,
        articles_text=articles_text,
    )

    try:
        result = llm.generate_json(prompt)
        indices = result.get("selected_indices", []) if isinstance(result, dict) else []
        selected = [selector_pool[index] for index in indices if 0 <= index < visible_count]
        if selected:
            capped = _enforce_domain_cap(selected, selector_pool, top_n, max_per_domain)
            logger.info(
                "Selector kept %d of %d articles (LLM valid indices: %d)",
                len(capped),
                len(selector_pool),
                len(selected),
            )
            return capped
    except Exception as exc:
        logger.warning("Selector failed, falling back to first %d articles: %s", top_n, exc)

    return _enforce_domain_cap(selector_pool[:top_n], selector_pool, top_n, max_per_domain)
