from datetime import datetime, timedelta

from pipeline.sources.filters import keyword_filter, normalize_pub_dates, recency_filter
from pipeline.sources.rss import RawArticle


def _article(title: str, description: str = "") -> RawArticle:
    return RawArticle(
        title=title,
        url="https://example.com",
        source="Test",
        description=description,
        pub_date="2026-03-23",
    )


def test_keyword_filter_matches_title_and_description():
    articles = [
        _article("EU Loot Box Regulation"),
        _article("New Policy", description="FTC announces gaming probe"),
        _article("Cooking Recipes for Spring"),
    ]
    result = keyword_filter(articles, ["loot box", "FTC"])
    assert [article.title for article in result] == ["EU Loot Box Regulation", "New Policy"]


def test_keyword_filter_returns_all_without_keywords():
    articles = [_article("Anything")]
    assert keyword_filter(articles, []) == articles


def test_keyword_filter_enforces_word_boundaries():
    articles = [
        _article("This email was sent yesterday"),
        _article("The CEO said", description="again and again"),
        _article("New AI regulation proposed"),
    ]
    result = keyword_filter(articles, ["AI"])
    assert len(result) == 1
    assert result[0].title == "New AI regulation proposed"


def test_keyword_filter_case_insensitive():
    articles = [
        _article("Gaming LAWSUIT filed today"),
        _article("A lawsuit is pending"),
    ]
    result = keyword_filter(articles, ["lawsuit"])
    assert len(result) == 2


def test_keyword_filter_multi_word_keywords():
    articles = [
        _article("LOOT BOX regulations tightened"),
        _article("Loot box proposal"),
        _article("Loot and box separate"),
    ]
    result = keyword_filter(articles, ["loot box"])
    assert [article.title for article in result] == [
        "LOOT BOX regulations tightened",
        "Loot box proposal",
    ]


def test_normalize_pub_dates_fills_missing_and_invalid_dates():
    articles = [
        _article("Valid", "unchanged"),
        _article("Missing", "missing"),
        _article("Invalid", "invalid"),
    ]
    articles[0].pub_date = "2026-04-27"
    articles[1].pub_date = ""
    articles[2].pub_date = "April 27, 2026"

    result = normalize_pub_dates(articles, default_date="2026-04-27")

    assert [article.pub_date for article in result] == [
        "2026-04-27",
        "2026-04-27",
        "2026-04-27",
    ]


def test_recency_filter_drops_missing_invalid_and_old_dates():
    today = datetime.now().strftime("%Y-%m-%d")
    old = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    articles = [
        _article("Recent"),
        _article("Old"),
        _article("Missing"),
        _article("Invalid"),
    ]
    articles[0].pub_date = today
    articles[1].pub_date = old
    articles[2].pub_date = ""
    articles[3].pub_date = "not-a-date"

    result = recency_filter(articles, max_age_days=7)

    assert [article.title for article in result] == ["Recent"]
