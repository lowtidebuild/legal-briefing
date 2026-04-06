from __future__ import annotations

import logging

from pipeline.config import LLMConfig
from pipeline.llm.base import LLMProvider

logger = logging.getLogger(__name__)


def create_provider(
    cfg: LLMConfig,
    google_api_key: str | None = None,
    anthropic_api_key: str | None = None,
) -> LLMProvider:
    """Create an LLM provider from config, with automatic fallback when both keys are available."""
    primary = _create_single_provider(cfg, google_api_key, anthropic_api_key)

    # If both keys are available, wrap with fallback
    secondary = _try_create_secondary(cfg, google_api_key, anthropic_api_key)
    if secondary is not None:
        from pipeline.llm.fallback import FallbackProvider
        logger.info("Fallback provider configured: %s -> %s", cfg.provider, _secondary_provider_name(cfg))
        return FallbackProvider(primary=primary, secondary=secondary)

    return primary


def _create_single_provider(
    cfg: LLMConfig,
    google_api_key: str | None,
    anthropic_api_key: str | None,
) -> LLMProvider:
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


def _secondary_provider_name(cfg: LLMConfig) -> str:
    return "claude" if cfg.provider == "gemini" else "gemini"


def _try_create_secondary(
    cfg: LLMConfig,
    google_api_key: str | None,
    anthropic_api_key: str | None,
) -> LLMProvider | None:
    """Try to create a secondary provider for fallback. Returns None if not possible."""
    try:
        if cfg.provider == "gemini" and anthropic_api_key:
            from pipeline.llm.claude import ClaudeProvider
            return ClaudeProvider(
                api_key=anthropic_api_key,
                model="claude-haiku-4-5-20251001",
                max_retries=cfg.max_retries,
                request_timeout_seconds=cfg.request_timeout_seconds,
            )
        if cfg.provider == "claude" and google_api_key:
            from pipeline.llm.gemini import GeminiProvider
            return GeminiProvider(
                api_key=google_api_key,
                model="gemini-3.1-flash-lite",
                max_retries=cfg.max_retries,
                request_timeout_seconds=cfg.request_timeout_seconds,
            )
    except ImportError:
        pass
    return None
