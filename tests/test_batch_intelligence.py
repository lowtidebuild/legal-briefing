import json
from unittest.mock import MagicMock

import pytest

from pipeline.intelligence.batch import BatchValidationError
from pipeline.intelligence.classifier import classify_articles
from pipeline.intelligence.dedup import url_hash
from pipeline.intelligence.selector import select_top_articles
from pipeline.intelligence.summarizer import summarize_articles
from pipeline.llm.base import LLMProvider
from pipeline.llm.fallback import FallbackProvider
from pipeline.sources.rss import RawArticle


def _articles(count: int) -> list[RawArticle]:
    return [
        RawArticle(
            title=f"FTC gaming policy {index}",
            url=f"https://example.com/{index}",
            source="Test Feed",
            description="FTC policy update for gaming platforms",
            pub_date="2026-07-15",
        )
        for index in range(count)
    ]


def _prompt_items(prompt: str) -> list[dict]:
    return json.loads(prompt.split("Items JSON:\n", 1)[1].split("\n\n", 1)[0])


def _classification_payload(item: dict) -> dict:
    return {
        "item_id": item["item_id"],
        "category": "PRIVACY_SECURITY",
        "jurisdiction": "US",
        "event_type": "policy",
        "regulatory_phase": "proposed",
        "actors": ["FTC"],
        "object": item["title"],
        "action": "updated guidance",
        "game_mechanic": "none",
        "time_hint": "",
        "event_key": f"us_ftc_policy_{item['item_id']}",
    }


def _summary_payload(item: dict) -> dict:
    return {
        "item_id": item["item_id"],
        "title_ko": f"요약 {item['title']}",
        "summary_ko": ["첫째", "둘째", "셋째"],
    }


def test_classification_batch_restores_input_order():
    articles = _articles(3)
    llm = MagicMock(spec=LLMProvider)
    llm.generate_json_schema.side_effect = lambda prompt, schema, system=None: {
        "results": [_classification_payload(item) for item in reversed(_prompt_items(prompt))]
    }

    results = classify_articles(articles, llm)

    assert [result.event.object for result in results] == [article.title for article in articles]
    assert llm.generate_json_schema.call_count == 1


def test_classification_batch_recovers_only_missing_items_with_fallback():
    articles = _articles(3)
    primary = MagicMock(spec=LLMProvider)
    secondary = MagicMock(spec=LLMProvider)
    primary.generate_json_schema.side_effect = lambda prompt, schema, system=None: {
        "results": [_classification_payload(_prompt_items(prompt)[0])]
    }
    secondary.generate_json_schema.side_effect = lambda prompt, schema, system=None: {
        "results": [_classification_payload(item) for item in _prompt_items(prompt)]
    }
    llm = FallbackProvider(primary, secondary)

    results = classify_articles(articles, llm)

    assert len(results) == 3
    recovered_items = _prompt_items(secondary.generate_json_schema.call_args.args[0])
    assert [item["item_id"] for item in recovered_items] == [
        url_hash(article.url) for article in articles[1:]
    ]
    assert llm.fallback_calls == 1


@pytest.mark.parametrize("mode", ["unknown", "duplicate"])
def test_classification_batch_rejects_unmatchable_ids(mode):
    articles = _articles(2)
    llm = MagicMock(spec=LLMProvider)

    def response(prompt, schema, system=None):
        items = _prompt_items(prompt)
        results = [_classification_payload(item) for item in items]
        if mode == "unknown":
            results[0]["item_id"] = "unknown"
        else:
            results[1]["item_id"] = results[0]["item_id"]
        return {"results": results}

    llm.generate_json_schema.side_effect = response

    with pytest.raises(BatchValidationError):
        classify_articles(articles, llm)


def test_summarizer_uses_two_batches_when_batch_size_is_five():
    articles = _articles(10)
    llm = MagicMock(spec=LLMProvider)
    llm.generate_json_schema.side_effect = lambda prompt, schema, system=None: {
        "results": [_summary_payload(item) for item in _prompt_items(prompt)]
    }

    results = summarize_articles(articles, llm, batch_size=5)

    assert len(results) == 10
    assert llm.generate_json_schema.call_count == 2


def test_ten_selected_articles_use_three_llm_calls():
    articles = _articles(11)

    class CountingLLM:
        def __init__(self):
            self.calls = 0

        def generate_json_schema(self, prompt, schema, system=None):
            self.calls += 1
            items = _prompt_items(prompt)
            if "selected" in schema["properties"]:
                return {
                    "selected": [
                        {
                            "item_id": item["item_id"],
                            "is_legally_relevant": True,
                            "legal_hook": "official_guidance",
                        }
                        for item in items[:10]
                    ]
                }
            properties = schema["properties"]["results"]["items"]["properties"]
            builder = _classification_payload if "category" in properties else _summary_payload
            return {"results": [builder(item) for item in items]}

    llm = CountingLLM()
    selected = select_top_articles(articles, llm, top_n=10, max_per_domain=10)
    classify_articles(selected, llm)
    summarize_articles(selected, llm)

    assert len(selected) == 10
    assert llm.calls == 3
