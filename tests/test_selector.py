import json
from unittest.mock import MagicMock

import pytest

from pipeline.intelligence.dedup import url_hash
from pipeline.intelligence.selector import select_articles, select_top_articles
from pipeline.sources.rss import RawArticle


def _article(
    title: str,
    idx: int = 0,
    url: str | None = None,
    description: str | None = None,
) -> RawArticle:
    return RawArticle(
        title=title,
        url=url or f"https://example.com/{idx}",
        source="Test",
        description=description or f"Description for {title}",
        pub_date="2026-04-01",
    )


def _selected(articles: list[RawArticle], count: int, hook: str = "regulation") -> dict:
    return {
        "selected": [
            {
                "item_id": url_hash(article.url),
                "is_legally_relevant": True,
                "legal_hook": hook,
            }
            for article in articles[:count]
        ]
    }


def test_selector_runs_even_when_candidates_are_below_top_n():
    articles = [_article("Game privacy regulation", 0), _article("Game labor ruling", 1)]
    llm = MagicMock()
    llm.generate_json_schema.return_value = _selected(articles, 1)

    result = select_top_articles(articles, llm, top_n=5)

    assert result == articles[:1]
    llm.generate_json_schema.assert_called_once()


@pytest.mark.parametrize("selected_count", [0, 3, 7, 10])
def test_selector_returns_zero_to_top_n_without_backfill(selected_count):
    articles = [_article(f"Game regulation {index}", index) for index in range(10)]
    llm = MagicMock()
    llm.generate_json_schema.return_value = _selected(articles, selected_count)

    result = select_articles(articles, llm, top_n=10, max_per_domain=10)

    assert len(result.articles) == selected_count
    assert len(result.legal_hooks) == selected_count
    assert result.degraded is False


def test_selector_domain_cap_drops_excess_without_backfill_or_relaxation():
    articles = [
        _article("A0 game regulation", 0, "https://same.example/a0"),
        _article("A1 game regulation", 1, "https://same.example/a1"),
        _article("A2 game regulation", 2, "https://same.example/a2"),
        _article("B0 game regulation", 3, "https://other.example/b0"),
    ]
    llm = MagicMock()
    llm.generate_json_schema.return_value = _selected(articles, 4)

    result = select_top_articles(articles, llm, top_n=4, max_per_domain=2)

    assert [article.title for article in result] == [
        "A0 game regulation",
        "A1 game regulation",
        "B0 game regulation",
    ]


def test_selector_failure_excludes_ai_only_and_keeps_game_ai_ip_dispute():
    articles = [
        _article(
            "Roblox lets users make games with AI on mobile",
            0,
            description="New creation tools improve mobile production workflows.",
        ),
        _article(
            "Game studio faces AI copyright lawsuit",
            1,
            description="A court will hear copyright infringement claims over generated game art.",
        ),
    ]
    llm = MagicMock()
    llm.generate_json_schema.side_effect = RuntimeError("API down")

    result = select_articles(articles, llm, top_n=10)

    assert [article.title for article in result.articles] == [
        "Game studio faces AI copyright lawsuit"
    ]
    assert result.legal_hooks[result.articles[0].url] == "ip_dispute"
    assert result.degraded is True


def test_selector_empty_response_is_valid_no_updates_not_fallback():
    articles = [_article("Roblox AI creation tools", 0)]
    llm = MagicMock()
    llm.generate_json_schema.return_value = {"selected": []}

    result = select_articles(articles, llm)

    assert result.articles == []
    assert result.degraded is False
    llm.generate_json_schema.assert_called_once()


def test_selector_rejects_unknown_id_and_uses_strict_fallback():
    articles = [
        _article(
            "FTC gaming privacy enforcement",
            0,
            description="FTC enforcement action concerns player privacy in a game.",
        ),
        _article("Generic AI market forecast", 1),
    ]
    llm = MagicMock()
    llm.generate_json_schema.return_value = {
        "selected": [
            {
                "item_id": "unknown",
                "is_legally_relevant": True,
                "legal_hook": "enforcement",
            }
        ]
    }

    result = select_articles(articles, llm)

    assert [article.title for article in result.articles] == ["FTC gaming privacy enforcement"]
    assert result.degraded is True


def test_selector_respects_max_input_chars_and_ranks_signals_first():
    articles = [
        _article("General update", 0, "https://a.example/0"),
        _article("Another general update", 1, "https://b.example/1"),
        _article("FTC gaming enforcement", 2, "https://c.example/2"),
        _article("General three", 3, "https://d.example/3"),
    ]
    llm = MagicMock()

    def response(prompt, schema, system=None):
        items = json.loads(prompt.split("Items JSON:\n", 1)[1].split("\n\n", 1)[0])
        return {
            "selected": [
                {
                    "item_id": items[0]["item_id"],
                    "is_legally_relevant": True,
                    "legal_hook": "enforcement",
                }
            ]
        }

    llm.generate_json_schema.side_effect = response

    result = select_top_articles(
        articles,
        llm,
        top_n=2,
        max_input_chars=180,
        keywords=["FTC", "enforcement", "gaming"],
    )

    prompt = llm.generate_json_schema.call_args_list[0].args[0]
    assert "FTC gaming enforcement" in prompt
    assert result[0].title == "FTC gaming enforcement"


def test_selector_prioritizes_legal_nexus_before_many_broad_matches():
    broad = [
        _article(
            f"Gaming product update {index}",
            index,
            f"https://broad-{index}.example/story",
            description="A game studio announced a new product feature.",
        )
        for index in range(30)
    ]
    legal = _article(
        "FTC brings gaming privacy enforcement action",
        99,
        "https://legal.example/privacy",
        description="The regulator alleges a game violated children's privacy law.",
    )
    llm = MagicMock()

    def response(prompt, schema, system=None):
        items = json.loads(prompt.split("Items JSON:\n", 1)[1].split("\n\n", 1)[0])
        assert items[0]["title"] == legal.title
        return {
            "selected": [
                {
                    "item_id": items[0]["item_id"],
                    "is_legally_relevant": True,
                    "legal_hook": "enforcement",
                }
            ]
        }

    llm.generate_json_schema.side_effect = response

    result = select_articles(
        [*broad, legal],
        llm,
        top_n=1,
        max_input_chars=350,
    )

    assert result.articles == [legal]
    assert result.candidate_count == 31
    assert 0 < result.evaluated_count < result.candidate_count


def test_selector_runs_second_validation_pass_when_truncated_and_underfilled():
    articles = [
        _article(
            f"Game privacy enforcement {index}",
            index,
            f"https://source-{index}.example/story",
        )
        for index in range(12)
    ]
    llm = MagicMock()

    def response(prompt, schema, system=None):
        items = json.loads(prompt.split("Items JSON:\n", 1)[1].split("\n\n", 1)[0])
        return {
            "selected": [
                {
                    "item_id": items[0]["item_id"],
                    "is_legally_relevant": True,
                    "legal_hook": "enforcement",
                }
            ]
        }

    llm.generate_json_schema.side_effect = response

    result = select_articles(
        articles,
        llm,
        top_n=3,
        max_input_chars=400,
        max_per_domain=3,
    )

    assert len(result.articles) == 2
    assert result.articles[0].url != result.articles[1].url
    assert llm.generate_json_schema.call_count == 2
    assert result.evaluated_count > 1
