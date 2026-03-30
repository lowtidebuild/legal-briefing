from pipeline.sources.filters import keyword_filter
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

