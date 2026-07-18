from __future__ import annotations

import json
import logging
import re
from collections import Counter, OrderedDict
from dataclasses import dataclass
from urllib.parse import urlparse

from pipeline.intelligence.dedup import url_hash
from pipeline.llm.base import LLMProvider
from pipeline.sources.rss import RawArticle

logger = logging.getLogger(__name__)

LEGAL_HOOKS = {
    "litigation",
    "enforcement",
    "legislation",
    "regulation",
    "official_guidance",
    "platform_policy",
    "privacy_security_incident",
    "ip_dispute",
    "labor_employment",
    "antitrust_transaction",
    "consumer_monetization_compliance",
}

DEFAULT_GAME_SIGNALS = [
    "game",
    "gaming",
    "esports",
    "app store",
    "loot box",
    "virtual goods",
    "in-game purchase",
    "steam",
    "roblox",
    "playstation",
    "xbox",
    "nintendo",
]

DEFAULT_LEGAL_SIGNALS = [
    "lawsuit",
    "court",
    "enforcement",
    "regulation",
    "legislation",
    "antitrust",
    "privacy",
    "copyright",
    "patent",
    "labor",
    "platform policy",
    "settlement",
    "fine",
    "guidance",
]

SELECTOR_SCHEMA = {
    "type": "object",
    "properties": {
        "selected": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "is_legally_relevant": {"type": "boolean"},
                    "legal_hook": {"type": "string", "enum": sorted(LEGAL_HOOKS)},
                },
                "required": ["item_id", "is_legally_relevant", "legal_hook"],
            },
        }
    },
    "required": ["selected"],
}

SELECTOR_PROMPT = """You are a legal editor for the game industry.

Select up to {top_n} articles with a concrete game-industry legal nexus. Return
fewer or zero when relevance is insufficient. AI, product features, production
efficiency, market forecasts, and marketing are not legal hooks by themselves.

For every selected item, set is_legally_relevant=true and choose exactly one
allowed legal_hook. Do not select an item merely to fill the quota. Prefer source
diversity; code will enforce at most {max_per_domain} items per domain.

Allowed legal_hook values: {legal_hooks}

Items JSON:
{items_json}

Return JSON only as {{"selected": [...]}}."""


@dataclass(frozen=True)
class SelectionResult:
    articles: list[RawArticle]
    legal_hooks: dict[str, str]
    degraded: bool = False


def _domain_of(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def _enforce_domain_cap(
    selected: list[RawArticle],
    top_n: int,
    max_per_domain: int,
) -> list[RawArticle]:
    """Apply the domain cap only to selected articles; never backfill."""
    if max_per_domain <= 0:
        return selected[:top_n]

    capped: list[RawArticle] = []
    domain_counts: Counter[str] = Counter()
    seen_urls: set[str] = set()
    for article in selected:
        if article.url in seen_urls:
            continue
        domain = _domain_of(article.url)
        if domain_counts[domain] >= max_per_domain:
            continue
        seen_urls.add(article.url)
        domain_counts[domain] += 1
        capped.append(article)
        if len(capped) >= top_n:
            break
    return capped


def _contains_signal(text: str, signals: list[str]) -> bool:
    return any(
        re.search(r"\b" + re.escape(signal) + r"\b", text, flags=re.IGNORECASE)
        for signal in signals
        if signal
    )


def _legal_hook_for(article: RawArticle, game_signals: list[str], legal_signals: list[str]) -> str | None:
    text = f"{article.title} {article.description}"
    game_source = article.source in {"게임물관리위원회", "GameDeveloper", "GamesIndustry.biz"}
    if not game_source and not _contains_signal(text, game_signals):
        return None
    if not _contains_signal(text, legal_signals):
        return None

    lowered = text.casefold()
    hook_signals = [
        ("antitrust_transaction", ("antitrust", "competition authority", "merger review")),
        ("labor_employment", ("labor", "employment", "union", "layoff")),
        ("privacy_security_incident", ("privacy", "data breach", "security incident", "coppa", "gdpr")),
        ("ip_dispute", ("copyright", "patent", "trademark", "infringement", "dmca")),
        ("consumer_monetization_compliance", ("loot box", "in-game purchase", "monetization", "gambling")),
        ("platform_policy", ("platform policy", "app store policy", "store rule")),
        ("enforcement", ("enforcement", "fine", "settlement", "probe")),
        ("litigation", ("lawsuit", "litigation", "court", "judge")),
        ("legislation", ("legislation", "bill", "act", "law")),
        ("official_guidance", ("guidance", "official notice")),
        ("regulation", ("regulation", "regulatory", "compliance")),
    ]
    for hook, signals in hook_signals:
        if any(signal in lowered for signal in signals):
            return hook
    return None


def _keyword_score(article: RawArticle, keywords: list[str]) -> int:
    text = f"{article.title} {article.description}"
    return sum(1 for keyword in keywords if _contains_signal(text, [keyword]))


def _diversify_for_selector(
    articles: list[RawArticle],
    keywords: list[str] | None = None,
) -> list[RawArticle]:
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

    domains = sorted(groups, key=lambda domain: (-groups[domain][0][0], first_index[domain]))
    ranked: list[RawArticle] = []
    while any(groups[domain] for domain in domains):
        for domain in domains:
            if groups[domain]:
                ranked.append(groups[domain].pop(0)[2])
    return ranked


def _deterministic_selection(
    articles: list[RawArticle],
    top_n: int,
    max_per_domain: int,
    game_signals: list[str],
    legal_signals: list[str],
) -> SelectionResult:
    hooks = {
        article.url: hook
        for article in articles
        if (hook := _legal_hook_for(article, game_signals, legal_signals)) is not None
    }
    selected = _enforce_domain_cap(
        [article for article in articles if article.url in hooks],
        top_n,
        max_per_domain,
    )
    return SelectionResult(
        articles=selected,
        legal_hooks={article.url: hooks[article.url] for article in selected},
        degraded=True,
    )


def select_articles(
    articles: list[RawArticle],
    llm: LLMProvider,
    top_n: int = 10,
    max_input_chars: int = 8000,
    max_per_domain: int = 2,
    keywords: list[str] | None = None,
    game_signals: list[str] | None = None,
    legal_signals: list[str] | None = None,
) -> SelectionResult:
    """Select zero to top_n articles with validated legal hooks."""
    if not articles or top_n <= 0:
        return SelectionResult(articles=[], legal_hooks={})

    game_signals = game_signals or DEFAULT_GAME_SIGNALS
    legal_signals = legal_signals or DEFAULT_LEGAL_SIGNALS
    ranking_signals = keywords or [*game_signals, *legal_signals]
    selector_pool = _diversify_for_selector(articles, ranking_signals)

    visible: list[RawArticle] = []
    items: list[dict] = []
    total_chars = 0
    for article in selector_pool:
        item = {
            "item_id": url_hash(article.url),
            "title": article.title,
            "source": article.source,
            "description": article.description[:240],
        }
        encoded = json.dumps(item, ensure_ascii=False)
        if visible and total_chars + len(encoded) > max_input_chars:
            break
        visible.append(article)
        items.append(item)
        total_chars += len(encoded)

    if len(visible) < len(selector_pool):
        logger.info("Selector input truncated: %d -> %d articles", len(selector_pool), len(visible))

    prompt = SELECTOR_PROMPT.format(
        top_n=top_n,
        max_per_domain=max_per_domain,
        legal_hooks=", ".join(sorted(LEGAL_HOOKS)),
        items_json=json.dumps(items, ensure_ascii=False),
    )
    by_id = {url_hash(article.url): article for article in visible}

    try:
        payload = llm.generate_json_schema(prompt, SELECTOR_SCHEMA)
        if not isinstance(payload, dict) or not isinstance(payload.get("selected"), list):
            raise ValueError("Selector response must contain a selected array")

        selected: list[RawArticle] = []
        hooks: dict[str, str] = {}
        seen_ids: set[str] = set()
        for entry in payload["selected"]:
            if not isinstance(entry, dict):
                raise ValueError("Selector entry must be an object")
            item_id = entry.get("item_id")
            hook = entry.get("legal_hook")
            if item_id not in by_id or item_id in seen_ids:
                raise ValueError("Selector returned an unknown or duplicate item_id")
            seen_ids.add(item_id)
            if entry.get("is_legally_relevant") is not True:
                continue
            if hook not in LEGAL_HOOKS:
                raise ValueError("Selector returned an invalid legal_hook")
            article = by_id[item_id]
            selected.append(article)
            hooks[article.url] = hook

        capped = _enforce_domain_cap(selected, top_n, max_per_domain)
        logger.info("Selector kept %d of %d candidate articles", len(capped), len(selector_pool))
        return SelectionResult(
            articles=capped,
            legal_hooks={article.url: hooks[article.url] for article in capped},
        )
    except Exception as exc:
        logger.warning("Selector failed; using strict deterministic legal fallback: %s", exc)
        return _deterministic_selection(
            selector_pool,
            top_n,
            max_per_domain,
            game_signals,
            legal_signals,
        )


def select_top_articles(
    articles: list[RawArticle],
    llm: LLMProvider,
    top_n: int = 10,
    max_input_chars: int = 8000,
    max_per_domain: int = 2,
    keywords: list[str] | None = None,
    game_signals: list[str] | None = None,
    legal_signals: list[str] | None = None,
) -> list[RawArticle]:
    """Compatibility wrapper returning only the selected articles."""
    return select_articles(
        articles,
        llm,
        top_n=top_n,
        max_input_chars=max_input_chars,
        max_per_domain=max_per_domain,
        keywords=keywords,
        game_signals=game_signals,
        legal_signals=legal_signals,
    ).articles
