from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    text: str


def extract_json_from_text(text: str) -> dict | list | None:
    """Extract a JSON object or array from plain text or a fenced code block."""
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence_match:
        candidate = fence_match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    for pattern in (r"\{[\s\S]*\}", r"\[[\s\S]*\]"):
        inline_match = re.search(pattern, text)
        if not inline_match:
            continue
        try:
            return json.loads(inline_match.group(0))
        except json.JSONDecodeError:
            continue
    return None


class LLMProvider(ABC):
    """Base interface for LLM API calls with lightweight retry handling."""

    def __init__(self, max_retries: int = 2, request_timeout_seconds: int = 30):
        self.max_retries = max_retries
        self.request_timeout_seconds = request_timeout_seconds

    @abstractmethod
    def _call_api(self, prompt: str, system: str | None = None) -> str:
        """Execute a single provider API call and return raw text."""

    def generate(self, prompt: str, system: str | None = None) -> LLMResponse:
        """Return raw LLM text, retrying transient failures."""
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return LLMResponse(text=self._call_api(prompt, system))
            except Exception as exc:  # pragma: no cover - exercised via mocks
                last_error = exc
                if attempt == self.max_retries:
                    break
                wait_seconds = min(2**attempt, 4)
                logger.warning(
                    "LLM generate failed on attempt %d/%d: %s",
                    attempt + 1,
                    self.max_retries + 1,
                    exc,
                )
                time.sleep(wait_seconds)
        assert last_error is not None
        raise last_error

    def generate_json(self, prompt: str, system: str | None = None) -> dict | list:
        """Return parsed JSON, retrying when the provider emits invalid text."""
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                text = self._call_api(prompt, system)
            except Exception as exc:  # pragma: no cover - exercised via mocks
                last_error = exc
                if attempt == self.max_retries:
                    break
                time.sleep(min(2**attempt, 4))
                continue

            try:
                return json.loads(text)
            except json.JSONDecodeError:
                extracted = extract_json_from_text(text)
                if extracted is not None:
                    return extracted
                last_error = ValueError(f"Could not parse JSON from provider output: {text[:200]}")
                logger.warning(
                    "LLM returned invalid JSON on attempt %d/%d",
                    attempt + 1,
                    self.max_retries + 1,
                )
        assert last_error is not None
        raise last_error

