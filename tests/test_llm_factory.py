from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pipeline.config import LLMConfig
from pipeline.llm import create_provider
from pipeline.llm.claude import ClaudeProvider
from pipeline.llm.gemini import GeminiProvider
from pipeline.llm.groq import GroqProvider
from pipeline.llm.offline import OfflineLLMProvider


def test_create_gemini_provider():
    cfg = LLMConfig(provider="gemini", model="gemini-3.1-flash-lite")
    with patch("pipeline.llm.gemini.genai", new=SimpleNamespace(Client=lambda api_key: object())):
        provider = create_provider(cfg, google_api_key="test-key")
    assert isinstance(provider, GeminiProvider)


def test_create_claude_provider():
    cfg = LLMConfig(provider="claude", model="claude-haiku-4-5-20251001")
    with patch("pipeline.llm.claude.anthropic", new=SimpleNamespace(Anthropic=lambda api_key: object())):
        provider = create_provider(cfg, anthropic_api_key="test-key")
    assert isinstance(provider, ClaudeProvider)


def test_create_groq_provider():
    cfg = LLMConfig(
        provider="groq",
        model="openai/gpt-oss-120b",
        reasoning_effort="low",
    )
    with patch("pipeline.llm.groq.groq_sdk.Groq", return_value=object()):
        provider = create_provider(cfg, groq_api_key="test-key")
    assert isinstance(provider, GroqProvider)


def test_create_groq_summary_provider_has_model_fallback():
    cfg = LLMConfig(
        provider="groq",
        model="qwen/qwen3.6-27b",
        fallback_model="openai/gpt-oss-120b",
        reasoning_effort="none",
        fallback_reasoning_effort="low",
    )
    with patch("pipeline.llm.groq.groq_sdk.Groq", return_value=object()):
        provider = create_provider(cfg, groq_api_key="test-key")

    assert provider._primary._model_name == "qwen/qwen3.6-27b"
    assert provider._secondary._model_name == "openai/gpt-oss-120b"


def test_create_provider_unknown_raises():
    cfg = LLMConfig(provider="unknown")
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        create_provider(cfg)


def test_create_provider_can_use_offline_fallback():
    cfg = LLMConfig(provider="gemini")
    provider = create_provider(cfg, offline_fallback=True, offline_context="dry-run mode")
    assert isinstance(provider, OfflineLLMProvider)
