"""Game Legal Briefing CLI orchestrator."""
from __future__ import annotations

import argparse
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime
from typing import Callable, TypeVar

try:  # pragma: no cover - import availability depends on environment
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - graceful fallback
    def load_dotenv() -> None:
        return None

from pipeline.admin.sheets import read_event_keys_from_sheets
from pipeline.config import load_config
from pipeline.intelligence.classifier import classify_articles
from pipeline.intelligence.dedup import DedupEntry, DedupIndex, deduplicate_articles, url_hash
from pipeline.intelligence.event_dedup import build_classified_article, dedup_classified_articles
from pipeline.intelligence.selector import select_articles
from pipeline.intelligence.summarizer import summarize_articles
from pipeline.llm import create_provider
from pipeline.llm.rate_limit import RateLimitGate
from pipeline.quality import validate_briefing_quality
from pipeline.run_report import (
    RunReport,
    RunStatus,
    collect_llm_metrics,
    determine_run_status,
    llm_was_degraded,
    make_run_id,
    source_actions,
    summarize_sources,
    write_run_report,
)
from pipeline.run_manifest import create_run_manifest
from pipeline.render.email import render_email, write_email_preview
from pipeline.render.site import copy_static, render_archive, render_article_pages, render_index
from pipeline.sources.fetcher import fetch_article_body
from pipeline.sources.filters import keyword_filter, normalize_pub_dates, recency_filter
from pipeline.sources.rss import (
    SourceFetchResult,
    SourceStatus,
    fetch_all_feeds_with_report,
    sample_articles,
)
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
    delivery: str = "none",
) -> None:
    """Generate briefing artifacts without external delivery side effects."""
    if delivery != "none":
        raise ValueError("main.py only supports generation; use scripts/deliver_existing.py")
    load_dotenv()
    cfg = load_config(config_path)
    today = os.getenv("BRIEFING_DATE") or datetime.now().strftime("%Y-%m-%d")
    started_at = time.monotonic()
    run_id = make_run_id(today)
    source_results: list[SourceFetchResult] = []
    source_article_count = 0
    tier_a_total = 0
    tier_a_unhealthy = 0
    selector_completed = False
    selector_degraded = False
    quality_gate: dict[str, object] = {"status": "not_run", "issue_codes": []}
    counts = {
        "raw": 0,
        "keyword": 0,
        "recent": 0,
        "url_dedup": 0,
        "selector_evaluated": 0,
        "selected": 0,
        "event_dedup": 0,
        "published": 0,
    }
    stages = {
        "generate": "in_progress",
        "git": "not_run",
        "pages": "not_run",
        "email": "not_run",
        "sheets": "not_run",
    }

    output_data_dir = os.path.join(output_dir, "data", "daily")
    dedup_path = os.path.join(output_dir, "data", "dedup_index.json")
    rate_limit_gate = RateLimitGate()

    analysis_llm = create_provider(
        cfg.llm,
        google_api_key=None if use_sample_data else cfg.google_api_key,
        anthropic_api_key=None if use_sample_data else cfg.anthropic_api_key,
        groq_api_key=None if use_sample_data else cfg.groq_api_key,
        offline_fallback=use_sample_data or dry_run,
        offline_context="sample mode" if use_sample_data else "dry-run mode",
        rate_limit_gate=rate_limit_gate,
    )
    summary_llm = analysis_llm
    if cfg.llm.summary_model and (
        cfg.llm.summary_model != cfg.llm.model
        or cfg.llm.summary_reasoning_effort != cfg.llm.reasoning_effort
    ):
        summary_cfg = replace(
            cfg.llm,
            model=cfg.llm.summary_model,
            reasoning_effort=cfg.llm.summary_reasoning_effort,
        )
        summary_llm = create_provider(
            summary_cfg,
            google_api_key=None if use_sample_data else cfg.google_api_key,
            anthropic_api_key=None if use_sample_data else cfg.anthropic_api_key,
            groq_api_key=None if use_sample_data else cfg.groq_api_key,
            offline_fallback=use_sample_data or dry_run,
            offline_context="sample mode" if use_sample_data else "dry-run mode",
            rate_limit_gate=rate_limit_gate,
        )

    def emit_run_report(forced_status: RunStatus | None = None) -> str:
        llm_models, fallback_batches = collect_llm_metrics([analysis_llm, summary_llm])
        status = forced_status or determine_run_status(
            source_has_data=source_article_count > 0,
            selector_completed=selector_completed,
            published_count=counts["published"],
            tier_a_total=tier_a_total,
            tier_a_unhealthy=tier_a_unhealthy,
            llm_degraded=llm_was_degraded(llm_models, fallback_batches),
            selector_degraded=selector_degraded,
            quality_ok=quality_gate["status"] != "failed",
        )
        actions = source_actions(source_results)
        if quality_gate["status"] == "failed":
            actions.append("quality_gate: failed")
        report = RunReport(
            run_id=run_id,
            briefing_date=today,
            status=status,
            source_statuses=summarize_sources(source_results),
            counts=counts.copy(),
            llm_models=llm_models,
            fallback_batches=fallback_batches,
            quality_gate=quality_gate.copy(),
            stages=stages.copy(),
            duration_seconds=time.monotonic() - started_at,
            action_required=actions,
        )
        return write_run_report(report, output_dir=output_dir)

    if use_sample_data:
        articles = sample_articles()
        source_article_count = len(articles)
        source_results = [
            SourceFetchResult(
                source_name="sample_data",
                tier="sample",
                status=SourceStatus.OK,
                article_count=len(articles),
                articles=articles,
            )
        ]
    else:
        feed_report = fetch_all_feeds_with_report(
            tier_a=cfg.sources.tier_a,
            tier_b=cfg.sources.tier_b,
        )
        tier_a_total = feed_report.tier_a_total
        tier_a_unhealthy = feed_report.tier_a_empty
        source_results.extend(feed_report.source_results)
        if feed_report.tier_a_failure_rate >= 0.5:
            logger.warning(
                "Tier A feed health degraded: %s/%s sources returned no articles; "
                "continuing with available feeds",
                feed_report.tier_a_empty,
                feed_report.tier_a_total,
            )
        articles = feed_report.articles
        from pipeline.sources.tier_c import fetch_tier_c_with_report, write_sources_backlog

        write_sources_backlog(cfg.sources.tier_c)
        tier_c_results = fetch_tier_c_with_report(cfg.sources.tier_c)
        source_results.extend(tier_c_results)
        articles.extend(article for result in tier_c_results for article in result.articles)
        source_article_count = len(articles)
    counts["raw"] = source_article_count
    if not use_sample_data and source_article_count == 0:
        if not dry_run:
            stages["generate"] = "failed"
            emit_run_report(RunStatus.FAIL)
        _handle_operational_issue(
            "Pipeline health check failed: all configured sources returned 0 articles",
            dry_run=dry_run,
            exit_code=2,
        )
    game_signals = getattr(cfg.pipeline, "game_signals", [])
    legal_signals = getattr(cfg.pipeline, "legal_signals", [])
    candidate_signals = list(dict.fromkeys([*game_signals, *legal_signals]))
    if not candidate_signals:
        candidate_signals = cfg.pipeline.keywords
    articles = keyword_filter(articles, keywords=candidate_signals)
    counts["keyword"] = len(articles)
    if not use_sample_data:
        articles = recency_filter(articles, max_age_days=7)
    counts["recent"] = len(articles)
    articles = normalize_pub_dates(articles, default_date=today)

    dedup_index = DedupIndex() if use_sample_data else prune_old_entries(
        load_dedup_index(dedup_path), today=today, retention_days=cfg.dedup.retention_days,
    )
    sheets_event_keys = read_event_keys_from_sheets(cfg.google_sheets_credentials, cfg.google_sheets_id)
    if sheets_event_keys is None:
        if not dry_run:
            stages["generate"] = "failed"
            emit_run_report(RunStatus.FAIL)
        _handle_operational_issue(
            "Google Sheets unavailable or missing event_key column; aborting to avoid duplicate publication",
            dry_run=dry_run,
            exit_code=3,
        )
        sheets_event_keys = set()

    articles = deduplicate_articles(articles, dedup_index)
    counts["url_dedup"] = len(articles)
    selection_result = select_articles(
        articles,
        analysis_llm,
        top_n=cfg.pipeline.top_n,
        max_input_chars=cfg.llm.max_input_chars,
        max_per_domain=cfg.pipeline.max_per_domain,
        keywords=candidate_signals,
        game_signals=game_signals or None,
        legal_signals=legal_signals or None,
    )
    selector_completed = True
    selector_degraded = selection_result.degraded
    counts["selector_evaluated"] = selection_result.evaluated_count
    articles = selection_result.articles
    counts["selected"] = len(articles)

    classification_results = classify_articles(articles, analysis_llm)
    classifications = [
        build_classified_article(article, classification)
        for article, classification in zip(articles, classification_results)
    ]

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
    counts["event_dedup"] = len(classified_articles)

    def article_for_summary(item):
        article_for_summary = item.article
        if cfg.pipeline.fetch_body_for_selected and not use_sample_data:
            body = fetch_article_body(
                item.article.url,
                timeout=cfg.pipeline.body_fetch_timeout_seconds,
                max_chars=cfg.pipeline.body_fetch_max_chars,
            )
            if body:
                article_for_summary = replace(item.article, description=body)
        return article_for_summary

    summary_articles = _map_ordered(
        article_for_summary,
        classified_articles,
        max_workers=cfg.llm.concurrency,
    )
    summaries = summarize_articles(summary_articles, summary_llm)
    nodes = [
        assemble_node(item.article, item.classification, summary)
        for item, summary in zip(classified_articles, summaries)
    ]
    for node in nodes:
        if not _useful_time_hint(node.event.time_hint):
            node.event.time_hint = ""

    if not use_sample_data:
        quality_report = validate_briefing_quality(
            nodes,
            legal_hooks=[selection_result.legal_hooks.get(node.url, "") for node in nodes],
        )
        quality_gate = {
            "status": "passed" if quality_report.ok else "failed",
            "issue_codes": [issue.code for issue in quality_report.issues],
        }
        if not quality_report.ok:
            logger.error("Pipeline quality check failed: %s", quality_report.describe())
            stages["generate"] = "failed"
            emit_run_report(RunStatus.FAIL)
            raise SystemExit(4)
    else:
        quality_gate = {"status": "skipped_sample", "issue_codes": []}

    save_daily(nodes, today, data_dir=output_data_dir)
    counts["published"] = len(nodes)

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

    create_run_manifest(
        date=today,
        run_id=run_id,
        item_count=len(nodes),
        output_dir=output_dir,
    )

    if dry_run and nodes:
        email_html = render_email(
            nodes,
            today,
            template_dir=template_dir,
            web_url=cfg.email.web_url,
        )
        write_email_preview(email_html, output_dir=output_dir)

    if not nodes:
        logger.info("No articles to report, skipping email delivery")
        stages["email"] = "skipped_no_updates"
    else:
        stages["email"] = "skipped_generation_only"

    if not nodes:
        stages["sheets"] = "skipped_no_updates"
    else:
        stages["sheets"] = "skipped_generation_only"

    stages["generate"] = "completed"
    emit_run_report()
    logger.info("Pipeline complete with %d published nodes", len(nodes))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Game Legal Briefing site and outputs")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--output", default="output", help="Directory for generated output")
    parser.add_argument("--templates", default="templates", help="Template directory")
    parser.add_argument("--static", default="static", help="Static asset directory")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use the offline provider and write an email preview",
    )
    parser.add_argument(
        "--delivery",
        choices=["none"],
        default="none",
        help="Generation is side-effect free; delivery is a separate command",
    )
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
        delivery=args.delivery,
    )


if __name__ == "__main__":
    main()
