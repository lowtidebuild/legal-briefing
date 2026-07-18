from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from pipeline.intelligence.batch import run_validated_batch
from pipeline.intelligence.dedup import canonicalize_event_key, compute_event_key, url_hash
from pipeline.llm.base import LLMProvider
from pipeline.models import (
    VALID_CATEGORIES,
    EventType,
    Jurisdiction,
    LegalEvent,
    RegulatoryPhase,
)
from pipeline.sources.rss import RawArticle

logger = logging.getLogger(__name__)

CLASSIFIER_SYSTEM = (
    "You are a legal analyst specializing in the game industry. "
    "Extract structured regulatory metadata."
)

CLASSIFIER_PROMPT = """Analyze this article and return JSON with:
- category
- jurisdiction
- event_type
- regulatory_phase
- actors
- object
- action
- game_mechanic
- time_hint
- event_key: a short, stable, human-readable identifier for the underlying regulatory EVENT (not the article). Use lowercase_snake_case without a year or quarter; code adds the publication quarter. Example: "eu_lootbox_transparency_directive". The SAME event covered by different news outlets MUST produce the SAME event_key.

Allowed categories: {categories}
Allowed jurisdictions: {jurisdictions}
Allowed event types: {event_types}
Allowed phases: {phases}

Article title: {title}
Source: {source}
Publication date: {pub_date}
Description: {description}

Return JSON only."""

CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": sorted(VALID_CATEGORIES)},
        "jurisdiction": {"type": "string", "enum": [item.value for item in Jurisdiction]},
        "event_type": {"type": "string", "enum": [item.value for item in EventType]},
        "regulatory_phase": {"type": "string", "enum": [item.value for item in RegulatoryPhase]},
        "actors": {"type": "array", "items": {"type": "string"}},
        "object": {"type": "string"},
        "action": {"type": "string"},
        "game_mechanic": {"type": "string"},
        "time_hint": {"type": "string"},
        "event_key": {"type": "string"},
    },
    "required": [
        "category",
        "jurisdiction",
        "event_type",
        "regulatory_phase",
        "actors",
        "object",
        "action",
        "time_hint",
        "event_key",
    ],
}

CLASSIFICATION_BATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    **CLASSIFICATION_SCHEMA["properties"],
                },
                "required": ["item_id", *CLASSIFICATION_SCHEMA["required"]],
            },
        }
    },
    "required": ["results"],
}

CLASSIFICATION_BATCH_PROMPT = """Analyze every article below and return one result per item_id.
Apply the same legal classification rules to every item. event_key must be a stable
lowercase_snake_case event identifier without a year or quarter. Do not omit items.

Allowed categories: {categories}
Allowed jurisdictions: {jurisdictions}
Allowed event types: {event_types}
Allowed phases: {phases}

Items JSON:
{items_json}

Return JSON only as {{"results": [...]}}."""


@dataclass
class ClassificationResult:
    category: str
    event: LegalEvent
    event_key: str = ""


def _safe_enum(enum_cls, raw_value: str, default):
    try:
        return enum_cls(raw_value)
    except ValueError:
        return default


def _classification_from_payload(article: RawArticle, payload: dict) -> ClassificationResult:
    category = payload.get("category", "ETC")
    if category not in VALID_CATEGORIES:
        category = "ETC"

    event = LegalEvent(
        jurisdiction=_safe_enum(
            Jurisdiction,
            payload.get("jurisdiction", Jurisdiction.GLOBAL.value),
            Jurisdiction.GLOBAL,
        ),
        event_type=_safe_enum(
            EventType,
            payload.get("event_type", EventType.OTHER.value),
            EventType.OTHER,
        ),
        regulatory_phase=_safe_enum(
            RegulatoryPhase,
            payload.get("regulatory_phase", RegulatoryPhase.PROPOSED.value),
            RegulatoryPhase.PROPOSED,
        ),
        actors=list(payload.get("actors", [])),
        object=str(payload.get("object", "")),
        action=str(payload.get("action", "")),
        game_mechanic=payload.get("game_mechanic"),
        time_hint=str(payload.get("time_hint", "")),
    )
    if event.actors or event.object or event.action:
        fallback_event_key = compute_event_key(
            jurisdiction=event.jurisdiction.value,
            actors=event.actors,
            object_=event.object,
            action=event.action,
        )
    else:
        fallback_event_key = url_hash(article.url)
    event_key = canonicalize_event_key(
        payload.get("event_key"),
        article.pub_date,
        fallback_event_key,
    )
    return ClassificationResult(category=category, event=event, event_key=event_key)


def classify_article(article: RawArticle, llm: LLMProvider) -> ClassificationResult:
    """Classify a single article into the briefing metadata schema."""
    prompt = CLASSIFIER_PROMPT.format(
        categories=", ".join(sorted(VALID_CATEGORIES)),
        jurisdictions=", ".join(item.value for item in Jurisdiction),
        event_types=", ".join(item.value for item in EventType),
        phases=", ".join(item.value for item in RegulatoryPhase),
        title=article.title,
        source=article.source,
        pub_date=article.pub_date,
        description=article.description[:2000],
    )

    try:
        payload = llm.generate_json_schema(
            prompt,
            schema=CLASSIFICATION_SCHEMA,
            system=CLASSIFIER_SYSTEM,
        )
        if not isinstance(payload, dict):
            raise ValueError("Classifier response must be a JSON object")

        return _classification_from_payload(article, payload)
    except Exception as exc:
        logger.warning("Classification failed for '%s': %s", article.title, exc)
        return ClassificationResult(
            category="ETC",
            event=LegalEvent(
                jurisdiction=Jurisdiction.GLOBAL,
                event_type=EventType.OTHER,
                regulatory_phase=RegulatoryPhase.PROPOSED,
                actors=[],
                object="",
                action="",
                game_mechanic=None,
                time_hint="",
            ),
            event_key=canonicalize_event_key(
                raw_event_key="",
                pub_date=article.pub_date,
                fallback_event_key=url_hash(article.url),
            ),
        )


def classify_articles(
    articles: list[RawArticle],
    llm: LLMProvider,
) -> list[ClassificationResult]:
    """Classify articles in one validated batch while preserving input order."""
    if not articles:
        return []

    from pipeline.llm.offline import OfflineLLMProvider

    if isinstance(llm, OfflineLLMProvider):
        return [classify_article(article, llm) for article in articles]

    def build_prompt(batch: list[RawArticle]) -> str:
        items = [
            {
                "item_id": url_hash(article.url),
                "title": article.title,
                "source": article.source,
                "pub_date": article.pub_date,
                "description": article.description[:2000],
            }
            for article in batch
        ]
        return CLASSIFICATION_BATCH_PROMPT.format(
            categories=", ".join(sorted(VALID_CATEGORIES)),
            jurisdictions=", ".join(item.value for item in Jurisdiction),
            event_types=", ".join(item.value for item in EventType),
            phases=", ".join(item.value for item in RegulatoryPhase),
            items_json=json.dumps(items, ensure_ascii=False),
        )

    return run_validated_batch(
        items=articles,
        llm=llm,
        item_id=lambda article: url_hash(article.url),
        build_prompt=build_prompt,
        schema=CLASSIFICATION_BATCH_SCHEMA,
        parse_item=_classification_from_payload,
        system=CLASSIFIER_SYSTEM,
    )
