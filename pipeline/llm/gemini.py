from __future__ import annotations

import json
import time
from types import SimpleNamespace

try:  # pragma: no cover - import availability depends on environment
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover - handled at runtime
    genai = SimpleNamespace(Client=None)
    types = SimpleNamespace(GenerateContentConfig=lambda **kwargs: kwargs)

from pipeline.llm.base import LLMProvider, extract_json_from_text


class GeminiProvider(LLMProvider):
    """Google Gemini provider implementation."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.1-flash-lite",
        max_retries: int = 2,
        request_timeout_seconds: int = 30,
    ):
        super().__init__(max_retries=max_retries, request_timeout_seconds=request_timeout_seconds)
        if getattr(genai, "Client", None) is None:
            raise ImportError("google-genai is required for GeminiProvider")
        self._client = genai.Client(api_key=api_key)
        self._model_name = model

    def _call_api(self, prompt: str, system: str | None = None) -> str:
        config = None
        if system:
            config = types.GenerateContentConfig(system_instruction=system)
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=prompt,
            config=config,
        )
        return response.text

    def generate_json(self, prompt: str, system: str | None = None) -> dict | list:
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
        )
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=self._model_name,
                    contents=prompt,
                    config=config,
                )
            except Exception as exc:
                last_error = exc
                if attempt == self.max_retries:
                    break
                time.sleep(min(2**attempt, 4))
                continue

            if getattr(response, "parsed", None) is not None:
                return response.parsed
            try:
                return json.loads(response.text)
            except json.JSONDecodeError:
                extracted = extract_json_from_text(response.text)
                if extracted is not None:
                    return extracted
                last_error = ValueError(f"Could not parse JSON from Gemini response: {response.text[:200]}")
                if attempt == self.max_retries:
                    break
                time.sleep(min(2**attempt, 4))

        assert last_error is not None
        raise last_error
