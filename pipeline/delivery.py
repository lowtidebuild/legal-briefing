from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from pipeline.admin.sheets import sync_to_sheets
from pipeline.config import Config
from pipeline.deliver.mailer import send_briefing_email
from pipeline.render.email import render_email
from pipeline.run_manifest import RunManifest, verify_run_manifest
from pipeline.run_report import RunStatus, update_run_report
from pipeline.store.daily import load_daily


class DeliveryError(RuntimeError):
    pass


class DeliveryConflict(DeliveryError):
    pass


class PartialDeliveryRequiresApproval(DeliveryError):
    pass


@dataclass(frozen=True)
class DeliveryOutcome:
    receipt: dict[str, object]
    already_completed: bool


def receipt_path(output_dir: str, date: str) -> str:
    return os.path.join(output_dir, "data", "delivery_receipts", f"{date}.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_receipt(path: str, receipt: dict[str, object]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _load_receipt(path: str) -> dict[str, object] | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise DeliveryError("Delivery receipt is unreadable") from exc
    if payload.get("schema_version") != 1:
        raise DeliveryError("Unsupported delivery receipt schema")
    return payload


def _new_receipt(manifest: RunManifest, cfg: Config) -> dict[str, object]:
    if manifest.item_count == 0:
        email_status = "skipped_no_updates"
        sheets_status = "skipped_no_updates"
    else:
        email_status = (
            "pending"
            if cfg.smtp_user and cfg.smtp_pass and cfg.recipients
            else "not_configured"
        )
        sheets_status = (
            "pending"
            if cfg.google_sheets_credentials and cfg.google_sheets_id
            else "not_configured"
        )
    return {
        "schema_version": 1,
        "run_id": manifest.run_id,
        "briefing_date": manifest.briefing_date,
        "content_sha256": manifest.content_sha256,
        "status": "in_progress",
        "pages": "completed",
        "email": email_status,
        "sheets": sheets_status,
        "completed_at": None,
    }


def _assert_receipt_matches(receipt: dict[str, object], manifest: RunManifest) -> None:
    if receipt.get("run_id") != manifest.run_id:
        raise DeliveryConflict("Existing receipt belongs to a different run ID")
    if receipt.get("content_sha256") != manifest.content_sha256:
        raise DeliveryConflict("Same run ID has a different content hash")


def _is_terminal_stage(status: object) -> bool:
    return status in {"completed", "not_configured", "skipped_no_updates"}


def _finish_if_complete(receipt: dict[str, object]) -> bool:
    if _is_terminal_stage(receipt.get("email")) and _is_terminal_stage(receipt.get("sheets")):
        receipt["status"] = "completed"
        receipt["completed_at"] = _now()
        return True
    return False


def render_delivery_summary(receipt: dict[str, object]) -> str:
    return (
        f"## Delivery — {receipt['status']}\n\n"
        "| Stage | Status |\n"
        "|---|---|\n"
        f"| Pages | {receipt['pages']} |\n"
        f"| Email | {receipt['email']} |\n"
        f"| Sheets | {receipt['sheets']} |\n\n"
    )


def _append_summary(receipt: dict[str, object], step_summary_path: str | None) -> None:
    path = step_summary_path or os.getenv("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(render_delivery_summary(receipt))


def _sync_run_report(
    receipt: dict[str, object],
    output_dir: str,
    *,
    failed: bool = False,
) -> None:
    update_run_report(
        output_dir=output_dir,
        date=str(receipt["briefing_date"]),
        stage_updates={
            "pages": str(receipt["pages"]),
            "email": str(receipt["email"]),
            "sheets": str(receipt["sheets"]),
        },
        status=RunStatus.FAIL if failed else None,
        action="delivery: partial" if failed else None,
    )


def deliver_existing(
    *,
    date: str,
    cfg: Config,
    output_dir: str = "output",
    template_dir: str = "templates",
    expected_run_id: str | None = None,
    force_delivery: bool = False,
    step_summary_path: str | None = None,
) -> DeliveryOutcome:
    """Deliver an immutable generated run after its Pages deployment succeeds."""
    manifest = verify_run_manifest(
        output_dir=output_dir,
        date=date,
        expected_run_id=expected_run_id,
    )
    path = receipt_path(output_dir, date)
    receipt = _load_receipt(path)
    if receipt is not None:
        _assert_receipt_matches(receipt, manifest)
        if receipt.get("status") == "completed":
            _sync_run_report(receipt, output_dir)
            _append_summary(receipt, step_summary_path)
            return DeliveryOutcome(receipt=receipt, already_completed=True)
        if "ambiguous" in {receipt.get("email"), receipt.get("sheets")}:
            raise PartialDeliveryRequiresApproval(
                "Ambiguous delivery cannot be retried automatically"
            )
        if not force_delivery:
            raise PartialDeliveryRequiresApproval(
                "Partial delivery requires --force-delivery to resume pending stages"
            )
    else:
        receipt = _new_receipt(manifest, cfg)
        _write_receipt(path, receipt)

    nodes = load_daily(date, data_dir=os.path.join(output_dir, "data", "daily"))
    if len(nodes) != manifest.item_count:
        raise DeliveryConflict("Loaded nodes do not match manifest item count")

    if receipt["email"] == "pending":
        email_html = render_email(
            nodes,
            date,
            template_dir=template_dir,
            web_url=cfg.email.web_url,
        )
        try:
            send_briefing_email(
                html_body=email_html,
                subject=f"{cfg.email.subject_prefix} {date}",
                smtp_user=cfg.smtp_user or "",
                smtp_pass=cfg.smtp_pass or "",
                recipients=cfg.recipients,
            )
        except Exception as exc:
            receipt["email"] = "ambiguous"
            receipt["status"] = "partial"
            _write_receipt(path, receipt)
            _sync_run_report(receipt, output_dir, failed=True)
            _append_summary(receipt, step_summary_path)
            raise DeliveryError("Email delivery failed with an ambiguous result") from exc
        receipt["email"] = "completed"
        _write_receipt(path, receipt)

    if receipt["sheets"] in {"pending", "failed"}:
        try:
            sync_to_sheets(
                nodes,
                cfg.google_sheets_credentials,
                cfg.google_sheets_id,
            )
        except Exception as exc:
            receipt["sheets"] = "failed"
            receipt["status"] = "partial"
            _write_receipt(path, receipt)
            _sync_run_report(receipt, output_dir, failed=True)
            _append_summary(receipt, step_summary_path)
            raise DeliveryError("Google Sheets delivery failed") from exc
        receipt["sheets"] = "completed"

    _finish_if_complete(receipt)
    _write_receipt(path, receipt)
    _sync_run_report(receipt, output_dir)
    _append_summary(receipt, step_summary_path)
    return DeliveryOutcome(receipt=receipt, already_completed=False)
