from __future__ import annotations

from pipeline.config import LLMConfig
from pipeline.llm.base import LLMProvider


def create_provider(
    cfg: LLMConfig,
    google_api_key: str | None = None,
    anthropic_api_key: str | None = None,
) -> LLMProvider:
    """Create an LLM provider from config."""
    if cfg.provider == "gemini":
        if not google_api_key:
            raise ValueError("GOOGLE_API_KEY required for Gemini provider")
        from pipeline.llm.gemini import GeminiProvider

        return GeminiProvider(
            api_key=google_api_key,
            model=cfg.model,
            max_retries=cfg.max_retries,
            request_timeout_seconds=cfg.request_timeout_seconds,
        )

    if cfg.provider == "claude":
        if not anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY required for Claude provider")
        from pipeline.llm.claude import ClaudeProvider

        return ClaudeProvider(
            api_key=anthropic_api_key,
            model=cfg.model,
            max_retries=cfg.max_retries,
            request_timeout_seconds=cfg.request_timeout_seconds,
        )

    raise ValueError(f"Unknown LLM provider: {cfg.provider}")
