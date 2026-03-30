import os
from unittest.mock import MagicMock, patch

from pipeline.admin.sheets import format_row, sync_to_sheets
from pipeline.deliver.mailer import send_briefing_email
from pipeline.models import BriefingNode, EventType, Jurisdiction, LegalEvent, RegulatoryPhase
from pipeline.render.email import render_email


def _node() -> BriefingNode:
    return BriefingNode(
        title="Test Article",
        url="https://example.com",
        source="TestFeed",
        pub_date="2026-03-23",
        category="IP",
        summary_ko=["요약 1", "요약 2"],
        event=LegalEvent(
            jurisdiction=Jurisdiction.US,
            event_type=EventType.LITIGATION,
            regulatory_phase=RegulatoryPhase.ENACTED,
            actors=["Nintendo"],
            object="patent",
            action="filed",
            game_mechanic=None,
            time_hint="",
        ),
        event_key="key1",
        is_primary=True,
    )


def test_render_email_and_format_row():
    template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
    html = render_email(nodes=[_node()], date="2026-03-23", template_dir=template_dir)
    row = format_row(_node())
    assert "Game Legal Briefing" in html
    assert row[0] == "2026-03-23"


def test_send_email_skips_empty_recipients():
    with patch("pipeline.deliver.mailer.smtplib.SMTP_SSL") as mock_smtp:
        send_briefing_email("<h1>Test</h1>", "Test", "sender@gmail.com", "password", [])
        mock_smtp.assert_not_called()


def test_send_email_uses_smtp_for_real_recipients():
    with patch("pipeline.deliver.mailer.smtplib.SMTP_SSL") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_briefing_email(
            "<h1>Test</h1>",
            "Test",
            "sender@gmail.com",
            "password",
            ["a@example.com"],
        )
        mock_smtp.send_message.assert_called_once()
        args, kwargs = mock_smtp.send_message.call_args
        assert args[0]["To"] == "sender@gmail.com"
        assert kwargs["to_addrs"] == ["a@example.com"]


def test_sync_to_sheets_appends_rows():
    sheet = MagicMock()
    with patch("pipeline.admin.sheets._get_worksheet", return_value=sheet):
        sync_to_sheets([_node()], credentials_json="{}", spreadsheet_id="test-id")
        sheet.append_rows.assert_called_once()
