import os
import json
import logging
import tempfile
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pipeline.config import LLMConfig
from pipeline.sources.rss import FeedFetchReport, RawArticle


def _make_config():
    return SimpleNamespace(
        llm=SimpleNamespace(
            provider="gemini",
            model="gemini-3.5-flash",
            summary_model=None,
            fallback_model=None,
            reasoning_effort=None,
            summary_reasoning_effort=None,
            fallback_reasoning_effort=None,
            max_retries=2,
            request_timeout_seconds=30,
            max_input_chars=8000,
            concurrency=1,
        ),
        google_api_key=None,
        anthropic_api_key=None,
        groq_api_key=None,
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


class _HealthyLLM:
    def __init__(self):
        self._classification_count = 0

    def generate_json(self, prompt: str, system: str | None = None):
        if "selected_indices" in prompt:
            return {"selected_indices": list(range(10))}
        return {
            "title_ko": "FTC, 게임 정책 업데이트",
            "summary_ko": [
                "FTC가 게임 플랫폼 정책 업데이트를 검토하고 있습니다.",
                "소비자 보호와 플랫폼 운영 기준에 영향이 있을 수 있습니다.",
                "게임사는 고지와 내부 정책을 점검해야 합니다.",
            ],
        }

    def generate_json_schema(self, prompt: str, schema: dict, system: str | None = None):
        self._classification_count += 1
        return {
            "category": "PRIVACY_SECURITY",
            "jurisdiction": "US",
            "event_type": "policy",
            "regulatory_phase": "proposed",
            "actors": ["FTC"],
            "object": f"gaming policy {self._classification_count}",
            "action": "updated guidance",
            "game_mechanic": "none",
            "time_hint": "2026",
            "event_key": f"us_ftc_gaming_policy_{self._classification_count}_2026",
        }


class _DegradedLLM:
    def generate_json(self, prompt: str, system: str | None = None):
        if "selected_indices" in prompt:
            return {"selected_indices": list(range(10))}
        return {"title_ko": "", "summary_ko": ["English fallback summary"]}

    def generate_json_schema(self, prompt: str, schema: dict, system: str | None = None):
        return {
            "category": "ETC",
            "jurisdiction": "Global",
            "event_type": "other",
            "regulatory_phase": "proposed",
            "actors": [],
            "object": "",
            "action": "",
            "game_mechanic": None,
            "time_hint": "",
            "event_key": "global_llm_failure_fallback",
        }


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


def test_pipeline_routes_groq_analysis_and_summary_models():
    cfg = _make_config()
    cfg.llm = LLMConfig(
        provider="groq",
        model="openai/gpt-oss-120b",
        summary_model="qwen/qwen3.6-27b",
        fallback_model="openai/gpt-oss-120b",
        reasoning_effort="low",
        summary_reasoning_effort="none",
        fallback_reasoning_effort="low",
        concurrency=1,
    )
    cfg.groq_api_key = "test-key"

    with tempfile.TemporaryDirectory() as tmpdir:
        with (
            patch("main.load_config", return_value=cfg),
            patch(
                "main.create_provider",
                side_effect=[_HealthyLLM(), _HealthyLLM()],
            ) as create_mock,
        ):
            from main import run_pipeline

            run_pipeline(
                config_path="config.yaml",
                output_dir=tmpdir,
                template_dir=_template_dir(),
                static_dir=_static_dir(),
                dry_run=True,
                use_sample_data=True,
            )

    assert create_mock.call_count == 2
    assert create_mock.call_args_list[0].args[0].model == "openai/gpt-oss-120b"
    summary_cfg = create_mock.call_args_list[1].args[0]
    assert summary_cfg.model == "qwen/qwen3.6-27b"
    assert summary_cfg.reasoning_effort == "none"
    assert summary_cfg.fallback_model == "openai/gpt-oss-120b"


def test_pipeline_separates_gemini_thinking_levels_for_analysis_and_summary():
    cfg = _make_config()
    cfg.llm = LLMConfig(
        provider="gemini",
        model="gemini-3.5-flash",
        summary_model="gemini-3.5-flash",
        fallback_model="gemini-3.1-flash-lite",
        reasoning_effort="low",
        summary_reasoning_effort="minimal",
        fallback_reasoning_effort="minimal",
        concurrency=1,
    )
    cfg.google_api_key = "test-key"

    with tempfile.TemporaryDirectory() as tmpdir:
        with (
            patch("main.load_config", return_value=cfg),
            patch(
                "main.create_provider",
                side_effect=[_HealthyLLM(), _HealthyLLM()],
            ) as create_mock,
        ):
            from main import run_pipeline

            run_pipeline(
                config_path="config.yaml",
                output_dir=tmpdir,
                template_dir=_template_dir(),
                static_dir=_static_dir(),
                dry_run=True,
                use_sample_data=True,
            )

    assert create_mock.call_count == 2
    analysis_cfg = create_mock.call_args_list[0].args[0]
    summary_cfg = create_mock.call_args_list[1].args[0]
    assert analysis_cfg.reasoning_effort == "low"
    assert summary_cfg.model == "gemini-3.5-flash"
    assert summary_cfg.reasoning_effort == "minimal"
    assert summary_cfg.fallback_model == "gemini-3.1-flash-lite"


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
            patch("pipeline.sources.tier_c.write_sources_backlog"),
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
        assert os.path.exists(os.path.join(tmpdir, "email-preview.html"))


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
            patch("main.create_provider", return_value=_HealthyLLM()),
            patch(
                "main.fetch_all_feeds_with_report",
                return_value=FeedFetchReport(articles=articles, tier_a_total=1, tier_a_empty=0),
            ),
            patch("pipeline.sources.tier_c.write_sources_backlog"),
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


def test_live_pipeline_continues_on_degraded_tier_a_feed_health(caplog):
    cfg = _make_config()
    cfg.google_api_key = "test-key"
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
            patch("main.create_provider", return_value=_HealthyLLM()),
            patch(
                "main.fetch_all_feeds_with_report",
                return_value=FeedFetchReport(articles=articles, tier_a_total=44, tier_a_empty=24),
            ),
            patch("pipeline.sources.tier_c.write_sources_backlog"),
        ):
            from main import run_pipeline

            caplog.set_level(logging.WARNING)
            run_pipeline(
                config_path="config.yaml",
                output_dir=tmpdir,
                template_dir=_template_dir(),
                static_dir=_static_dir(),
                dry_run=False,
                use_sample_data=False,
            )

        data_dir = os.path.join(tmpdir, "data", "daily")
        json_files = [name for name in os.listdir(data_dir) if name.endswith(".json")]
        assert len(json_files) == 1
        assert "Tier A feed health degraded: 24/44" in caplog.text


def test_live_pipeline_drops_missing_date_articles_before_rendering():
    cfg = _make_config()
    cfg.google_api_key = "test-key"
    today = datetime.now().strftime("%Y-%m-%d")
    fresh_articles = [
        RawArticle(
            title=f"FTC gaming policy update {index}",
            url=f"https://example.com/{index}",
            source="Test Feed",
            description="FTC policy update for gaming platforms",
            pub_date=today,
        )
        for index in range(10)
    ]
    stale_undated_article = RawArticle(
        title="US Copyright Office rules that monkeys CAN'T claim copyright over their selfies",
        url=(
            "http://go.theregister.com/feed/www.theregister.co.uk/2014/08/22/"
            "us_copyright_office_rules_monkeys_selfie_public_domain/"
        ),
        source="The Register - Policy",
        description="2014 copyright article without a parseable RSS publication date",
        pub_date="",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        with (
            patch("main.load_config", return_value=cfg),
            patch("main.create_provider", return_value=_HealthyLLM()),
            patch(
                "main.fetch_all_feeds_with_report",
                return_value=FeedFetchReport(
                    articles=fresh_articles + [stale_undated_article],
                    tier_a_total=1,
                    tier_a_empty=0,
                ),
            ),
            patch("pipeline.sources.tier_c.write_sources_backlog"),
        ):
            from main import run_pipeline

            run_pipeline(
                config_path="config.yaml",
                output_dir=tmpdir,
                template_dir=_template_dir(),
                static_dir=_static_dir(),
                dry_run=False,
                use_sample_data=False,
            )

        data_dir = os.path.join(tmpdir, "data", "daily")
        json_files = [name for name in os.listdir(data_dir) if name.endswith(".json")]
        payload = open(os.path.join(data_dir, json_files[0]), encoding="utf-8").read()
        assert "monkeys CAN'T claim copyright" not in payload
        assert "FTC gaming policy update 0" in payload


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
            patch("main.create_provider", return_value=_HealthyLLM()),
            patch(
                "main.fetch_all_feeds_with_report",
                return_value=FeedFetchReport(articles=[article], tier_a_total=1, tier_a_empty=0),
            ),
            patch("pipeline.sources.tier_c.write_sources_backlog"),
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


def test_live_pipeline_aborts_on_degraded_llm_output():
    cfg = _make_config()
    cfg.google_api_key = "test-key"
    today = datetime.now().strftime("%Y-%m-%d")
    articles = [
        RawArticle(
            title=f"AI gaming article {index}",
            url=f"https://example.com/{index}",
            source="Test Feed",
            description="AI policy update for gaming platforms",
            pub_date=today,
        )
        for index in range(10)
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        with (
            patch("main.load_config", return_value=cfg),
            patch("main.create_provider", return_value=_DegradedLLM()),
            patch(
                "main.fetch_all_feeds_with_report",
                return_value=FeedFetchReport(articles=articles, tier_a_total=1, tier_a_empty=0),
            ),
            patch("pipeline.sources.tier_c.write_sources_backlog"),
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

        assert exc.value.code == 4
        assert not os.path.exists(os.path.join(tmpdir, "data", "daily"))
