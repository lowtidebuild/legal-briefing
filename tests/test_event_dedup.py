from pipeline.intelligence.classifier import ClassificationResult
from pipeline.intelligence.event_dedup import build_classified_article, dedup_classified_articles
from pipeline.models import EventType, Jurisdiction, LegalEvent, RegulatoryPhase
from pipeline.sources.rss import RawArticle


def _article(title: str, url: str = "https://example.com/a") -> RawArticle:
    return RawArticle(
        title=title,
        url=url,
        source="Test",
        description="desc",
        pub_date="2026-04-27",
    )


def _classification(event_key: str = "") -> ClassificationResult:
    return ClassificationResult(
        category="CONSUMER_MONETIZATION",
        event=LegalEvent(
            jurisdiction=Jurisdiction.EU,
            event_type=EventType.LEGISLATION,
            regulatory_phase=RegulatoryPhase.ENACTED,
            actors=["EU Commission"],
            object="loot box disclosure",
            action="published rules",
            game_mechanic="loot_box",
            time_hint="2026",
        ),
        event_key=event_key,
    )


def test_build_classified_article_has_stable_fingerprint():
    first = build_classified_article(_article("A"), _classification())
    second = build_classified_article(_article("B"), _classification())
    assert len(first.event_fingerprint) == 16
    assert first.event_fingerprint == second.event_fingerprint


def test_dedup_classified_articles_removes_existing_fingerprint():
    item = build_classified_article(_article("A"), _classification())
    result = dedup_classified_articles(
        [item],
        existing_event_keys=set(),
        existing_event_fingerprints={item.event_fingerprint},
    )
    assert result == []


def test_dedup_classified_articles_removes_duplicate_event_key():
    first = build_classified_article(_article("A"), _classification("same_key"))
    second = build_classified_article(_article("B", "https://example.com/b"), _classification("same_key"))
    result = dedup_classified_articles(
        [first, second],
        existing_event_keys=set(),
        existing_event_fingerprints=set(),
    )
    assert result == [first]


def test_weak_classification_uses_title_fallback():
    classification = ClassificationResult(
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
    first = build_classified_article(_article("EU Loot Box Regulation"), classification)
    second = build_classified_article(_article("Completely Different Topic"), classification)
    assert first.event_fingerprint != second.event_fingerprint
