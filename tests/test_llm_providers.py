from unittest.mock import MagicMock, patch

from pipeline.llm.claude import ClaudeProvider
from pipeline.llm.gemini import GeminiProvider


def test_gemini_provider_calls_model():
    with patch("pipeline.llm.gemini.genai") as mock_genai:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"result": "ok"}'
        mock_client.models.generate_content.return_value = mock_response
        mock_genai.Client.return_value = mock_client

        provider = GeminiProvider(api_key="test-key", model="gemini-3.1-flash-lite")
        assert provider._call_api("test prompt") == '{"result": "ok"}'


def test_claude_provider_calls_client():
    with patch("pipeline.llm.claude.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"result": "ok"}')]
        mock_client.messages.create.return_value = mock_response
        mock_cls.return_value = mock_client

        provider = ClaudeProvider(api_key="test-key", model="claude-haiku-4-5-20251001")
        assert provider._call_api("test prompt", system="be helpful") == '{"result": "ok"}'
