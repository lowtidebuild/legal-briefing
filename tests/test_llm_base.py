from pipeline.llm.base import LLMProvider, LLMResponse, extract_json_from_text


class MockProvider(LLMProvider):
    def __init__(self, responses: list[str]):
        super().__init__(max_retries=2, request_timeout_seconds=5)
        self._responses = responses
        self._call_count = 0

    def _call_api(self, prompt: str, system: str | None = None) -> str:
        index = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        return self._responses[index]


def test_generate_returns_response():
    provider = MockProvider(['{"result": "ok"}'])
    response = provider.generate("test prompt")
    assert isinstance(response, LLMResponse)
    assert response.text == '{"result": "ok"}'


def test_generate_json_handles_markdown_and_retries():
    provider = MockProvider(["not json", '```json\n{"key": "value"}\n```'])
    result = provider.generate_json("test prompt")
    assert result == {"key": "value"}
    assert provider._call_count == 2


def test_extract_json_from_text_returns_none_for_missing_payload():
    assert extract_json_from_text("no json here") is None

