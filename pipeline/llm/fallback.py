"""Fallback LLM provider that tries primary, falls back to secondary on failure."""
from __future__ import annotations

import logging

from pipeline.llm.base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class FallbackProvider(LLMProvider):
    """Tries the primary provider first, falls back to secondary on any exception."""

    def __init__(self, primary: LLMProvider, secondary: LLMProvider):
        super().__init__(max_retries=0, request_timeout_seconds=0)
        self._primary = primary
        self._secondary = secondary

    def _call_api(self, prompt: str, system: str | None = None) -> str:
        try:
            return self._primary._call_api(prompt, system)
        except Exception as exc:
            logger.warning("Primary LLM failed, falling back to secondary: %s", exc)
            return self._secondary._call_api(prompt, system)

    def generate(self, prompt: str, system: str | None = None) -> LLMResponse:
        try:
            return self._primary.generate(prompt, system)
        except Exception as exc:
            logger.warning("Primary LLM generate failed, falling back: %s", exc)
            return self._secondary.generate(prompt, system)

    def generate_json(self, prompt: str, system: str | None = None) -> dict | list:
        try:
            return self._primary.generate_json(prompt, system)
        except Exception as exc:
            logger.warning("Primary LLM generate_json failed, falling back: %s", exc)
            return self._secondary.generate_json(prompt, system)
