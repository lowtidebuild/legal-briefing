from unittest.mock import MagicMock, patch

from pipeline.sources.fetcher import fetch_article_body


def test_fetch_article_body_extracts_article_text():
    response = MagicMock()
    response.read.return_value = b"""
    <html><body>
      <script>ignore()</script>
      <article><h1>Title</h1><p>Main body text.</p></article>
    </body></html>
    """
    response.__enter__.return_value = response
    response.__exit__.return_value = False

    with patch("pipeline.sources.fetcher.urllib.request.urlopen", return_value=response):
        assert fetch_article_body("https://example.com") == "Title Main body text."


def test_fetch_article_body_returns_empty_on_failure():
    with patch("pipeline.sources.fetcher.urllib.request.urlopen", side_effect=RuntimeError("down")):
        assert fetch_article_body("https://example.com") == ""
