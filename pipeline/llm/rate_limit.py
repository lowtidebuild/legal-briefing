from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable


class ModelCircuitOpen(RuntimeError):
    """Raised when a model has exhausted its safe retry budget for this run."""


@dataclass
class RateLimitGate:
    """Share per-model quota state across provider instances in one pipeline run."""

    blocked_until_by_model: dict[str, float] = field(default_factory=dict)
    disabled_models: set[str] = field(default_factory=set)
    rate_limit_counts: dict[str, int] = field(default_factory=dict)
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep

    def before_call(self, model: str) -> None:
        if model in self.disabled_models:
            raise ModelCircuitOpen(f"Model circuit is open: {model}")
        delay = self.blocked_until_by_model.get(model, 0.0) - self.clock()
        if delay > 0:
            self.sleep(delay)

    def register_rate_limit(self, model: str, retry_delay_seconds: float | None) -> bool:
        """Return whether one delayed retry is allowed for this model."""
        count = self.rate_limit_counts.get(model, 0) + 1
        self.rate_limit_counts[model] = count
        if count > 1 or retry_delay_seconds is None or retry_delay_seconds > 60:
            self.disabled_models.add(model)
            return False
        self.blocked_until_by_model[model] = self.clock() + max(0.0, retry_delay_seconds)
        return True


def is_rate_limit_error(exc: Exception) -> bool:
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    text = str(exc).lower()
    return code == 429 or "429" in text or "resource_exhausted" in text


def retry_delay_from_error(exc: Exception) -> float | None:
    for attr in ("retry_delay", "retry_after"):
        value = getattr(exc, attr, None)
        if isinstance(value, (int, float)):
            return float(value)

    text = str(exc)
    patterns = (
        r"retry(?:Delay| delay)?[^0-9]*(\d+(?:\.\d+)?)s",
        r"retry in\s+(\d+(?:\.\d+)?)s",
        r"retry-after[^0-9]*(\d+(?:\.\d+)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def is_transient_error(exc: Exception) -> bool:
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if code in {500, 502, 503, 504}:
        return True
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    return any(token in name or token in text for token in ("timeout", "connection", "temporarily unavailable"))
