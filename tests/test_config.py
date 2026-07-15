import os
import tempfile

import yaml

from pipeline.config import load_config


def test_load_config_from_file():
    data = {
        "llm": {
            "provider": "groq",
            "model": "openai/gpt-oss-120b",
            "summary_model": "qwen/qwen3.6-27b",
            "fallback_model": "openai/gpt-oss-120b",
            "reasoning_effort": "low",
            "summary_reasoning_effort": "none",
            "fallback_reasoning_effort": "low",
            "max_retries": 2,
            "concurrency": 6,
        },
        "sources": {
            "tier_a": [{"name": "Test", "url": "https://example.com/feed"}],
            "tier_b": [],
            "tier_c": [{"name": "Tier C", "url": "https://example.com/html"}],
        },
        "pipeline": {
            "top_n": 10,
            "max_per_domain": 3,
            "fetch_body_for_selected": True,
            "body_fetch_timeout_seconds": 5,
            "body_fetch_max_chars": 4000,
            "categories": ["IP", "ETC"],
        },
        "dedup": {"retention_days": 30},
        "site": {"base_url": "/game-legal-briefing"},
        "email": {
            "subject_prefix": "[Test]",
            "web_url": "https://example.com/briefing",
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as handle:
        yaml.safe_dump(data, handle)
        path = handle.name
    try:
        cfg = load_config(path)
        assert cfg.llm.provider == "groq"
        assert cfg.llm.model == "openai/gpt-oss-120b"
        assert cfg.llm.summary_model == "qwen/qwen3.6-27b"
        assert cfg.llm.fallback_model == "openai/gpt-oss-120b"
        assert cfg.llm.reasoning_effort == "low"
        assert cfg.llm.summary_reasoning_effort == "none"
        assert cfg.llm.fallback_reasoning_effort == "low"
        assert cfg.llm.concurrency == 6
        assert cfg.pipeline.top_n == 10
        assert cfg.pipeline.max_per_domain == 3
        assert cfg.pipeline.fetch_body_for_selected is True
        assert cfg.pipeline.body_fetch_timeout_seconds == 5
        assert cfg.pipeline.body_fetch_max_chars == 4000
        assert cfg.sources.tier_a[0].name == "Test"
        assert cfg.sources.tier_c[0].name == "Tier C"
        assert cfg.site.base_url == "/game-legal-briefing"
        assert cfg.email.web_url == "https://example.com/briefing"
    finally:
        os.unlink(path)


def test_config_exposes_env_vars(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-123")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key-123")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as handle:
        yaml.safe_dump({"sources": {"tier_a": [], "tier_b": []}}, handle)
        path = handle.name
    try:
        cfg = load_config(path)
        assert cfg.google_api_key == "test-key-123"
        assert cfg.groq_api_key == "test-groq-key-123"
        assert cfg.pipeline.max_per_domain == 2
        assert cfg.pipeline.fetch_body_for_selected is False
        assert cfg.llm.concurrency == 4
    finally:
        os.unlink(path)
