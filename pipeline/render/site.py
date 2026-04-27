from __future__ import annotations

import logging
import os
import shutil

from jinja2 import Environment, FileSystemLoader, select_autoescape

from pipeline.models import BriefingNode

logger = logging.getLogger(__name__)


def _normalize_base_url(base_url: str) -> str:
    if not base_url:
        return ""
    return base_url.rstrip("/")


def _get_env(template_dir: str) -> Environment:
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _write_if_changed(path: str, html: str) -> bool:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            if handle.read() == html:
                return False
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(html)
    return True


def render_index(
    nodes: list[BriefingNode],
    date: str,
    output_dir: str = "output",
    template_dir: str = "templates",
    base_url: str = "",
) -> str:
    """Render the latest briefing page and a dated archive copy."""
    normalized_base_url = _normalize_base_url(base_url)
    env = _get_env(template_dir)
    template = env.get_template("index.html")
    html = template.render(nodes=nodes, date=date, base_url=normalized_base_url)

    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "index.html")
    _write_if_changed(path, html)

    archive_dir = os.path.join(output_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)
    archive_path = os.path.join(archive_dir, f"{date}.html")
    _write_if_changed(archive_path, html)

    logger.info("Rendered latest page and archive snapshot for %s", date)
    return path


def render_archive(
    entries: list[dict],
    output_dir: str = "output",
    template_dir: str = "templates",
    base_url: str = "",
    all_daily_nodes: dict | None = None,
) -> str:
    """Render the archive index page and per-date archive pages."""
    normalized_base_url = _normalize_base_url(base_url)
    env = _get_env(template_dir)
    template = env.get_template("archive.html")
    html = template.render(entries=entries, base_url=normalized_base_url)

    archive_dir = os.path.join(output_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)
    path = os.path.join(archive_dir, "index.html")
    _write_if_changed(path, html)

    # Render per-date archive pages (always overwrite to stay in sync with JSON)
    if all_daily_nodes:
        index_template = env.get_template("index.html")
        for date, nodes in all_daily_nodes.items():
            date_path = os.path.join(archive_dir, f"{date}.html")
            date_html = index_template.render(nodes=nodes, date=date, base_url=normalized_base_url)
            _write_if_changed(date_path, date_html)

    logger.info("Rendered archive listing with %d dates", len(entries))
    return path


def render_article_pages(
    nodes: list[BriefingNode],
    output_dir: str = "output",
    template_dir: str = "templates",
    base_url: str = "",
) -> None:
    """Render one detail page per briefing node."""
    normalized_base_url = _normalize_base_url(base_url)
    env = _get_env(template_dir)
    template = env.get_template("article.html")

    article_dir = os.path.join(output_dir, "article")
    os.makedirs(article_dir, exist_ok=True)
    for node in nodes:
        html = template.render(node=node, base_url=normalized_base_url)
        path = os.path.join(article_dir, f"{node.event_key}.html")
        _write_if_changed(path, html)

    logger.info("Rendered %d article pages", len(nodes))


def copy_static(output_dir: str = "output", static_dir: str = "static") -> None:
    """Copy static assets into the output directory."""
    if not os.path.exists(static_dir):
        return
    destination = os.path.join(output_dir, "static")
    shutil.copytree(static_dir, destination, dirs_exist_ok=True)
    logger.info("Copied static assets to %s", destination)
