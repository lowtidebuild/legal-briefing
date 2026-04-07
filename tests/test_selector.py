from unittest.mock import MagicMock

from pipeline.intelligence.selector import select_top_articles
from pipeline.sources.rss import RawArticle


def _article(title: str, idx: int = 0) -> RawArticle:
    return RawArticle(
        title=title,
        url=f"https://example.com/{idx}",
        source="Test",
        description=f"Description for {title}",
        pub_date="2026-04-01",
    )


def test_returns_all_when_within_top_n():
    articles = [_article("A", 0), _article("B", 1)]
    llm = MagicMock()
    result = select_top_articles(articles, llm, top_n=5)
    assert result == articles
    llm.generate_json.assert_not_called()


def test_selects_by_llm_indices():
    articles = [_article(f"Art{i}", i) for i in range(20)]
    llm = MagicMock()
    llm.generate_json.return_value = {"selected_indices": [0, 5, 10]}
    result = select_top_articles(articles, llm, top_n=3)
    assert len(result) == 3
    assert result[0].title == "Art0"
    assert result[1].title == "Art5"


def test_handles_out_of_range_indices():
    articles = [_article(f"Art{i}", i) for i in range(5)]
    llm = MagicMock()
    llm.generate_json.return_value = {"selected_indices": [0, 99, -1, 2]}
    result = select_top_articles(articles, llm, top_n=3)
    # LLM returned 2 valid indices, fill adds 1 more to reach top_n=3
    assert len(result) == 3
    assert result[0].title == "Art0"
    assert result[1].title == "Art2"


def test_falls_back_on_llm_failure():
    articles = [_article(f"Art{i}", i) for i in range(20)]
    llm = MagicMock()
    llm.generate_json.side_effect = RuntimeError("API down")
    result = select_top_articles(articles, llm, top_n=3)
    assert len(result) == 3
    assert result[0].title == "Art0"


def test_respects_max_input_chars():
    articles = [_article(f"Article with a long title number {i}", i) for i in range(100)]
    llm = MagicMock()
    llm.generate_json.return_value = {"selected_indices": [0, 1]}
    result = select_top_articles(articles, llm, top_n=5, max_input_chars=500)
    # LLM returned 2, fill adds 3 more to reach top_n=5
    assert len(result) == 5
    # Verify the prompt was truncated (not all 100 articles included)
    call_args = llm.generate_json.call_args[0][0]
    assert "[99]" not in call_args
