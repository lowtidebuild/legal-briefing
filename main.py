"""Game Legal Briefing CLI orchestrator."""
from __future__ import annotations

import argparse
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime
from typing import Callable, TypeVar

try:  # pragma: no cover - import availability depends on environment
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - graceful fallback
    def load_dotenv() -> None:
        return None

from pipeline.admin.sheets import read_event_keys_from_sheets, sync_to_sheets
from pipeline.config import load_config
from pipeline.deliver.mailer import send_briefing_email
from pipeline.intelligence.classifier import classify_article
from pipeline.intelligence.dedup import DedupEntry, DedupIndex, deduplicate_articles, url_hash
from pipeline.intelligence.event_dedup import build_classified_article, dedup_classified_articles
from pipeline.intelligence.selector import select_top_articles
from pipeline.intelligence.summarizer import summarize_article
from pipeline.llm import create_provider
from pipeline.render.email import render_email
from pipeline.render.site import copy_static, render_archive, render_article_pages, render_index
from pipeline.sources.fetcher import fetch_article_body
from pipeline.sources.filters import keyword_filter, normalize_pub_dates, recency_filter
from pipeline.sources.rss import fetch_all_feeds_with_report, sample_articles
from pipeline.store.daily import load_daily, save_daily
from pipeline.store.dedup_index import load_dedup_index, prune_old_entries, save_dedup_index
from pipeline.store.nodes import assemble_node
from pipeline.store.query import list_briefing_dates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)
T = TypeVar("T")
U = TypeVar("U")


def _map_ordered(func: Callable[[T], U], items: list[T], max_workers: int) -> list[U]:
    if len(items) <= 1 or max_workers <= 1:
        return [func(item) for item in items]
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(func, items))


def _handle_operational_issue(message: str, dry_run: bool, exit_code: int) -> None:
    if dry_run:
        logger.warning("%s; dry-run continues", message)
        return
    logger.error(message)
    raise SystemExit(exit_code)


def _useful_time_hint(value: str) -> bool:
    normalized = " ".join(value.lower().split())
    return bool(normalized) and normalized not in {"current", "ongoing", "months", "recent"}


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

    llm = create_provider(
        cfg.llm,
        google_api_key=cfg.google_api_key,
        anthropic_api_key=cfg.anthropic_api_key,
        offline_fallback=use_sample_data or dry_run,
        offline_context="sample mode" if use_sample_data else "dry-run mode",
    )

    if use_sample_data:
        articles = sample_articles()
    else:
        feed_report = fetch_all_feeds_with_report(
            tier_a=cfg.sources.tier_a,
            tier_b=cfg.sources.tier_b,
        )
        if feed_report.tier_a_failure_rate >= 0.5:
            _handle_operational_issue(
                (
                    "Tier A feed health check failed: "
                    f"{feed_report.tier_a_empty}/{feed_report.tier_a_total} sources returned no articles"
                ),
                dry_run=dry_run,
                exit_code=2,
            )
        articles = feed_report.articles
        from pipeline.sources.tier_c import fetch_tier_c

        articles.extend(fetch_tier_c(cfg.sources.tier_c))
    articles = keyword_filter(articles, keywords=cfg.pipeline.keywords)
    if not use_sample_data and len(articles) < 10:
        _handle_operational_issue(
            f"Pipeline health check failed: only {len(articles)} articles after keyword filter",
            dry_run=dry_run,
            exit_code=2,
        )
    articles = normalize_pub_dates(articles, default_date=today)
    if not use_sample_data:
        articles = recency_filter(articles, max_age_days=7)

    dedup_index = DedupIndex() if use_sample_data else prune_old_entries(
        load_dedup_index(dedup_path), today=today, retention_days=cfg.dedup.retention_days,
    )
    sheets_event_keys = read_event_keys_from_sheets(cfg.google_sheets_credentials, cfg.google_sheets_id)
    if sheets_event_keys is None:
        _handle_operational_issue(
            "Google Sheets unavailable or missing event_key column; aborting to avoid duplicate publication",
            dry_run=dry_run,
            exit_code=3,
        )
        sheets_event_keys = set()

    articles = deduplicate_articles(articles, dedup_index)
    articles = select_top_articles(
        articles,
        llm,
        top_n=cfg.pipeline.top_n,
        max_input_chars=cfg.llm.max_input_chars,
        max_per_domain=cfg.pipeline.max_per_domain,
        keywords=cfg.pipeline.keywords,
    )

    classifications = _map_ordered(
        lambda article: build_classified_article(article, classify_article(article, llm)),
        articles,
        max_workers=cfg.llm.concurrency,
    )

    # Event dedup before summarization: Sheets event_key remains authoritative,
    # while JSON event_fingerprint catches cross-source duplicates from this point on.
    json_event_keys = {entry.event_key for entry in dedup_index.entries if entry.event_key}
    json_event_fingerprints = {
        entry.event_fingerprint for entry in dedup_index.entries if entry.event_fingerprint
    }
    existing_event_keys = sheets_event_keys | json_event_keys
    classified_articles = dedup_classified_articles(
        classifications,
        existing_event_keys=existing_event_keys,
        existing_event_fingerprints=json_event_fingerprints,
    )

    def summarize_classified(item):
        article_for_summary = item.article
        if cfg.pipeline.fetch_body_for_selected and not use_sample_data:
            body = fetch_article_body(
                item.article.url,
                timeout=cfg.pipeline.body_fetch_timeout_seconds,
                max_chars=cfg.pipeline.body_fetch_max_chars,
            )
            if body:
                article_for_summary = replace(item.article, description=body)
        return item, summarize_article(article_for_summary, llm)

    summarized = _map_ordered(
        summarize_classified,
        classified_articles,
        max_workers=cfg.llm.concurrency,
    )
    nodes = [
        assemble_node(item.article, item.classification, summary)
        for item, summary in summarized
    ]
    for node in nodes:
        if not _useful_time_hint(node.event.time_hint):
            node.event.time_hint = ""

    if not use_sample_data and not nodes:
        _handle_operational_issue(
            "Pipeline health check failed: produced 0 briefing nodes",
            dry_run=dry_run,
            exit_code=2,
        )

    save_daily(nodes, today, data_dir=output_data_dir)

    if not use_sample_data:
        for node, item in zip(nodes, classified_articles):
            dedup_index.entries.append(
                DedupEntry(
                    event_key=node.event_key,
                    url_hash=url_hash(node.url),
                    date=today,
                    event_fingerprint=item.event_fingerprint,
                )
            )
        save_dedup_index(dedup_index, dedup_path)

    render_index(
        nodes=nodes,
        date=today,
        output_dir=output_dir,
        template_dir=template_dir,
        base_url=cfg.site.base_url,
    )

    all_dates = list_briefing_dates(data_dir=output_data_dir)
    all_daily_nodes = {date: load_daily(date, data_dir=output_data_dir) for date in all_dates}
    archive_entries = [
        {"date": date, "count": len(all_daily_nodes[date])}
        for date in all_dates
    ]
    render_archive(
        entries=archive_entries,
        output_dir=output_dir,
        template_dir=template_dir,
        base_url=cfg.site.base_url,
        all_daily_nodes=all_daily_nodes,
    )
    all_nodes_flat = [n for ns in all_daily_nodes.values() for n in ns]
    render_article_pages(
        nodes=all_nodes_flat,
        output_dir=output_dir,
        template_dir=template_dir,
        base_url=cfg.site.base_url,
    )
    copy_static(output_dir=output_dir, static_dir=static_dir)

    # Publish output/manifest.json for the briefing-hub aggregator.
    # Best-effort — never block the deploy if this misfires.
    try:
        from pipeline.render.manifest import write_manifest

        write_manifest(output_dir=output_dir)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Briefing-hub manifest write failed: %s", exc)

    if not dry_run and nodes and cfg.smtp_user and cfg.smtp_pass and cfg.recipients:
        send_briefing_email(
            html_body=render_email(nodes, today, template_dir=template_dir, web_url=cfg.email.web_url),
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
