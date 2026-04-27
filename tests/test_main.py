import os
import json
import tempfile
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from pipeline.sources.rss import FeedFetchReport, RawArticle


def _make_config():
    return SimpleNamespace(
        llm=SimpleNamespace(
            provider="gemini",
            model="gemini-3.1-flash-lite",
            max_retries=2,
            request_timeout_seconds=30,
            max_input_chars=8000,
            concurrency=1,
        ),
        google_api_key=None,
        anthropic_api_key=None,
        sources=SimpleNamespace(
            tier_a=[],
            tier_b=[],
            tier_c=[],
        ),
        pipeline=SimpleNamespace(
            top_n=10,
            max_per_domain=2,
            fetch_body_for_selected=False,
            body_fetch_timeout_seconds=10,
            body_fetch_max_chars=8000,
            keywords=[],
        ),
        dedup=SimpleNamespace(
            retention_days=30,
        ),
        site=SimpleNamespace(
            base_url="",
        ),
        email=SimpleNamespace(
            subject_prefix="[Test]",
            web_url="https://example.com/web",
        ),
        smtp_user=None,
        smtp_pass=None,
        recipients=[],
        google_sheets_credentials=None,
        google_sheets_id=None,
    )


def _template_dir():
    return os.path.join(os.path.dirname(__file__), "..", "templates")


def _static_dir():
    return os.path.join(os.path.dirname(__file__), "..", "static")


def test_main_runs_with_sample_mode_and_offline_provider():
    cfg = _make_config()

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("main.load_config", return_value=cfg):
            from main import run_pipeline

            run_pipeline(
                config_path="config.yaml",
                output_dir=tmpdir,
                template_dir=_template_dir(),
                static_dir=_static_dir(),
                dry_run=True,
                use_sample_data=True,
            )

        data_dir = os.path.join(tmpdir, "data", "daily")
        assert os.path.exists(data_dir)
        json_files = [name for name in os.listdir(data_dir) if name.endswith(".json")]
        assert len(json_files) == 1
        assert os.path.exists(os.path.join(tmpdir, "index.html"))


def test_sample_mode_is_repeatable_on_same_day():
    cfg = _make_config()

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("main.load_config", return_value=cfg):
            from main import run_pipeline

            run_pipeline(
                config_path="config.yaml",
                output_dir=tmpdir,
                template_dir=_template_dir(),
                static_dir=_static_dir(),
                dry_run=True,
                use_sample_data=True,
            )
            run_pipeline(
                config_path="config.yaml",
                output_dir=tmpdir,
                template_dir=_template_dir(),
                static_dir=_static_dir(),
                dry_run=True,
                use_sample_data=True,
            )

        daily_path = os.path.join(tmpdir, "data", "daily")
        files = [name for name in os.listdir(daily_path) if name.endswith(".json")]
        assert len(files) == 1
        payload = open(os.path.join(daily_path, files[0]), encoding="utf-8").read()
        assert "Sample Feed" in payload


def test_dry_run_without_api_key_uses_offline_provider_for_live_pipeline():
    cfg = _make_config()
    today = datetime.now().strftime("%Y-%m-%d")
    article = RawArticle(
        title="FTC issues new gaming policy",
        url="https://example.com/ftc",
        source="Test Feed",
        description="FTC policy update for gaming platforms",
        pub_date=today,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        with (
            patch("main.load_config", return_value=cfg),
            patch(
                "main.fetch_all_feeds_with_report",
                return_value=FeedFetchReport(articles=[article], tier_a_total=1, tier_a_empty=0),
            ),
        ):
            from main import run_pipeline

            run_pipeline(
                config_path="config.yaml",
                output_dir=tmpdir,
                template_dir=_template_dir(),
                static_dir=_static_dir(),
                dry_run=True,
                use_sample_data=False,
            )

        data_dir = os.path.join(tmpdir, "data", "daily")
        json_files = [name for name in os.listdir(data_dir) if name.endswith(".json")]
        assert len(json_files) == 1
        payload = open(os.path.join(data_dir, json_files[0]), encoding="utf-8").read()
        assert "Test Feed" in payload
        dedup_payload = json.loads(
            open(os.path.join(tmpdir, "data", "dedup_index.json"), encoding="utf-8").read()
        )
        assert dedup_payload["schema_version"] == 2
        assert dedup_payload["entries"][0]["event_fingerprint"]


def test_live_pipeline_aborts_when_sheets_read_fails():
    cfg = _make_config()
    cfg.google_api_key = "test-key"
    cfg.google_sheets_credentials = "{}"
    cfg.google_sheets_id = "sheet-id"
    today = datetime.now().strftime("%Y-%m-%d")
    articles = [
        RawArticle(
            title=f"FTC gaming policy update {index}",
            url=f"https://example.com/{index}",
            source="Test Feed",
            description="FTC policy update for gaming platforms",
            pub_date=today,
        )
        for index in range(10)
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        with (
            patch("main.load_config", return_value=cfg),
            patch("main.create_provider", return_value=MagicMock()),
            patch(
                "main.fetch_all_feeds_with_report",
                return_value=FeedFetchReport(articles=articles, tier_a_total=1, tier_a_empty=0),
            ),
            patch("main.read_event_keys_from_sheets", return_value=None),
        ):
            from main import run_pipeline

            with pytest.raises(SystemExit) as exc:
                run_pipeline(
                    config_path="config.yaml",
                    output_dir=tmpdir,
                    template_dir=_template_dir(),
                    static_dir=_static_dir(),
                    dry_run=False,
                    use_sample_data=False,
                )

        assert exc.value.code == 3


def test_live_pipeline_aborts_on_low_article_health():
    cfg = _make_config()
    cfg.google_api_key = "test-key"
    today = datetime.now().strftime("%Y-%m-%d")
    article = RawArticle(
        title="FTC gaming policy update",
        url="https://example.com/ftc",
        source="Test Feed",
        description="FTC policy update for gaming platforms",
        pub_date=today,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        with (
            patch("main.load_config", return_value=cfg),
            patch("main.create_provider", return_value=MagicMock()),
            patch(
                "main.fetch_all_feeds_with_report",
                return_value=FeedFetchReport(articles=[article], tier_a_total=1, tier_a_empty=0),
            ),
        ):
            from main import run_pipeline

            with pytest.raises(SystemExit) as exc:
                run_pipeline(
                    config_path="config.yaml",
                    output_dir=tmpdir,
                    template_dir=_template_dir(),
                    static_dir=_static_dir(),
                    dry_run=False,
                    use_sample_data=False,
                )

        assert exc.value.code == 2
