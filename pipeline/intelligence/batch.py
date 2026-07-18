from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from pipeline.llm.base import LLMProvider
from pipeline.llm.fallback import FallbackProvider

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")


class BatchValidationError(ValueError):
    """Raised when a structured batch response cannot be safely matched to inputs."""


def _validate_batch_payload(
    payload: dict | list,
    expected_ids: list[str],
    parse_item: Callable[[dict], R],
) -> tuple[dict[str, R], list[str]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise BatchValidationError("Batch response must contain a results array")

    expected = set(expected_ids)
    parsed: dict[str, R] = {}
    for item in payload["results"]:
        if not isinstance(item, dict):
            raise BatchValidationError("Batch result must be an object")
        item_id = item.get("item_id")
        if not isinstance(item_id, str) or item_id not in expected:
            raise BatchValidationError("Batch response contained an unknown item_id")
        if item_id in parsed:
            raise BatchValidationError("Batch response contained a duplicate item_id")
        parsed[item_id] = parse_item(item)
    return parsed, [item_id for item_id in expected_ids if item_id not in parsed]


def run_validated_batch(
    items: list[T],
    llm: LLMProvider,
    item_id: Callable[[T], str],
    build_prompt: Callable[[list[T]], str],
    schema: dict,
    parse_item: Callable[[T, dict], R],
    system: str | None = None,
) -> list[R]:
    """Run one ID-addressed batch, using fallback only for failed or missing items."""
    expected_ids = [item_id(item) for item in items]
    if len(expected_ids) != len(set(expected_ids)):
        raise BatchValidationError("Batch input contained duplicate item_id values")
    by_id = dict(zip(expected_ids, items))

    wrapper = llm if isinstance(llm, FallbackProvider) else None
    primary = wrapper.primary if wrapper else llm
    secondary = wrapper.secondary if wrapper else None

    def call(provider: LLMProvider, subset_ids: list[str]) -> tuple[dict[str, R], list[str]]:
        subset = [by_id[value] for value in subset_ids]
        payload = provider.generate_json_schema(build_prompt(subset), schema, system=system)
        return _validate_batch_payload(
            payload,
            subset_ids,
            lambda raw: parse_item(by_id[raw["item_id"]], raw),
        )

    try:
        results, missing = call(primary, expected_ids)
    except Exception as exc:
        if secondary is None:
            raise
        logger.warning("Primary batch failed; retrying the batch with fallback: %s", exc)
        wrapper.record_fallback()
        results, missing = call(secondary, expected_ids)
        if missing:
            raise BatchValidationError("Fallback batch omitted required item_id values")
        return [results[value] for value in expected_ids]

    if missing:
        if secondary is None:
            raise BatchValidationError("Primary batch omitted required item_id values")
        logger.warning("Primary batch omitted %d item(s); recovering only missing items", len(missing))
        wrapper.record_fallback()
        recovered, still_missing = call(secondary, missing)
        if still_missing:
            raise BatchValidationError("Fallback batch omitted required item_id values")
        results.update(recovered)

    return [results[value] for value in expected_ids]
