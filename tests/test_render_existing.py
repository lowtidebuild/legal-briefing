from pathlib import Path

from pipeline.store.daily import save_daily
from scripts.render_existing import render_existing


def test_render_existing_supports_no_updates_daily_file(tmp_path):
    repo = Path(__file__).parents[1]
    date = "2026-07-20"
    save_daily([], date, data_dir=str(tmp_path / "data" / "daily"))

    render_existing(
        date=date,
        config_path=str(repo / "config.yaml"),
        output_dir=str(tmp_path),
        template_dir=str(repo / "templates"),
        static_dir=str(repo / "static"),
    )

    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "오늘은 중대한 게임 법률 업데이트가 없습니다" in html
    assert (tmp_path / "archive" / f"{date}.html").is_file()
