"""Generate /manifest.json for the briefing-hub aggregator.

Schema follows DESIGN.md §4 of the briefing-hub repo:
    { name, category, accent, description, url, updated_at, latest, items[] }

Reads from output/data/daily/*.json (each file is a list of article dicts).
Emits one manifest item per recent article. items[].url points to the
per-article briefing page on this site (Korean summary), not the original
English article — matches KP's value-add of curated Korean translation.

Run standalone for testing:
    python -m pipeline.render.manifest [output_dir]
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SITE_URL = "https://lowtidebuild.github.io/legal-briefing/"
NAME = "Game Legal Briefing"
CATEGORY = "Game · Legal"
ACCENT = "#6b2d5c"
DESCRIPTION = "게임 산업 규제 + 판례 + IP · 주 3회 큐레이션"
MAX_ITEMS = 10


def _published_at(pub_date: str | None) -> str:
    """Coerce YYYY-MM-DD to ISO 8601 UTC at 00:00."""
    if pub_date and isinstance(pub_date, str):
        try:
            d = datetime.strptime(pub_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return d.strftime("%Y-%m-%dT00:00:00Z")
        except ValueError:
            pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _article_url(event_key: str | None) -> str:
    """Per-article briefing page URL on the live site."""
    if event_key and isinstance(event_key, str):
        return f"{SITE_URL}article/{event_key}.html"
    return SITE_URL


def _title_for_article(article: dict[str, Any]) -> str:
    """Prefer Korean translated title; fall back to original."""
    for key in ("title_ko", "title"):
        v = article.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:200]
    return "(untitled)"


def _source_label(article: dict[str, Any]) -> str:
    """Original publisher (e.g. 'GamesIndustry.biz')."""
    src = article.get("source")
    if isinstance(src, str) and src.strip():
        return src.strip()
    return "Game Legal Briefing"


def _load_articles(daily_dir: Path) -> list[dict[str, Any]]:
    """Walk all daily JSONs, flatten into a single article list."""
    out: list[dict[str, Any]] = []
    for path in sorted(daily_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Skipping unreadable daily file %s: %s", path, e)
            continue
        if not isinstance(data, list):
            continue
        out.extend(item for item in data if isinstance(item, dict))
    return out


def build_manifest(output_dir: str | Path) -> dict[str, Any]:
    out = Path(output_dir)
    daily_dir = out / "data" / "daily"
    if not daily_dir.exists():
        logger.warning("No daily data at %s — manifest will be empty", daily_dir)
        return {
            "name": NAME,
            "category": CATEGORY,
            "accent": ACCENT,
            "description": DESCRIPTION,
            "url": SITE_URL,
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    articles = _load_articles(daily_dir)

    # Dedupe by event_key (latest occurrence wins — already iterating newest-first)
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for art in articles:
        key = art.get("event_key") or art.get("url")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(art)

    # Sort by pub_date descending (article publication date, not briefing date)
    deduped.sort(key=lambda a: a.get("pub_date") or "", reverse=True)

    items: list[dict[str, Any]] = []
    for art in deduped[:MAX_ITEMS]:
        items.append({
            "title": _title_for_article(art),
            "source": _source_label(art),
            "url": _article_url(art.get("event_key")),
            "published_at": _published_at(art.get("pub_date")),
        })

    latest = items[0] if items else None
    updated_at = (
        latest["published_at"]
        if latest
        else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    return {
        "name": NAME,
        "category": CATEGORY,
        "accent": ACCENT,
        "description": DESCRIPTION,
        "url": SITE_URL,
        "updated_at": updated_at,
        "latest": latest,
        "items": items,
    }


def write_manifest(output_dir: str | Path) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(out)
    target = out / "manifest.json"
    target.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Wrote %s (%d items)", target, len(manifest.get("items") or []))
    return target


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    output_dir = sys.argv[1] if len(sys.argv) > 1 else "output"
    write_manifest(output_dir)
