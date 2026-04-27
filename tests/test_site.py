import os
import tempfile

from pipeline.models import BriefingNode, EventType, Jurisdiction, LegalEvent, RegulatoryPhase
from pipeline.render.site import render_archive, render_article_pages, render_index


def _node(title: str = "Test", time_hint: str = "") -> BriefingNode:
    return BriefingNode(
        title=title,
        url="https://example.com",
        source="Test",
        pub_date="2026-03-23",
        category="IP",
        summary_ko=["요약 1", "요약 2"],
        event=LegalEvent(
            jurisdiction=Jurisdiction.US,
            event_type=EventType.LITIGATION,
            regulatory_phase=RegulatoryPhase.ENACTED,
            actors=["Nintendo"],
            object="patent",
            action="filed",
            game_mechanic="loot_box",
            time_hint=time_hint,
        ),
        event_key="key1",
        is_primary=True,
    )


def test_render_pages_create_html():
    with tempfile.TemporaryDirectory() as tmpdir:
        template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
        index_path = render_index(nodes=[_node()], date="2026-03-23", output_dir=tmpdir, template_dir=template_dir, base_url="")
        archive_path = render_archive(
            entries=[{"date": "2026-03-23", "count": 5}],
            output_dir=tmpdir,
            template_dir=template_dir,
            base_url="",
        )
        render_article_pages(nodes=[_node()], output_dir=tmpdir, template_dir=template_dir, base_url="")

        assert os.path.exists(index_path)
        assert os.path.exists(archive_path)
        assert os.path.exists(os.path.join(tmpdir, "article", "key1.html"))


def test_render_index_exposes_time_hint():
    with tempfile.TemporaryDirectory() as tmpdir:
        template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
        index_path = render_index(
            nodes=[_node(time_hint="June 2026")],
            date="2026-03-23",
            output_dir=tmpdir,
            template_dir=template_dir,
            base_url="",
        )
        html = open(index_path, encoding="utf-8").read()
        assert "Timeline · June 2026" in html
