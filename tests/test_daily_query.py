import tempfile

from pipeline.models import BriefingNode, EventType, Jurisdiction, LegalEvent, RegulatoryPhase
from pipeline.store.daily import load_daily, save_daily
from pipeline.store.query import list_briefing_dates, query_nodes


def _node(title: str, jurisdiction: Jurisdiction, category: str, pub_date: str) -> BriefingNode:
    return BriefingNode(
        title=title,
        url=f"https://example.com/{title}",
        source="Test",
        pub_date=pub_date,
        category=category,
        summary_ko=["요약"],
        event=LegalEvent(
            jurisdiction=jurisdiction,
            event_type=EventType.LEGISLATION,
            regulatory_phase=RegulatoryPhase.ENACTED,
            actors=["Test"],
            object="test",
            action="tested",
            game_mechanic=None,
            time_hint="",
        ),
        event_key=f"key_{title}",
        is_primary=True,
    )


def test_save_load_and_query_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        save_daily([_node("A", Jurisdiction.EU, "IP", "2026-03-23")], "2026-03-23", tmpdir)
        save_daily([_node("B", Jurisdiction.KR, "ETC", "2026-03-25")], "2026-03-25", tmpdir)

        loaded = load_daily("2026-03-23", data_dir=tmpdir)
        assert len(loaded) == 1
        assert loaded[0].title == "A"

        dates = list_briefing_dates(data_dir=tmpdir)
        assert dates == ["2026-03-25", "2026-03-23"]

        result = query_nodes(data_dir=tmpdir, jurisdiction=Jurisdiction.EU)
        assert len(result) == 1
        assert result[0].title == "A"

