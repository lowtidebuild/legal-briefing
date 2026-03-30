from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from enum import Enum


class Jurisdiction(str, Enum):
    EU = "EU"
    KR = "KR"
    US = "US"
    UK = "UK"
    JP = "JP"
    AU = "AU"
    CN = "CN"
    GLOBAL = "Global"


class RegulatoryPhase(str, Enum):
    PROPOSED = "proposed"
    PUBLIC_COMMENT = "public_comment"
    ENACTED = "enacted"
    ENFORCED = "enforced"
    LITIGATION = "litigation"


class EventType(str, Enum):
    ENFORCEMENT = "enforcement"
    LEGISLATION = "legislation"
    LITIGATION = "litigation"
    POLICY = "policy"
    SECURITY_INCIDENT = "security_incident"
    BUSINESS = "business"
    OTHER = "other"


VALID_CATEGORIES: set[str] = {
    "IP",
    "CONSUMER_MONETIZATION",
    "CONTENT_AGE",
    "PRIVACY_SECURITY",
    "PLATFORM_PUBLISHING",
    "AI_EMERGING",
    "MA_CORP_ANTITRUST",
    "ESPORTS_MARKETING",
    "LABOR_EMPLOYMENT",
    "ETC",
}


@dataclass
class LegalEvent:
    jurisdiction: Jurisdiction
    event_type: EventType
    regulatory_phase: RegulatoryPhase
    actors: list[str]
    object: str
    action: str
    game_mechanic: str | None
    time_hint: str


@dataclass
class BriefingNode:
    title: str
    url: str
    source: str
    pub_date: str
    category: str
    summary_ko: list[str]
    event: LegalEvent
    event_key: str
    is_primary: bool


def briefing_node_to_dict(node: BriefingNode) -> dict:
    """Serialize a briefing node into JSON-friendly primitives."""
    data = dataclasses.asdict(node)
    data["event"]["jurisdiction"] = node.event.jurisdiction.value
    data["event"]["event_type"] = node.event.event_type.value
    data["event"]["regulatory_phase"] = node.event.regulatory_phase.value
    return data


def dict_to_briefing_node(data: dict) -> BriefingNode:
    """Deserialize a persisted dictionary into a BriefingNode."""
    event_data = data["event"]
    event = LegalEvent(
        jurisdiction=Jurisdiction(event_data["jurisdiction"]),
        event_type=EventType(event_data["event_type"]),
        regulatory_phase=RegulatoryPhase(event_data["regulatory_phase"]),
        actors=list(event_data["actors"]),
        object=event_data["object"],
        action=event_data["action"],
        game_mechanic=event_data.get("game_mechanic"),
        time_hint=event_data.get("time_hint", ""),
    )
    return BriefingNode(
        title=data["title"],
        url=data["url"],
        source=data["source"],
        pub_date=data["pub_date"],
        category=data["category"],
        summary_ko=list(data["summary_ko"]),
        event=event,
        event_key=data["event_key"],
        is_primary=bool(data["is_primary"]),
    )

