from pipeline.intelligence.classifier import ClassificationResult
from pipeline.models import EventType, Jurisdiction, LegalEvent, RegulatoryPhase
from pipeline.sources.rss import RawArticle
from pipeline.store.nodes import assemble_node


def _article() -> RawArticle:
    return RawArticle(
        title="Test Article",
        url="https://example.com/test",
        source="TestFeed",
        description="desc",
        pub_date="2026-03-23",
    )


def _classification() -> ClassificationResult:
    return ClassificationResult(
        category="IP",
        event=LegalEvent(
            jurisdiction=Jurisdiction.US,
            event_type=EventType.LITIGATION,
            regulatory_phase=RegulatoryPhase.LITIGATION,
            actors=["Nintendo"],
            object="patent",
            action="filed suit",
            game_mechanic=None,
            time_hint="",
        ),
    )


def test_assemble_node():
    node = assemble_node(_article(), _classification(), ["요약 1", "요약 2", "요약 3"])
    assert node.title == "Test Article"
    assert node.category == "IP"
    assert node.event.jurisdiction == Jurisdiction.US
    assert len(node.summary_ko) == 3
    assert len(node.event_key) == 16
    assert node.is_primary is True

