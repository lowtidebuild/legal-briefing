from unittest.mock import MagicMock

from pipeline.intelligence.selector import select_top_articles
from pipeline.sources.rss import RawArticle


def _article(title: str, idx: int = 0, url: str | None = None) -> RawArticle:
    return RawArticle(
        title=title,
        url=url or f"https://example.com/{idx}",
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


def test_prompt_removes_specific_law_firm_bias():
    articles = [_article(f"Art{i}", i) for i in range(5)]
    llm = MagicMock()
    llm.generate_json.return_value = {"selected_indices": [0]}

    select_top_articles(articles, llm, top_n=2)

    prompt = llm.generate_json.call_args[0][0]
    assert "Cooley" not in prompt
    assert "DLA Piper" not in prompt
    assert "Norton Rose" not in prompt


def test_enforces_domain_cap_with_alternative_sources():
    articles = [
        _article("A0", 0, "https://same.example/a0"),
        _article("A1", 1, "https://same.example/a1"),
        _article("A2", 2, "https://same.example/a2"),
        _article("A3", 3, "https://same.example/a3"),
        _article("B0", 4, "https://other.example/b0"),
        _article("B1", 5, "https://other.example/b1"),
        _article("C0", 6, "https://third.example/c0"),
    ]
    llm = MagicMock()
    llm.generate_json.return_value = {"selected_indices": [0, 1, 2, 3, 4]}

    result = select_top_articles(articles, llm, top_n=5, max_per_domain=2)

    domains = [article.url.split("/")[2] for article in result]
    assert len(result) == 5
    assert domains.count("same.example") == 2
    assert domains.count("other.example") == 2
    assert domains.count("third.example") == 1


def test_domain_cap_relaxes_when_no_alternatives_are_available():
    articles = [_article(f"Art{i}", i, f"https://same.example/{i}") for i in range(8)]
    llm = MagicMock()
    llm.generate_json.return_value = {"selected_indices": [0, 1, 2, 3]}

    result = select_top_articles(articles, llm, top_n=4, max_per_domain=2)

    assert len(result) == 4
    assert [article.title for article in result] == ["Art0", "Art1", "Art2", "Art3"]


def test_selector_ranks_keyword_matches_before_truncation():
    articles = [
        _article("General one", 0, "https://a.example/0"),
        _article("General two", 1, "https://b.example/1"),
        _article("FTC gaming enforcement", 2, "https://c.example/2"),
        _article("General three", 3, "https://d.example/3"),
    ]
    llm = MagicMock()
    llm.generate_json.return_value = {"selected_indices": [0]}

    result = select_top_articles(
        articles,
        llm,
        top_n=2,
        max_input_chars=120,
        keywords=["FTC", "enforcement"],
    )

    prompt = llm.generate_json.call_args[0][0]
    assert "[0] FTC gaming enforcement" in prompt
    assert result[0].title == "FTC gaming enforcement"
