from __future__ import annotations

import logging
from dataclasses import dataclass

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
- event_key: a short, stable, human-readable identifier for the underlying regulatory EVENT (not the article). Use lowercase_snake_case. Format: {{jurisdiction}}_{{topic}}_{{action}}_{{year_or_quarter}}. Examples: "eu_lootbox_transparency_directive_2026", "us_ftc_coppa_enforcement_2026q1", "kr_age_rating_mobile_guidance_update". The SAME event covered by different news outlets MUST produce the SAME event_key.

Allowed categories: {categories}
Allowed jurisdictions: {jurisdictions}
Allowed event types: {event_types}
Allowed phases: {phases}

Article title: {title}
Source: {source}
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
    ],
}


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


def classify_article(article: RawArticle, llm: LLMProvider) -> ClassificationResult:
    """Classify a single article into the briefing metadata schema."""
    prompt = CLASSIFIER_PROMPT.format(
        categories=", ".join(sorted(VALID_CATEGORIES)),
        jurisdictions=", ".join(item.value for item in Jurisdiction),
        event_types=", ".join(item.value for item in EventType),
        phases=", ".join(item.value for item in RegulatoryPhase),
        title=article.title,
        source=article.source,
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

        category = payload.get("category", "ETC")
        if category not in VALID_CATEGORIES:
            category = "ETC"

        event_key = str(payload.get("event_key", "")).strip().lower().replace(" ", "_")

        return ClassificationResult(
            category=category,
            event=LegalEvent(
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
            ),
            event_key=event_key,
        )
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
        )
