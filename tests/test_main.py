import os
import tempfile
from unittest.mock import MagicMock, patch


def _make_config():
    cfg = MagicMock()
    cfg.llm.provider = "gemini"
    cfg.llm.model = "gemini-3.1-flash-lite"
    cfg.llm.max_retries = 2
    cfg.llm.request_timeout_seconds = 30
    cfg.google_api_key = None
    cfg.anthropic_api_key = None
    cfg.sources.tier_a = []
    cfg.sources.tier_b = []
    cfg.pipeline.top_n = 10
    cfg.pipeline.keywords = []
    cfg.site.base_url = ""
    cfg.email.subject_prefix = "[Test]"
    cfg.smtp_user = None
    cfg.smtp_pass = None
    cfg.recipients = []
    cfg.google_sheets_credentials = None
    cfg.google_sheets_id = None
    return cfg


def _template_dir():
    return os.path.join(os.path.dirname(__file__), "..", "templates")


def _static_dir():
    return os.path.join(os.path.dirname(__file__), "..", "static")


def test_main_runs_with_sample_mode_and_offline_provider():
    cfg = _make_config()

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("main.load_config", return_value=cfg), patch("main.create_provider", side_effect=ValueError("missing key")):
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
        with patch("main.load_config", return_value=cfg), patch("main.create_provider", side_effect=ValueError("missing key")):
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
