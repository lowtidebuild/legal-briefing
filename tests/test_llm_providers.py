from unittest.mock import MagicMock, patch

import pytest

from pipeline.llm.claude import ClaudeProvider
from pipeline.llm.gemini import GeminiProvider
from pipeline.llm.groq import GroqProvider
from pipeline.llm.rate_limit import ModelCircuitOpen, RateLimitGate


def test_gemini_provider_calls_model():
    with patch("pipeline.llm.gemini.genai") as mock_genai:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"result": "ok"}'
        mock_client.models.generate_content.return_value = mock_response
        mock_genai.Client.return_value = mock_client

        provider = GeminiProvider(api_key="test-key", model="gemini-3.1-flash-lite")
        assert provider._call_api("test prompt") == '{"result": "ok"}'


def test_gemini_provider_applies_timeout_in_milliseconds():
    with patch("pipeline.llm.gemini.genai") as mock_genai, patch("pipeline.llm.gemini.types") as mock_types:
        mock_types.HttpOptions.side_effect = lambda **kwargs: kwargs
        mock_genai.Client.return_value = MagicMock()

        GeminiProvider(api_key="test-key", request_timeout_seconds=45)

    assert mock_genai.Client.call_args.kwargs["http_options"] == {"timeout": 45000}


def test_gemini_rate_limit_uses_retry_info_delay_once():
    class RateLimitError(RuntimeError):
        code = 429

    sleeps = []
    gate = RateLimitGate(clock=lambda: 100.0, sleep=sleeps.append)
    with patch("pipeline.llm.gemini.genai") as mock_genai:
        response = MagicMock(text='{"result": "ok"}', parsed={"result": "ok"})
        client = MagicMock()
        client.models.generate_content.side_effect = [
            RateLimitError("429 RESOURCE_EXHAUSTED: retry in 45s"),
            response,
        ]
        mock_genai.Client.return_value = client
        provider = GeminiProvider(
            api_key="test-key",
            model="gemini-3.5-flash",
            rate_limit_gate=gate,
        )

        assert provider.generate_json("test") == {"result": "ok"}

    assert sleeps == [45.0]
    assert provider.metrics.rate_limits == 1
    assert client.models.generate_content.call_count == 2


def test_gemini_shared_gate_opens_circuit_after_second_rate_limit():
    class RateLimitError(RuntimeError):
        code = 429

    gate = RateLimitGate(clock=lambda: 100.0, sleep=lambda _seconds: None)
    with patch("pipeline.llm.gemini.genai") as mock_genai:
        first_client = MagicMock()
        first_client.models.generate_content.side_effect = RateLimitError(
            "429 RESOURCE_EXHAUSTED: retry in 1s"
        )
        second_client = MagicMock()
        mock_genai.Client.side_effect = [first_client, second_client]
        first = GeminiProvider(api_key="key", model="gemini-3.5-flash", rate_limit_gate=gate)
        second = GeminiProvider(api_key="key", model="gemini-3.5-flash", rate_limit_gate=gate)

        with pytest.raises(RateLimitError):
            first.generate_json("test")
        with pytest.raises(ModelCircuitOpen):
            second.generate_json("test")

    assert first_client.models.generate_content.call_count == 2
    second_client.models.generate_content.assert_not_called()


def test_gemini_provider_uses_response_schema():
    with patch("pipeline.llm.gemini.genai") as mock_genai, patch("pipeline.llm.gemini.types") as mock_types:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"result": "ok"}'
        mock_response.parsed = None
        mock_client.models.generate_content.return_value = mock_response
        mock_genai.Client.return_value = mock_client
        mock_types.GenerateContentConfig.side_effect = lambda **kwargs: kwargs

        provider = GeminiProvider(api_key="test-key", model="gemini-3.1-flash-lite")
        result = provider.generate_json_schema("test prompt", schema={"type": "object"})

        assert result == {"result": "ok"}
        config = mock_client.models.generate_content.call_args.kwargs["config"]
        assert config["response_schema"] == {"type": "object"}


def test_gemini_provider_passes_thinking_level():
    with patch("pipeline.llm.gemini.genai") as mock_genai, patch("pipeline.llm.gemini.types") as mock_types:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"result": "ok"}'
        mock_response.parsed = None
        mock_client.models.generate_content.return_value = mock_response
        mock_genai.Client.return_value = mock_client
        mock_types.ThinkingConfig.side_effect = lambda **kwargs: kwargs
        mock_types.GenerateContentConfig.side_effect = lambda **kwargs: kwargs

        provider = GeminiProvider(
            api_key="test-key",
            model="gemini-3.5-flash",
            reasoning_effort="low",
        )
        provider.generate_json("test prompt")

    config = mock_client.models.generate_content.call_args.kwargs["config"]
    assert config["thinking_config"] == {"thinking_level": "low"}


def test_claude_provider_calls_client():
    with patch("pipeline.llm.claude.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"result": "ok"}')]
        mock_client.messages.create.return_value = mock_response
        mock_cls.return_value = mock_client

        provider = ClaudeProvider(api_key="test-key", model="claude-haiku-4-5-20251001")
        assert provider._call_api("test prompt", system="be helpful") == '{"result": "ok"}'


def test_claude_provider_uses_tool_for_json():
    with patch("pipeline.llm.claude.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(type="tool_use", input={"result": "ok"}),
        ]
        mock_client.messages.create.return_value = mock_response
        mock_cls.return_value = mock_client

        provider = ClaudeProvider(api_key="test-key", model="claude-haiku-4-5-20251001")
        result = provider.generate_json_schema("test prompt", schema={"type": "object"})

        assert result == {"result": "ok"}
        kwargs = mock_client.messages.create.call_args.kwargs
        assert kwargs["tool_choice"] == {"type": "tool", "name": "respond"}
    assert kwargs["tools"][0]["input_schema"] == {"type": "object"}


def test_groq_provider_uses_json_object_mode_and_hidden_reasoning():
    with patch("pipeline.llm.groq.groq_sdk.Groq") as mock_cls:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='{"result": "ok"}'))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_cls.return_value = mock_client

        provider = GroqProvider(
            api_key="test-key",
            model="qwen/qwen3.6-27b",
            reasoning_effort="none",
        )
        result = provider.generate_json("test prompt")

    assert result == {"result": "ok"}
    kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["reasoning_effort"] == "none"
    assert kwargs["reasoning_format"] == "hidden"


def test_groq_provider_uses_strict_json_schema():
    with patch("pipeline.llm.groq.groq_sdk.Groq") as mock_cls:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='{"result": "ok"}'))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_cls.return_value = mock_client

        provider = GroqProvider(
            api_key="test-key",
            model="openai/gpt-oss-120b",
            reasoning_effort="low",
        )
        result = provider.generate_json_schema(
            "test prompt",
            schema={
                "type": "object",
                "properties": {"result": {"type": "string"}},
            },
        )

    assert result == {"result": "ok"}
    response_format = mock_client.chat.completions.create.call_args.kwargs["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"]["required"] == ["result"]
    assert response_format["json_schema"]["schema"]["additionalProperties"] is False
