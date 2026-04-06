from unittest.mock import MagicMock

from pipeline.llm.fallback import FallbackProvider


def test_fallback_uses_primary_on_success():
    primary = MagicMock()
    secondary = MagicMock()
    primary.generate_json.return_value = {"result": "ok"}
    provider = FallbackProvider(primary, secondary)
    result = provider.generate_json("test prompt")
    assert result == {"result": "ok"}
    secondary.generate_json.assert_not_called()


def test_fallback_uses_secondary_on_primary_failure():
    primary = MagicMock()
    secondary = MagicMock()
    primary.generate_json.side_effect = RuntimeError("API down")
    secondary.generate_json.return_value = {"fallback": True}
    provider = FallbackProvider(primary, secondary)
    result = provider.generate_json("test prompt")
    assert result == {"fallback": True}


def test_fallback_generate_uses_secondary_on_primary_failure():
    primary = MagicMock()
    secondary = MagicMock()
    primary.generate.side_effect = RuntimeError("timeout")
    secondary.generate.return_value = MagicMock(text="fallback text")
    provider = FallbackProvider(primary, secondary)
    result = provider.generate("test")
    assert result.text == "fallback text"
