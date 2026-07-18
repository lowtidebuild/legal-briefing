from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pipeline.delivery import (
    DeliveryConflict,
    DeliveryError,
    PartialDeliveryRequiresApproval,
    deliver_existing,
    receipt_path,
)
from pipeline.models import BriefingNode, EventType, Jurisdiction, LegalEvent, RegulatoryPhase
from pipeline.run_manifest import create_run_manifest
from pipeline.store.daily import save_daily


DATE = "2026-07-20"


def _node(event_key: str = "us_ftc_game_privacy_2026") -> BriefingNode:
    return BriefingNode(
        title="FTC gaming privacy order",
        title_ko="FTC, 게임 개인정보 명령",
        url="https://example.com/ftc",
        source="Test Feed",
        pub_date=DATE,
        category="PRIVACY_SECURITY",
        summary_ko=["첫 문장입니다.", "둘째 문장입니다.", "셋째 문장입니다."],
        event=LegalEvent(
            jurisdiction=Jurisdiction.US,
            event_type=EventType.ENFORCEMENT,
            regulatory_phase=RegulatoryPhase.ENFORCED,
            actors=["FTC"],
            object="gaming privacy",
            action="issued an order",
            game_mechanic="data_collection",
            time_hint="",
        ),
        event_key=event_key,
        is_primary=True,
    )


def _config(*, email: bool = True, sheets: bool = True):
    return SimpleNamespace(
        email=SimpleNamespace(subject_prefix="[Test]", web_url="https://example.com"),
        smtp_user="sender@example.com" if email else None,
        smtp_pass="password" if email else None,
        recipients=["recipient@example.com"] if email else [],
        google_sheets_credentials="{}" if sheets else None,
        google_sheets_id="sheet-id" if sheets else None,
    )


def _prepare(tmp_path, nodes: list[BriefingNode] | None = None) -> None:
    nodes = [_node()] if nodes is None else nodes
    save_daily(nodes, DATE, data_dir=str(tmp_path / "data" / "daily"))
    create_run_manifest(
        date=DATE,
        run_id=f"briefing-{DATE}",
        item_count=len(nodes),
        output_dir=str(tmp_path),
    )


def test_completed_run_is_not_delivered_twice(tmp_path):
    _prepare(tmp_path)
    with (
        patch("pipeline.delivery.send_briefing_email") as email_mock,
        patch("pipeline.delivery.sync_to_sheets") as sheets_mock,
    ):
        first = deliver_existing(date=DATE, cfg=_config(), output_dir=str(tmp_path))
        second = deliver_existing(date=DATE, cfg=_config(), output_dir=str(tmp_path))

    assert first.already_completed is False
    assert second.already_completed is True
    email_mock.assert_called_once()
    sheets_mock.assert_called_once()


def test_same_run_id_with_different_hash_is_a_conflict(tmp_path):
    _prepare(tmp_path)
    with (
        patch("pipeline.delivery.send_briefing_email"),
        patch("pipeline.delivery.sync_to_sheets"),
    ):
        deliver_existing(date=DATE, cfg=_config(), output_dir=str(tmp_path))

    changed = _node("us_ftc_changed_2026")
    save_daily([changed], DATE, data_dir=str(tmp_path / "data" / "daily"))
    create_run_manifest(
        date=DATE,
        run_id=f"briefing-{DATE}",
        item_count=1,
        output_dir=str(tmp_path),
    )
    with pytest.raises(DeliveryConflict, match="different content hash"):
        deliver_existing(date=DATE, cfg=_config(), output_dir=str(tmp_path))


def test_sheets_failure_is_partial_and_resume_does_not_resend_email(tmp_path):
    _prepare(tmp_path)
    with (
        patch("pipeline.delivery.send_briefing_email") as first_email,
        patch("pipeline.delivery.sync_to_sheets", side_effect=RuntimeError("down")),
        pytest.raises(DeliveryError, match="Sheets"),
    ):
        deliver_existing(date=DATE, cfg=_config(), output_dir=str(tmp_path))
    first_email.assert_called_once()

    receipt = json.loads(open(receipt_path(str(tmp_path), DATE), encoding="utf-8").read())
    assert receipt["status"] == "partial"
    assert receipt["email"] == "completed"
    assert receipt["sheets"] == "failed"

    with pytest.raises(PartialDeliveryRequiresApproval):
        deliver_existing(date=DATE, cfg=_config(), output_dir=str(tmp_path))

    with (
        patch("pipeline.delivery.send_briefing_email") as resumed_email,
        patch("pipeline.delivery.sync_to_sheets") as resumed_sheets,
    ):
        outcome = deliver_existing(
            date=DATE,
            cfg=_config(),
            output_dir=str(tmp_path),
            force_delivery=True,
        )
    resumed_email.assert_not_called()
    resumed_sheets.assert_called_once()
    assert outcome.receipt["status"] == "completed"


def test_email_failure_blocks_sheets_and_is_not_automatically_retryable(tmp_path):
    _prepare(tmp_path)
    with (
        patch("pipeline.delivery.send_briefing_email", side_effect=RuntimeError("smtp")),
        patch("pipeline.delivery.sync_to_sheets") as sheets_mock,
        pytest.raises(DeliveryError, match="Email"),
    ):
        deliver_existing(date=DATE, cfg=_config(), output_dir=str(tmp_path))
    sheets_mock.assert_not_called()

    with pytest.raises(PartialDeliveryRequiresApproval, match="Ambiguous"):
        deliver_existing(
            date=DATE,
            cfg=_config(),
            output_dir=str(tmp_path),
            force_delivery=True,
        )


def test_no_updates_completes_without_external_calls(tmp_path):
    _prepare(tmp_path, nodes=[])
    with (
        patch("pipeline.delivery.send_briefing_email") as email_mock,
        patch("pipeline.delivery.sync_to_sheets") as sheets_mock,
    ):
        outcome = deliver_existing(date=DATE, cfg=_config(), output_dir=str(tmp_path))
    email_mock.assert_not_called()
    sheets_mock.assert_not_called()
    assert outcome.receipt["status"] == "completed"
