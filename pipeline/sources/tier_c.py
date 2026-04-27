from __future__ import annotations

import logging
import os
import re
import urllib.request
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from pipeline.config import SourceEntry
from pipeline.sources.rss import FEED_TIMEOUT_SECONDS, RawArticle

logger = logging.getLogger(__name__)

MAX_ITEMS_PER_SOURCE = 20
USER_AGENT = "game-legal-briefing/1.0 (+https://github.com/lowtidebuild/game-legal-briefing)"


def _clean_text(text: str) -> str:
    return " ".join(text.split())


def _parse_korean_date(text: str) -> str:
    """Normalize supported Korean date formats to YYYY-MM-DD."""
    normalized = _clean_text(text)
    if not normalized:
        return ""

    for pattern in (
        r"(\d{4})[./-]\s*(\d{1,2})[./-]\s*(\d{1,2})\.?",
        r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일",
    ):
        match = re.search(pattern, normalized)
        if match:
            year, month, day = (int(value) for value in match.groups())
            return f"{year:04d}-{month:02d}-{day:02d}"

    if re.fullmatch(r"\d{1,2}[./]\d{1,2}\.?", normalized):
        return ""

    return ""


def _decode_html(response, payload: bytes) -> str:
    charsets: list[str] = []
    header_charset = response.headers.get_content_charset()
    if header_charset:
        charsets.append(header_charset)
    for charset in ("utf-8", "cp949", "euc-kr"):
        if charset not in charsets:
            charsets.append(charset)

    for charset in charsets:
        try:
            return payload.decode(charset)
        except UnicodeDecodeError:
            continue

    logger.warning("Falling back to replacement decode for %s", response.geturl())
    return payload.decode("utf-8", errors="replace")


def _fetch_html(source: SourceEntry) -> str | None:
    """Fetch one HTML source with a stable user agent."""
    request = urllib.request.Request(
        source.url,
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=FEED_TIMEOUT_SECONDS) as response:
            return _decode_html(response, response.read())
    except Exception as exc:
        logger.warning("Tier C fetch failed for %s: %s", source.name, exc)
        return None


def _article_from_row(
    *,
    source: SourceEntry,
    title: str,
    href: str,
    pub_date: str,
) -> RawArticle:
    return RawArticle(
        title=_clean_text(title),
        url=urljoin(source.url, href),
        source=source.name,
        description="",
        pub_date=_parse_korean_date(pub_date),
    )


def scrape_mcst(source: SourceEntry) -> list[RawArticle]:
    """Scrape 문화체육관광부 press releases."""
    html = _fetch_html(source)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    articles: list[RawArticle] = []
    for row in soup.select("tbody tr")[:MAX_ITEMS_PER_SOURCE]:
        link = row.select_one("td.tit_wrap a[href], td.subject a[href]")
        if link is None:
            continue

        title = link.get("title") or link.get_text(" ", strip=True)
        date_cell = row.find("td", attrs={"aria-label": re.compile(r"(게시일|등록일)")})
        if date_cell is None:
            cells = row.find_all("td")
            date_cell = cells[-2] if len(cells) >= 3 else None
        pub_date = date_cell.get_text(" ", strip=True) if date_cell else ""
        articles.append(
            _article_from_row(
                source=source,
                title=title,
                href=link["href"],
                pub_date=pub_date,
            )
        )
    return articles


def scrape_grac(source: SourceEntry) -> list[RawArticle]:
    """Scrape 게임물관리위원회 notice board."""
    html = _fetch_html(source)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    articles: list[RawArticle] = []
    for row in soup.select("table.topTable tbody tr")[:MAX_ITEMS_PER_SOURCE]:
        link = row.select_one("td.subject a[href]")
        cells = row.find_all("td")
        if link is None or len(cells) < 3:
            continue

        articles.append(
            _article_from_row(
                source=source,
                title=link.get_text(" ", strip=True),
                href=link["href"],
                pub_date=cells[2].get_text(" ", strip=True),
            )
        )
    return articles


def scrape_kftc(source: SourceEntry) -> list[RawArticle]:
    """Scrape 공정거래위원회 press releases."""
    html = _fetch_html(source)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    articles: list[RawArticle] = []
    for row in soup.select("tbody.text-center tr")[:MAX_ITEMS_PER_SOURCE]:
        link = row.select_one("td.p-subject a[href]")
        cells = row.find_all("td")
        if link is None or len(cells) < 5:
            continue

        title_node = link.select_one(".p-table__text")
        title = title_node.get_text(" ", strip=True) if title_node else link.get_text(" ", strip=True)
        articles.append(
            _article_from_row(
                source=source,
                title=title,
                href=link["href"],
                pub_date=cells[4].get_text(" ", strip=True),
            )
        )
    return articles


SCRAPER_REGISTRY = {
    "문화체육관광부": scrape_mcst,
    "게임물관리위원회": scrape_grac,
    "공정거래위원회": scrape_kftc,
}


def fetch_tier_c(sources: list[SourceEntry]) -> list[RawArticle]:
    """Fetch all configured Tier C sources with per-source graceful failure."""
    collected: list[RawArticle] = []
    for source in sources:
        scraper = SCRAPER_REGISTRY.get(source.name)
        if scraper is None:
            logger.info("Tier C scraper not implemented for %s - skipping", source.name)
            continue

        try:
            articles = scraper(source)
            logger.info("Tier C scraped %d articles from %s", len(articles), source.name)
            collected.extend(articles)
        except Exception as exc:
            logger.warning("Tier C scrape failed for %s: %s", source.name, exc)
    return collected


def unimplemented_sources(sources: list[SourceEntry]) -> list[SourceEntry]:
    """Return configured Tier C sources without a scraper implementation."""
    return [source for source in sources if source.name not in SCRAPER_REGISTRY]


def write_sources_backlog(
    sources: list[SourceEntry],
    path: str = "docs/sources-backlog.md",
) -> str:
    """Write a markdown backlog of configured Tier C sources still needing scrapers."""
    missing = unimplemented_sources(sources)
    lines = [
        "# Sources Backlog",
        "",
        "Tier C sources configured without scraper support.",
        "",
        "| Source | URL |",
        "|---|---|",
    ]
    if missing:
        lines.extend(f"| {source.name} | {source.url} |" for source in missing)
    else:
        lines.append("| None |  |")
    content = "\n".join(lines) + "\n"

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            if handle.read() == content:
                return path
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path
