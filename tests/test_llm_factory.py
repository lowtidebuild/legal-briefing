from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pipeline.config import LLMConfig
from pipeline.llm import create_provider
from pipeline.llm.claude import ClaudeProvider
from pipeline.llm.gemini import GeminiProvider
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


def test_create_provider_unknown_raises():
    cfg = LLMConfig(provider="unknown")
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        create_provider(cfg)


def test_create_provider_can_use_offline_fallback():
    cfg = LLMConfig(provider="gemini")
    provider = create_provider(cfg, offline_fallback=True, offline_context="dry-run mode")
    assert isinstance(provider, OfflineLLMProvider)
