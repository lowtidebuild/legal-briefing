import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from pipeline.intelligence.dedup import is_safe_event_key
from pipeline.models import BriefingNode, EventType, Jurisdiction, LegalEvent, RegulatoryPhase
from pipeline.models import dict_to_briefing_node
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


def test_render_article_pages_skips_unchanged_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
        render_article_pages(nodes=[_node()], output_dir=tmpdir, template_dir=template_dir, base_url="")
        path = os.path.join(tmpdir, "article", "key1.html")
        first_mtime = os.path.getmtime(path)
        time.sleep(0.01)
        render_article_pages(nodes=[_node()], output_dir=tmpdir, template_dir=template_dir, base_url="")
        assert os.path.getmtime(path) == first_mtime


@pytest.mark.parametrize("unsafe_key", ["../escape", "/tmp/escape", r"C:\tmp\escape", "bad\x00key"])
def test_render_article_pages_rejects_unsafe_event_key(tmp_path, unsafe_key):
    node = _node()
    node.event_key = unsafe_key
    template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")

    with pytest.raises(ValueError, match="Unsafe event_key"):
        render_article_pages(
            nodes=[node],
            output_dir=str(tmp_path),
            template_dir=template_dir,
            base_url="",
        )

    assert not (tmp_path / "escape.html").exists()


def test_render_article_pages_rejects_symlink_escape(tmp_path):
    article_dir = tmp_path / "article"
    article_dir.mkdir()
    outside_file = tmp_path / "outside.html"
    outside_file.write_text("do not overwrite", encoding="utf-8")
    (article_dir / "key1.html").symlink_to(outside_file)

    with pytest.raises(ValueError, match="escaped output/article"):
        render_article_pages(
            nodes=[_node()],
            output_dir=str(tmp_path),
            template_dir=os.path.join(os.path.dirname(__file__), "..", "templates"),
            base_url="",
        )

    assert outside_file.read_text(encoding="utf-8") == "do not overwrite"


def test_existing_daily_archive_event_keys_remain_renderable(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    daily_files = sorted((repo_root / "output" / "data" / "daily").glob("*.json"))
    nodes = []
    for daily_file in daily_files:
        payload = json.loads(daily_file.read_text(encoding="utf-8"))
        nodes.extend(dict_to_briefing_node(item) for item in payload)

    assert len(nodes) >= 500
    assert all(is_safe_event_key(node.event_key) for node in nodes)

    render_article_pages(
        nodes=nodes,
        output_dir=str(tmp_path),
        template_dir=str(repo_root / "templates"),
        base_url="",
    )

    assert all((tmp_path / "article" / f"{node.event_key}.html").exists() for node in nodes)
