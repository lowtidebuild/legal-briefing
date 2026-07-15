from __future__ import annotations

import json
import time
from copy import deepcopy
from types import SimpleNamespace

try:  # pragma: no cover - import availability depends on environment
    import groq as groq_sdk
except ImportError:  # pragma: no cover - handled at runtime
    groq_sdk = SimpleNamespace(Groq=None)

from pipeline.llm.base import LLMProvider, extract_json_from_text


def _strict_schema(schema: dict) -> dict:
    """Make object schemas compatible with Groq strict structured output."""
    strict = deepcopy(schema)

    def normalize(node):
        if not isinstance(node, dict):
            return
        if node.get("type") == "object" and isinstance(node.get("properties"), dict):
            node["required"] = list(node["properties"])
            node["additionalProperties"] = False
            for child in node["properties"].values():
                normalize(child)
        if node.get("type") == "array":
            normalize(node.get("items"))

    normalize(strict)
    return strict


class GroqProvider(LLMProvider):
    """Groq chat-completions provider with JSON mode and strict schemas."""

    def __init__(
        self,
        api_key: str,
        model: str,
        reasoning_effort: str | None = None,
        max_retries: int = 2,
        request_timeout_seconds: int = 30,
    ):
        super().__init__(max_retries=max_retries, request_timeout_seconds=request_timeout_seconds)
        if getattr(groq_sdk, "Groq", None) is None:
            raise ImportError("groq is required for GroqProvider")
        self._client = groq_sdk.Groq(
            api_key=api_key,
            timeout=request_timeout_seconds,
        )
        self._model_name = model
        self._reasoning_effort = reasoning_effort

    def _messages(self, prompt: str, system: str | None) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _completion(
        self,
        prompt: str,
        system: str | None = None,
        response_format: dict | None = None,
    ) -> str:
        kwargs = {
            "model": self._model_name,
            "messages": self._messages(prompt, system),
            "max_completion_tokens": 2048,
        }
        if self._reasoning_effort:
            kwargs["reasoning_effort"] = self._reasoning_effort
            kwargs["reasoning_format"] = "hidden"
        if response_format:
            kwargs["response_format"] = response_format

        response = self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Groq returned an empty response")
        return content

    def _call_api(self, prompt: str, system: str | None = None) -> str:
        return self._completion(prompt, system)

    def _generate_json_payload(
        self,
        prompt: str,
        system: str | None,
        response_format: dict,
    ) -> dict | list:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                text = self._completion(
                    prompt,
                    system=system,
                    response_format=response_format,
                )
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    extracted = extract_json_from_text(text)
                    if extracted is not None:
                        return extracted
                    raise ValueError(f"Could not parse JSON from Groq response: {text[:200]}")
            except Exception as exc:
                last_error = exc
                if attempt == self.max_retries:
                    break
                time.sleep(min(2**attempt, 4))
        assert last_error is not None
        raise last_error

    def generate_json(self, prompt: str, system: str | None = None) -> dict | list:
        return self._generate_json_payload(
            prompt,
            system=system,
            response_format={"type": "json_object"},
        )

    def generate_json_schema(
        self,
        prompt: str,
        schema: dict,
        system: str | None = None,
    ) -> dict | list:
        return self._generate_json_payload(
            prompt,
            system=system,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "briefing_response",
                    "strict": True,
                    "schema": _strict_schema(schema),
                },
            },
        )
