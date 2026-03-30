from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml


@dataclass
class LLMConfig:
    provider: str = "gemini"
    model: str = "gemini-3.1-flash-lite"
    max_retries: int = 2
    request_timeout_seconds: int = 30
    max_input_chars: int = 8000


@dataclass
class SourceEntry:
    name: str
    url: str


@dataclass
class SourcesConfig:
    tier_a: list[SourceEntry] = field(default_factory=list)
    tier_b: list[SourceEntry] = field(default_factory=list)


@dataclass
class PipelineConfig:
    top_n: int = 10
    categories: list[str] = field(default_factory=lambda: ["ETC"])
    keywords: list[str] = field(default_factory=list)


@dataclass
class DedupConfig:
    retention_days: int = 30


@dataclass
class SiteConfig:
    base_url: str = "/game-legal-briefing"


@dataclass
class EmailConfig:
    subject_prefix: str = "[Game Legal Briefing]"


@dataclass
class Config:
    llm: LLMConfig
    sources: SourcesConfig
    pipeline: PipelineConfig
    dedup: DedupConfig
    site: SiteConfig
    email: EmailConfig

    @property
    def google_api_key(self) -> str | None:
        return os.environ.get("GOOGLE_API_KEY")

    @property
    def anthropic_api_key(self) -> str | None:
        return os.environ.get("ANTHROPIC_API_KEY")

    @property
    def smtp_user(self) -> str | None:
        return os.environ.get("SMTP_USER")

    @property
    def smtp_pass(self) -> str | None:
        return os.environ.get("SMTP_PASS")

    @property
    def recipients(self) -> list[str]:
        raw = os.environ.get("RECIPIENTS", "")
        return [recipient.strip() for recipient in raw.split(",") if recipient.strip()]

    @property
    def google_sheets_credentials(self) -> str | None:
        return os.environ.get("GOOGLE_SHEETS_CREDENTIALS")

    @property
    def google_sheets_id(self) -> str | None:
        return os.environ.get("GOOGLE_SHEETS_ID")


def _load_sources(raw_sources: dict) -> SourcesConfig:
    return SourcesConfig(
        tier_a=[
            SourceEntry(name=entry["name"], url=entry["url"])
            for entry in raw_sources.get("tier_a", [])
        ],
        tier_b=[
            SourceEntry(name=entry["name"], url=entry["url"])
            for entry in raw_sources.get("tier_b", [])
        ],
    )


def load_config(path: str) -> Config:
    """Load the YAML configuration file with sane defaults."""
    with open(path, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    llm_raw = raw.get("llm", {})
    pipeline_raw = raw.get("pipeline", {})
    dedup_raw = raw.get("dedup", {})
    site_raw = raw.get("site", {})
    email_raw = raw.get("email", {})

    return Config(
        llm=LLMConfig(
            provider=llm_raw.get("provider", "gemini"),
            model=llm_raw.get("model", "gemini-3.1-flash-lite"),
            max_retries=llm_raw.get("max_retries", 2),
            request_timeout_seconds=llm_raw.get("request_timeout_seconds", 30),
            max_input_chars=llm_raw.get("max_input_chars", 8000),
        ),
        sources=_load_sources(raw.get("sources", {})),
        pipeline=PipelineConfig(
            top_n=pipeline_raw.get("top_n", 10),
            categories=pipeline_raw.get("categories", ["ETC"]),
            keywords=pipeline_raw.get("keywords", []),
        ),
        dedup=DedupConfig(
            retention_days=dedup_raw.get("retention_days", 30),
        ),
        site=SiteConfig(
            base_url=site_raw.get("base_url", "/game-legal-briefing"),
        ),
        email=EmailConfig(
            subject_prefix=email_raw.get("subject_prefix", "[Game Legal Briefing]"),
        ),
    )
