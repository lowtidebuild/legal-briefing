from __future__ import annotations

from types import SimpleNamespace

try:  # pragma: no cover - import availability depends on environment
    import anthropic
except ImportError:  # pragma: no cover - handled at runtime
    anthropic = SimpleNamespace(Anthropic=None)

from pipeline.llm.base import LLMProvider


class ClaudeProvider(LLMProvider):
    """Anthropic Claude provider implementation."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-haiku-4-5-20251001",
        max_retries: int = 2,
        request_timeout_seconds: int = 30,
    ):
        super().__init__(max_retries=max_retries, request_timeout_seconds=request_timeout_seconds)
        if getattr(anthropic, "Anthropic", None) is None:
            raise ImportError("anthropic is required for ClaudeProvider")
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model_name = model

    def _call_api(self, prompt: str, system: str | None = None) -> str:
        response = self._client.messages.create(
            model=self._model_name,
            max_tokens=4096,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def generate_json(self, prompt: str, system: str | None = None) -> dict | list:
        return self.generate_json_schema(prompt=prompt, schema={}, system=system)

    def generate_json_schema(
        self,
        prompt: str,
        schema: dict,
        system: str | None = None,
    ) -> dict | list:
        tool_schema = schema or {"type": "object", "additionalProperties": True}
        response = self._client.messages.create(
            model=self._model_name,
            max_tokens=4096,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
            tools=[
                {
                    "name": "respond",
                    "description": "Return the JSON response",
                    "input_schema": tool_schema,
                }
            ],
            tool_choice={"type": "tool", "name": "respond"},
        )
        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                return block.input
        return super().generate_json(prompt, system=system)
