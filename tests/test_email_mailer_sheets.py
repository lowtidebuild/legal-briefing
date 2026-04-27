import os
from unittest.mock import MagicMock, patch

from pipeline.admin.sheets import format_row, read_event_keys_from_sheets, sync_to_sheets
from pipeline.deliver.mailer import send_briefing_email
from pipeline.models import BriefingNode, EventType, Jurisdiction, LegalEvent, RegulatoryPhase
from pipeline.render.email import render_email


def _node(
    *,
    title: str = "Test Article",
    title_ko: str = "테스트 기사",
    url: str = "https://example.com",
    source: str = "TestFeed",
    pub_date: str = "2026-03-23",
    category: str = "IP",
    summary_ko: list[str] | None = None,
    time_hint: str = "",
) -> BriefingNode:
    return BriefingNode(
        title=title,
        title_ko=title_ko,
        url=url,
        source=source,
        pub_date=pub_date,
        category=category,
        summary_ko=summary_ko or ["요약 1", "요약 2", "요약 3"],
        event=LegalEvent(
            jurisdiction=Jurisdiction.US,
            event_type=EventType.LITIGATION,
            regulatory_phase=RegulatoryPhase.ENACTED,
            actors=["Nintendo"],
            object="patent",
            action="filed",
            game_mechanic=None,
            time_hint=time_hint,
        ),
        event_key="key1",
        is_primary=True,
    )


def _make_sample_nodes() -> list[BriefingNode]:
    return [
        _node(
            title="Sony acquires AI company",
            title_ko="소니, AI 기업 인수",
            category="MA_CORP_ANTITRUST",
            source="GamesIndustry.biz",
            pub_date="2026-04-07",
            summary_ko=["첫 번째 문장.", "두 번째 문장.", "세 번째 문장."],
        ),
        _node(
            title="Savvy leads M&A activity",
            title_ko="새비 게임즈, M&A 시장 주도",
            category="MA_CORP_ANTITRUST",
            source="PocketGamer.biz",
            pub_date="2026-04-07",
            summary_ko=["M&A 첫째.", "M&A 둘째.", "M&A 셋째."],
        ),
        _node(
            title="Nintendo patent ruling",
            title_ko="닌텐도 특허 출원 거절",
            category="IP",
            source="GamesIndustry.biz",
            pub_date="2026-04-02",
            summary_ko=["IP 첫째.", "IP 둘째.", "IP 셋째."],
        ),
        _node(
            title="Hogan Lovells AI checklist",
            title_ko="",
            category="PRIVACY_SECURITY",
            source="Hogan Lovells",
            pub_date="2026-04-05",
            summary_ko=["보안 첫째.", "보안 둘째.", "보안 셋째."],
        ),
    ]


def test_render_email_and_format_row():
    template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
    html = render_email(
        nodes=[_node()],
        date="2026-03-23",
        template_dir=template_dir,
        web_url="https://example.com/archive",
    )
    row = format_row(_node())
    assert "Game Legal Briefing" in html
    assert "게임산업 법무·규제 브리핑" in html
    assert "①" in html
    assert "#6b1010" in html
    assert "#f4efe6" in html
    assert "Noto Serif KR" in html or "Pretendard" in html
    assert "https://example.com/archive" in html
    assert row[0] == "2026-03-23"
    assert row[7] == ""


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


def test_format_row_includes_time_hint():
    row = format_row(_node(time_hint="June 2026"))
    assert row[7] == "June 2026"
    assert row[8] == "요약 1 | 요약 2 | 요약 3"


def test_read_event_keys_from_sheets_returns_none_on_configured_failure():
    with patch("pipeline.admin.sheets._get_worksheet", side_effect=RuntimeError("down")):
        assert read_event_keys_from_sheets(credentials_json="{}", spreadsheet_id="sheet-id") is None


def test_read_event_keys_from_sheets_unconfigured_returns_empty_set():
    assert read_event_keys_from_sheets(credentials_json=None, spreadsheet_id=None) == set()


def test_render_email_structure_and_breadcrumbs():
    template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")

    html = render_email(
        nodes=_make_sample_nodes(),
        date="2026-04-11",
        template_dir=template_dir,
        web_url="https://example.com/web",
    )

    expected_labels = ["지식재산권", "M&amp;A / 독점금지", "개인정보 / 보안"]
    assert sum(html.count(label) for label in expected_labels) == 3
    assert "IP 1" in html
    assert "M&amp;A 2" in html
    assert "개인정보 1" in html
    assert "①" in html and "②" in html and "③" in html
    assert "소니, AI 기업 인수" in html
    assert "새비 게임즈, M&amp;A 시장 주도" in html
    assert "닌텐도 특허 출원 거절" in html
    assert "Hogan Lovells AI checklist" in html
    assert 'href="https://example.com/web"' in html
    assert "소니, AI 기업 인수" in html
    assert "Hogan Lovells AI checklist" in html
