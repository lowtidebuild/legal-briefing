from __future__ import annotations

import logging
from pathlib import Path

from pipeline.config import SourceEntry
from pipeline.sources import tier_c


def _fixture(name: str) -> str:
    return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")


def test_parse_korean_date_iso_format():
    assert tier_c._parse_korean_date("2026-04-11") == "2026-04-11"


def test_parse_korean_date_dot_format():
    assert tier_c._parse_korean_date("2026.04.11.") == "2026-04-11"


def test_parse_korean_date_korean_format():
    assert tier_c._parse_korean_date("2026년 04월 11일") == "2026-04-11"


def test_parse_korean_date_short_format_returns_empty():
    assert tier_c._parse_korean_date("4.11") == ""


def test_parse_korean_date_invalid():
    assert tier_c._parse_korean_date("invalid") == ""


def test_fetch_tier_c_skips_unknown_source(caplog):
    caplog.set_level(logging.INFO)
    result = tier_c.fetch_tier_c([SourceEntry(name="Unknown", url="https://example.com")])
    assert result == []
    assert "Tier C scraper not implemented for Unknown - skipping" in caplog.text


def test_write_sources_backlog(tmp_path):
    path = tmp_path / "sources-backlog.md"
    tier_c.write_sources_backlog(
        [
            SourceEntry(name="문화체육관광부", url="https://implemented.example"),
            SourceEntry(name="Unknown", url="https://unknown.example"),
        ],
        path=str(path),
    )
    content = path.read_text(encoding="utf-8")
    assert "Unknown" in content
    assert "문화체육관광부" not in content


def test_fetch_tier_c_handles_scraper_exception(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    def explode(source: SourceEntry):
        raise RuntimeError("boom")

    monkeypatch.setitem(tier_c.SCRAPER_REGISTRY, "문화체육관광부", explode)
    result = tier_c.fetch_tier_c(
        [SourceEntry(name="문화체육관광부", url="https://www.mcst.go.kr/kor/s_notice/press/pressList.jsp")]
    )
    assert result == []
    assert "Tier C scrape failed for 문화체육관광부: boom" in caplog.text


def test_scrape_mcst_parses_fixture(monkeypatch):
    monkeypatch.setattr(tier_c, "_fetch_html", lambda source: _fixture("mcst_sample.html"))
    source = SourceEntry(name="문화체육관광부", url="https://www.mcst.go.kr/kor/s_notice/press/pressList.jsp")

    articles = tier_c.scrape_mcst(source)

    assert [article.title for article in articles] == [
        "문체부 보도자료 첫 번째",
        "문체부 보도자료 두 번째",
    ]
    assert [article.pub_date for article in articles] == ["2026-04-10", "2026-04-09"]
    assert articles[0].url == "https://www.mcst.go.kr/kor/s_notice/press/pressView.jsp?pSeq=22336"


def test_scrape_grac_parses_fixture(monkeypatch):
    monkeypatch.setattr(tier_c, "_fetch_html", lambda source: _fixture("grac_sample.html"))
    source = SourceEntry(
        name="게임물관리위원회",
        url="https://www.grac.or.kr/board/Inform.aspx?searchtype=001&type=list",
    )

    articles = tier_c.scrape_grac(source)

    assert [article.title for article in articles] == [
        "자체등급분류사업자 지정 공고",
        "게임산업법 시행령 별표2 제8호 적용대상 게임물 별지 서식 안내",
    ]
    assert [article.pub_date for article in articles] == ["2026-04-10", "2026-02-06"]
    assert articles[0].url == "https://www.grac.or.kr/board/Inform.aspx?searchtype=004&type=view&bno=892&searchtext="


def test_scrape_kftc_parses_fixture(monkeypatch):
    monkeypatch.setattr(tier_c, "_fetch_html", lambda source: _fixture("kftc_sample.html"))
    source = SourceEntry(
        name="공정거래위원회",
        url="https://www.ftc.go.kr/www/selectBbsNttList.do?bordCd=3&key=12&searchCtgry=01,02",
    )

    articles = tier_c.scrape_kftc(source)

    assert [article.title for article in articles] == [
        "공정거래위원장, 뿌리업계 현장방문 및 간담회 개최",
        "㈜대광테크의 불공정하도급거래행위 제재",
    ]
    assert [article.pub_date for article in articles] == ["2026-04-09", "2026-04-09"]
    assert articles[0].url == "https://www.ftc.go.kr/www/selectBbsNttView.do?nttSn=47324"
