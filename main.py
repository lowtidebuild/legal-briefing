"""Game Legal Briefing CLI orchestrator."""
from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime

try:  # pragma: no cover - import availability depends on environment
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - graceful fallback
    def load_dotenv() -> None:
        return None

from pipeline.admin.sheets import sync_to_sheets
from pipeline.config import load_config
from pipeline.deliver.mailer import send_briefing_email
from pipeline.intelligence.classifier import classify_article
from pipeline.intelligence.dedup import DedupEntry, DedupIndex, deduplicate_articles, url_hash
from pipeline.intelligence.selector import select_top_articles
from pipeline.intelligence.summarizer import summarize_article
from pipeline.llm import create_provider
from pipeline.llm.base import LLMProvider
from pipeline.llm.offline import OfflineLLMProvider
from pipeline.render.email import render_email
from pipeline.render.site import copy_static, render_archive, render_article_pages, render_index
from pipeline.sources.filters import keyword_filter
from pipeline.sources.rss import fetch_all_feeds, sample_articles
from pipeline.store.daily import load_daily, save_daily
from pipeline.store.dedup_index import load_dedup_index, prune_old_entries, save_dedup_index
from pipeline.store.nodes import assemble_node
from pipeline.store.query import list_briefing_dates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _build_provider(cfg, use_sample_data: bool) -> LLMProvider:
    try:
        return create_provider(
            cfg.llm,
            google_api_key=cfg.google_api_key,
            anthropic_api_key=cfg.anthropic_api_key,
        )
    except Exception as exc:
        if use_sample_data:
            logger.warning("Falling back to offline sample mode without live LLM access: %s", exc)
            return OfflineLLMProvider()
        raise


def run_pipeline(
    config_path: str = "config.yaml",
    output_dir: str = "output",
    template_dir: str = "templates",
    static_dir: str = "static",
    dry_run: bool = False,
    use_sample_data: bool = False,
) -> None:
    """Run the full Game Legal Briefing pipeline."""
    load_dotenv()
    cfg = load_config(config_path)
    today = datetime.now().strftime("%Y-%m-%d")

    output_data_dir = os.path.join(output_dir, "data", "daily")
    dedup_path = os.path.join(output_dir, "data", "dedup_index.json")

    llm = _build_provider(cfg, use_sample_data=use_sample_data)

    articles = sample_articles() if use_sample_data else fetch_all_feeds(
        tier_a=cfg.sources.tier_a,
        tier_b=cfg.sources.tier_b,
    )
    articles = keyword_filter(articles, keywords=cfg.pipeline.keywords)

    dedup_index = DedupIndex() if use_sample_data else prune_old_entries(
        load_dedup_index(dedup_path), today=today, retention_days=cfg.dedup.retention_days,
    )
    articles = deduplicate_articles(articles, dedup_index)
    articles = select_top_articles(articles, llm, top_n=cfg.pipeline.top_n, max_input_chars=cfg.llm.max_input_chars)

    nodes = []
    for article in articles:
        classification = classify_article(article, llm)
        summary_ko = summarize_article(article, llm)
        nodes.append(assemble_node(article, classification, summary_ko))

    existing_event_keys = {entry.event_key for entry in dedup_index.entries if entry.event_key}
    unique_nodes = []
    seen_event_keys: set[str] = set()
    for node in nodes:
        if node.event_key in existing_event_keys or node.event_key in seen_event_keys:
            continue
        seen_event_keys.add(node.event_key)
        unique_nodes.append(node)
    nodes = unique_nodes

    save_daily(nodes, today, data_dir=output_data_dir)

    if not use_sample_data:
        for node in nodes:
            dedup_index.entries.append(
                DedupEntry(event_key=node.event_key, url_hash=url_hash(node.url), date=today)
            )
        save_dedup_index(dedup_index, dedup_path)

    render_index(
        nodes=nodes,
        date=today,
        output_dir=output_dir,
        template_dir=template_dir,
        base_url=cfg.site.base_url,
    )

    archive_entries = [
        {"date": date, "count": len(load_daily(date, data_dir=output_data_dir))}
        for date in list_briefing_dates(data_dir=output_data_dir)
    ]
    render_archive(
        entries=archive_entries,
        output_dir=output_dir,
        template_dir=template_dir,
        base_url=cfg.site.base_url,
    )
    render_article_pages(
        nodes=nodes,
        output_dir=output_dir,
        template_dir=template_dir,
        base_url=cfg.site.base_url,
    )
    copy_static(output_dir=output_dir, static_dir=static_dir)

    if not dry_run and nodes and cfg.smtp_user and cfg.smtp_pass and cfg.recipients:
        send_briefing_email(
            html_body=render_email(nodes, today, template_dir=template_dir),
            subject=f"{cfg.email.subject_prefix} {today}",
            smtp_user=cfg.smtp_user,
            smtp_pass=cfg.smtp_pass,
            recipients=cfg.recipients,
        )
    elif not nodes:
        logger.info("No articles to report, skipping email delivery")

    if not dry_run and nodes:
        sync_to_sheets(nodes, cfg.google_sheets_credentials, cfg.google_sheets_id)

    logger.info("Pipeline complete with %d published nodes", len(nodes))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Game Legal Briefing site and outputs")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--output", default="output", help="Directory for generated output")
    parser.add_argument("--templates", default="templates", help="Template directory")
    parser.add_argument("--static", default="static", help="Static asset directory")
    parser.add_argument("--dry-run", action="store_true", help="Skip email and Sheets delivery")
    parser.add_argument(
        "--sample-data",
        action="store_true",
        help="Use built-in sample articles when secrets or live feeds are not configured",
    )
    args = parser.parse_args()

    run_pipeline(
        config_path=args.config,
        output_dir=args.output,
        template_dir=args.templates,
        static_dir=args.static,
        dry_run=args.dry_run,
        use_sample_data=args.sample_data,
    )


if __name__ == "__main__":
    main()
