from __future__ import annotations

import json
import time
from types import SimpleNamespace

try:  # pragma: no cover - import availability depends on environment
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover - handled at runtime
    genai = SimpleNamespace(Client=None)
    types = SimpleNamespace(
        GenerateContentConfig=lambda **kwargs: kwargs,
        HttpOptions=lambda **kwargs: kwargs,
        ThinkingConfig=lambda **kwargs: kwargs,
    )

from pipeline.llm.base import LLMProvider, extract_json_from_text
from pipeline.llm.rate_limit import (
    RateLimitGate,
    is_rate_limit_error,
    is_transient_error,
    retry_delay_from_error,
)


class GeminiProvider(LLMProvider):
    """Google Gemini provider implementation."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.5-flash",
        reasoning_effort: str | None = None,
        max_retries: int = 2,
        request_timeout_seconds: int = 30,
        rate_limit_gate: RateLimitGate | None = None,
    ):
        super().__init__(max_retries=max_retries, request_timeout_seconds=request_timeout_seconds)
        if getattr(genai, "Client", None) is None:
            raise ImportError("google-genai is required for GeminiProvider")
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=request_timeout_seconds * 1000),
        )
        self._model_name = model
        self._reasoning_effort = reasoning_effort
        self._rate_limit_gate = rate_limit_gate or RateLimitGate()

    def _config_kwargs(self, system: str | None = None) -> dict:
        config_kwargs = {"system_instruction": system}
        if self._reasoning_effort:
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_level=self._reasoning_effort,
            )
        return config_kwargs

    def _call_api(self, prompt: str, system: str | None = None) -> str:
        config_kwargs = self._config_kwargs(system)
        config = types.GenerateContentConfig(**config_kwargs) if any(config_kwargs.values()) else None
        response = self._generate_content(prompt, config)
        return response.text

    def _generate_content(self, prompt: str, config):
        rate_limit_retry_used = False
        transient_attempt = 0
        while True:
            self._rate_limit_gate.before_call(self._model_name)
            self.metrics.attempts += 1
            try:
                response = self._client.models.generate_content(
                    model=self._model_name,
                    contents=prompt,
                    config=config,
                )
            except Exception as exc:
                self.metrics.failures += 1
                if is_rate_limit_error(exc):
                    self.metrics.rate_limits += 1
                    retry_delay = retry_delay_from_error(exc)
                    retry_allowed = self._rate_limit_gate.register_rate_limit(
                        self._model_name,
                        retry_delay,
                    )
                    if retry_allowed and not rate_limit_retry_used:
                        rate_limit_retry_used = True
                        continue
                    raise
                if is_transient_error(exc) and transient_attempt < self.max_retries:
                    time.sleep(min(2**transient_attempt, 4))
                    transient_attempt += 1
                    continue
                raise
            self.metrics.successes += 1
            return response

    def generate_json(self, prompt: str, system: str | None = None) -> dict | list:
        return self.generate_json_schema(prompt=prompt, schema={}, system=system)

    def generate_json_schema(
        self,
        prompt: str,
        schema: dict,
        system: str | None = None,
    ) -> dict | list:
        config_kwargs = self._config_kwargs(system)
        config_kwargs["response_mime_type"] = "application/json"
        if schema:
            config_kwargs["response_schema"] = schema
        config = types.GenerateContentConfig(
            **config_kwargs,
        )
        response = self._generate_content(prompt, config)
        if getattr(response, "parsed", None) is not None:
            return response.parsed
        try:
            return json.loads(response.text)
        except json.JSONDecodeError:
            extracted = extract_json_from_text(response.text)
            if extracted is not None:
                return extracted
            raise ValueError(f"Could not parse JSON from Gemini response: {response.text[:200]}")
