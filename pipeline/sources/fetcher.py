from __future__ import annotations

import logging
import urllib.request

from bs4 import BeautifulSoup

USER_AGENT = "game-legal-briefing/1.0 (+https://github.com/lowtidebuild/legal-briefing)"

logger = logging.getLogger(__name__)


def fetch_article_body(url: str, timeout: int = 10, max_chars: int = 8000) -> str:
    """Fetch a readable article body, returning an empty string on failure."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            html = response.read()
    except Exception as exc:
        logger.info("Article body fetch failed for %s: %s", url, exc)
        return ""

    try:
        soup = BeautifulSoup(html, "html.parser")
        for element in soup(["script", "style", "noscript", "svg"]):
            element.decompose()

        main = (
            soup.find("article")
            or soup.find("main")
            or soup.find(attrs={"role": "main"})
            or soup.body
            or soup
        )
        text = main.get_text(" ", strip=True)
        return " ".join(text.split())[:max_chars]
    except Exception as exc:
        logger.info("Article body parse failed for %s: %s", url, exc)
        return ""
