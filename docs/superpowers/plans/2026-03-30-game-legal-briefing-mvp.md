# Game Legal Briefing MVP Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an open-source game industry regulatory intelligence platform that collects RSS articles, classifies them with structured metadata via Gemini AI, publishes a static briefing site, and emails subscribers.

**Architecture:** Pipeline architecture with structured metadata as the core primitive. RSS sources → LLM-based selection/classification/summarization → BriefingNode JSON → static HTML site + email + Google Sheets admin log. Each subsystem is a separate module under `pipeline/`.

**Tech Stack:** Python 3.11+, Jinja2, google-generativeai, anthropic, feedparser, gspread, premailer, pytest

---

## Chunk 1: Foundation

### Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `config.yaml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `LICENSE`
- Create: `pipeline/__init__.py`
- Create: `pipeline/sources/__init__.py`
- Create: `pipeline/intelligence/__init__.py`
- Create: `pipeline/llm/__init__.py`
- Create: `pipeline/store/__init__.py`
- Create: `pipeline/render/__init__.py`
- Create: `pipeline/deliver/__init__.py`
- Create: `pipeline/admin/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/fixtures/`
- Create: `templates/`
- Create: `static/`
- Create: `output/data/daily/`

- [ ] **Step 1: Initialize git repo**

```bash
cd "/Users/kpsfamily/코딩 프로젝트/game-legal-briefing"
git init
```

- [ ] **Step 2: Create .gitignore**

```gitignore
__pycache__/
*.pyc
.env
output/
!output/.gitkeep
.venv/
*.egg-info/
dist/
build/
.pytest_cache/
```

- [ ] **Step 3: Create LICENSE (Apache 2.0)**

Download standard Apache 2.0 license text with copyright `2026 lowtidebuild`.

- [ ] **Step 4: Create requirements.txt**

```
feedparser>=6.0
jinja2>=3.1
google-generativeai>=0.8
anthropic>=0.40
gspread>=6.0
google-auth>=2.0
premailer>=3.10
python-dotenv>=1.0
pyyaml>=6.0
pytest>=8.0
```

- [ ] **Step 5: Create .env.example**

```env
GOOGLE_API_KEY=your-gemini-api-key
ANTHROPIC_API_KEY=your-claude-api-key-optional
SMTP_USER=your-gmail@gmail.com
SMTP_PASS=your-gmail-app-password
RECIPIENTS=email1@example.com,email2@example.com
GOOGLE_SHEETS_CREDENTIALS=path/to/service-account.json
GOOGLE_SHEETS_ID=your-spreadsheet-id
```

- [ ] **Step 6: Create config.yaml**

```yaml
llm:
  provider: gemini
  model: gemini-3.1-flash-lite
  max_retries: 2
  request_timeout_seconds: 30
  max_input_chars: 8000

sources:
  tier_a:
    - name: "GamesIndustry.biz"
      url: "https://www.gamesindustry.biz/feed"
    # ... (full source list ported from v1 in a later task)
  tier_b: []

pipeline:
  top_n: 10
  categories:
    - IP
    - CONSUMER_MONETIZATION
    - CONTENT_AGE
    - PRIVACY_SECURITY
    - PLATFORM_PUBLISHING
    - AI_EMERGING
    - MA_CORP_ANTITRUST
    - ESPORTS_MARKETING
    - LABOR_EMPLOYMENT
    - ETC
  keywords:
    - game
    - gaming
    - loot box
    - microtransaction
    - esports
    - age rating
    - PEGI
    - ESRB
    - CERO
    - Nintendo
    - Sony
    - Microsoft
    - Epic Games
    - Steam
    - Valve
    - regulation
    - FTC
    - privacy
    - data protection
    - GDPR
    - COPPA

dedup:
  retention_days: 30

site:
  base_url: "/game-legal-briefing"

email:
  subject_prefix: "[Game Legal Briefing]"
```

- [ ] **Step 7: Create all `__init__.py` files and directory structure**

```bash
mkdir -p pipeline/{sources,intelligence,llm,store,render,deliver,admin}
mkdir -p tests/fixtures
mkdir -p templates/email
mkdir -p static
mkdir -p output/data/daily
touch pipeline/__init__.py
touch pipeline/{sources,intelligence,llm,store,render,deliver,admin}/__init__.py
touch tests/__init__.py
touch output/.gitkeep
```

- [ ] **Step 8: Commit**

```bash
git add .gitignore LICENSE requirements.txt config.yaml .env.example
git add pipeline/ tests/ output/.gitkeep
git commit -m "feat: project scaffolding with directory structure and config"
```

---

### Task 2: Data Models and Enums

**Files:**
- Create: `pipeline/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write tests for data models**

```python
# tests/test_models.py
import json
from pipeline.models import (
    Jurisdiction, RegulatoryPhase, EventType, VALID_CATEGORIES,
    LegalEvent, BriefingNode, briefing_node_to_dict, dict_to_briefing_node,
)


def test_jurisdiction_values():
    assert Jurisdiction.KR == "KR"
    assert Jurisdiction.EU == "EU"
    assert Jurisdiction.GLOBAL == "Global"


def test_regulatory_phase_values():
    assert RegulatoryPhase.PROPOSED == "proposed"
    assert RegulatoryPhase.ENACTED == "enacted"


def test_event_type_values():
    assert EventType.ENFORCEMENT == "enforcement"
    assert EventType.LEGISLATION == "legislation"


def test_valid_categories_complete():
    expected = {
        "IP", "CONSUMER_MONETIZATION", "CONTENT_AGE", "PRIVACY_SECURITY",
        "PLATFORM_PUBLISHING", "AI_EMERGING", "MA_CORP_ANTITRUST",
        "ESPORTS_MARKETING", "LABOR_EMPLOYMENT", "ETC",
    }
    assert VALID_CATEGORIES == expected


def _sample_event():
    return LegalEvent(
        jurisdiction=Jurisdiction.EU,
        event_type=EventType.LEGISLATION,
        regulatory_phase=RegulatoryPhase.ENACTED,
        actors=["EU Commission"],
        object="loot box regulation",
        action="enacted directive",
        game_mechanic="loot_box",
        time_hint="2026 Q2",
    )


def _sample_node():
    return BriefingNode(
        title="EU Enacts Loot Box Regulation",
        url="https://example.com/article",
        source="GamesIndustry.biz",
        pub_date="2026-03-28",
        category="CONSUMER_MONETIZATION",
        summary_ko=["EU가 루트박스 규제를 확정했다.", "2026년 2분기부터 시행.", "게임사 영향 불가피."],
        event=_sample_event(),
        event_key="eu_lootbox_enacted_2026",
        is_primary=True,
    )


def test_briefing_node_roundtrip():
    """BriefingNode -> dict -> JSON -> dict -> BriefingNode preserves all fields."""
    node = _sample_node()
    d = briefing_node_to_dict(node)
    json_str = json.dumps(d, ensure_ascii=False)
    d2 = json.loads(json_str)
    node2 = dict_to_briefing_node(d2)
    assert node2.title == node.title
    assert node2.event.jurisdiction == Jurisdiction.EU
    assert node2.event.game_mechanic == "loot_box"
    assert node2.summary_ko == node.summary_ko


def test_briefing_node_to_dict_structure():
    node = _sample_node()
    d = briefing_node_to_dict(node)
    assert d["title"] == "EU Enacts Loot Box Regulation"
    assert d["event"]["jurisdiction"] == "EU"
    assert d["event"]["regulatory_phase"] == "enacted"
    assert isinstance(d["summary_ko"], list)


def test_dict_to_briefing_node_with_none_mechanic():
    node = _sample_node()
    node.event.game_mechanic = None
    d = briefing_node_to_dict(node)
    node2 = dict_to_briefing_node(d)
    assert node2.event.game_mechanic is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/kpsfamily/코딩 프로젝트/game-legal-briefing" && python -m pytest tests/test_models.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement models.py**

```python
# pipeline/models.py
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from enum import Enum


class Jurisdiction(str, Enum):
    EU = "EU"
    KR = "KR"
    US = "US"
    UK = "UK"
    JP = "JP"
    AU = "AU"
    CN = "CN"
    GLOBAL = "Global"


class RegulatoryPhase(str, Enum):
    PROPOSED = "proposed"
    PUBLIC_COMMENT = "public_comment"
    ENACTED = "enacted"
    ENFORCED = "enforced"
    LITIGATION = "litigation"


class EventType(str, Enum):
    ENFORCEMENT = "enforcement"
    LEGISLATION = "legislation"
    LITIGATION = "litigation"
    POLICY = "policy"
    SECURITY_INCIDENT = "security_incident"
    BUSINESS = "business"
    OTHER = "other"


VALID_CATEGORIES: set[str] = {
    "IP", "CONSUMER_MONETIZATION", "CONTENT_AGE", "PRIVACY_SECURITY",
    "PLATFORM_PUBLISHING", "AI_EMERGING", "MA_CORP_ANTITRUST",
    "ESPORTS_MARKETING", "LABOR_EMPLOYMENT", "ETC",
}


@dataclass
class LegalEvent:
    jurisdiction: Jurisdiction
    event_type: EventType
    regulatory_phase: RegulatoryPhase
    actors: list[str]
    object: str
    action: str
    game_mechanic: str | None
    time_hint: str


@dataclass
class BriefingNode:
    title: str
    url: str
    source: str
    pub_date: str
    category: str
    summary_ko: list[str]
    event: LegalEvent
    event_key: str
    is_primary: bool


def briefing_node_to_dict(node: BriefingNode) -> dict:
    """Serialize BriefingNode to a plain dict for JSON storage."""
    d = dataclasses.asdict(node)
    d["event"]["jurisdiction"] = node.event.jurisdiction.value
    d["event"]["event_type"] = node.event.event_type.value
    d["event"]["regulatory_phase"] = node.event.regulatory_phase.value
    return d


def dict_to_briefing_node(d: dict) -> BriefingNode:
    """Deserialize a dict (from JSON) back to BriefingNode."""
    event_data = d["event"]
    event = LegalEvent(
        jurisdiction=Jurisdiction(event_data["jurisdiction"]),
        event_type=EventType(event_data["event_type"]),
        regulatory_phase=RegulatoryPhase(event_data["regulatory_phase"]),
        actors=event_data["actors"],
        object=event_data["object"],
        action=event_data["action"],
        game_mechanic=event_data.get("game_mechanic"),
        time_hint=event_data["time_hint"],
    )
    return BriefingNode(
        title=d["title"],
        url=d["url"],
        source=d["source"],
        pub_date=d["pub_date"],
        category=d["category"],
        summary_ko=d["summary_ko"],
        event=event,
        event_key=d["event_key"],
        is_primary=d["is_primary"],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/kpsfamily/코딩 프로젝트/game-legal-briefing" && python -m pytest tests/test_models.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/models.py tests/test_models.py
git commit -m "feat: BriefingNode data model with enums and JSON serialization"
```

---

### Task 3: Config Loading

**Files:**
- Create: `pipeline/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write tests for config loading**

```python
# tests/test_config.py
import os
import tempfile
import yaml
from pipeline.config import load_config, Config


def test_load_config_from_file():
    data = {
        "llm": {"provider": "gemini", "model": "gemini-3.1-flash-lite", "max_retries": 2,
                "request_timeout_seconds": 30, "max_input_chars": 8000},
        "sources": {"tier_a": [{"name": "Test", "url": "https://example.com/feed"}], "tier_b": []},
        "pipeline": {"top_n": 10, "categories": ["IP", "ETC"]},
        "dedup": {"retention_days": 30},
        "site": {"base_url": "/game-legal-briefing"},
        "email": {"subject_prefix": "[Test]"},
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        path = f.name
    try:
        cfg = load_config(path)
        assert cfg.llm.provider == "gemini"
        assert cfg.llm.model == "gemini-3.1-flash-lite"
        assert cfg.llm.max_retries == 2
        assert cfg.pipeline.top_n == 10
        assert cfg.dedup.retention_days == 30
        assert len(cfg.sources.tier_a) == 1
    finally:
        os.unlink(path)


def test_load_config_env_override(monkeypatch):
    """ANTHROPIC_API_KEY env var should be accessible via config."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-123")
    data = {
        "llm": {"provider": "gemini", "model": "gemini-3.1-flash-lite", "max_retries": 2,
                "request_timeout_seconds": 30, "max_input_chars": 8000},
        "sources": {"tier_a": [], "tier_b": []},
        "pipeline": {"top_n": 10, "categories": ["ETC"]},
        "dedup": {"retention_days": 30},
        "site": {"base_url": "/game-legal-briefing"},
        "email": {"subject_prefix": "[Test]"},
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        path = f.name
    try:
        cfg = load_config(path)
        assert cfg.google_api_key == "test-key-123"
    finally:
        os.unlink(path)


def test_config_defaults():
    """Config should have sensible defaults for missing optional fields."""
    data = {
        "llm": {"provider": "gemini", "model": "gemini-3.1-flash-lite"},
        "sources": {"tier_a": [], "tier_b": []},
        "pipeline": {"top_n": 10, "categories": ["ETC"]},
        "dedup": {},
        "email": {},
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        path = f.name
    try:
        cfg = load_config(path)
        assert cfg.llm.max_retries == 2
        assert cfg.llm.request_timeout_seconds == 30
        assert cfg.llm.max_input_chars == 8000
        assert cfg.dedup.retention_days == 30
        assert cfg.site.base_url == "/game-legal-briefing"
        assert cfg.email.subject_prefix == "[Game Legal Briefing]"
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL

- [ ] **Step 3: Implement config.py**

```python
# pipeline/config.py
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
        return [r.strip() for r in raw.split(",") if r.strip()]

    @property
    def google_sheets_credentials(self) -> str | None:
        return os.environ.get("GOOGLE_SHEETS_CREDENTIALS")

    @property
    def google_sheets_id(self) -> str | None:
        return os.environ.get("GOOGLE_SHEETS_ID")


def load_config(path: str) -> Config:
    """Load config from a YAML file. Missing optional fields use defaults."""
    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    llm_raw = raw.get("llm", {})
    llm = LLMConfig(
        provider=llm_raw.get("provider", "gemini"),
        model=llm_raw.get("model", "gemini-3.1-flash-lite"),
        max_retries=llm_raw.get("max_retries", 2),
        request_timeout_seconds=llm_raw.get("request_timeout_seconds", 30),
        max_input_chars=llm_raw.get("max_input_chars", 8000),
    )

    sources_raw = raw.get("sources", {})
    tier_a = [SourceEntry(name=s["name"], url=s["url"]) for s in sources_raw.get("tier_a", [])]
    tier_b = [SourceEntry(name=s["name"], url=s["url"]) for s in sources_raw.get("tier_b", [])]
    sources = SourcesConfig(tier_a=tier_a, tier_b=tier_b)

    pipe_raw = raw.get("pipeline", {})
    pipeline = PipelineConfig(
        top_n=pipe_raw.get("top_n", 10),
        categories=pipe_raw.get("categories", ["ETC"]),
        keywords=pipe_raw.get("keywords", []),
    )

    dedup_raw = raw.get("dedup", {})
    dedup = DedupConfig(retention_days=dedup_raw.get("retention_days", 30))

    site_raw = raw.get("site", {})
    site = SiteConfig(base_url=site_raw.get("base_url", "/game-legal-briefing"))

    email_raw = raw.get("email", {})
    email = EmailConfig(subject_prefix=email_raw.get("subject_prefix", "[Game Legal Briefing]"))

    return Config(llm=llm, sources=sources, pipeline=pipeline, dedup=dedup, site=site, email=email)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/config.py tests/test_config.py
git commit -m "feat: YAML config loading with env var secrets and defaults"
```

---

## Chunk 2: LLM Layer

### Task 4: Abstract LLM Provider

**Files:**
- Create: `pipeline/llm/base.py`
- Create: `tests/test_llm_base.py`

- [ ] **Step 1: Write tests for base LLM provider**

```python
# tests/test_llm_base.py
import json
import pytest
from pipeline.llm.base import LLMProvider, LLMResponse, extract_json_from_text


class MockProvider(LLMProvider):
    """Concrete test implementation that returns canned responses."""

    def __init__(self, responses: list[str]):
        super().__init__(max_retries=2, request_timeout_seconds=5)
        self._responses = responses
        self._call_count = 0

    def _call_api(self, prompt: str, system: str | None = None) -> str:
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        return self._responses[idx]


def test_generate_returns_llm_response():
    provider = MockProvider(['{"result": "ok"}'])
    resp = provider.generate("test prompt")
    assert isinstance(resp, LLMResponse)
    assert resp.text == '{"result": "ok"}'


def test_generate_json_parses_valid_json():
    provider = MockProvider(['{"key": "value"}'])
    result = provider.generate_json("test prompt")
    assert result == {"key": "value"}


def test_generate_json_retries_on_invalid_json():
    provider = MockProvider(['not json', '{"key": "value"}'])
    result = provider.generate_json("test prompt")
    assert result == {"key": "value"}
    assert provider._call_count == 2


def test_extract_json_from_text_finds_json_in_markdown():
    text = 'Here is the result:\n```json\n{"a": 1}\n```\nDone.'
    result = extract_json_from_text(text)
    assert result == {"a": 1}


def test_extract_json_from_text_finds_bare_json():
    text = 'some text {"a": 1} more text'
    result = extract_json_from_text(text)
    assert result == {"a": 1}


def test_extract_json_from_text_returns_none_for_no_json():
    assert extract_json_from_text("no json here") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_llm_base.py -v`
Expected: FAIL

- [ ] **Step 3: Implement base.py**

```python
# pipeline/llm/base.py
from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    text: str


def extract_json_from_text(text: str) -> dict | list | None:
    """Try to extract JSON from LLM output. Handles markdown code blocks and bare JSON."""
    # Try markdown code block first
    match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try to find bare JSON object or array
    for pattern in [r"\{[\s\S]*\}", r"\[[\s\S]*\]"]:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                continue

    return None


class LLMProvider(ABC):
    """Abstract base for LLM API calls with retry, backoff, and JSON extraction."""

    def __init__(self, max_retries: int = 2, request_timeout_seconds: int = 30):
        self.max_retries = max_retries
        self.request_timeout_seconds = request_timeout_seconds

    @abstractmethod
    def _call_api(self, prompt: str, system: str | None = None) -> str:
        """Make one API call. Subclasses implement this."""
        ...

    def generate(self, prompt: str, system: str | None = None) -> LLMResponse:
        """Call LLM with retry on transient errors."""
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                text = self._call_api(prompt, system)
                return LLMResponse(text=text)
            except Exception as e:
                last_error = e
                if "429" in str(e) or "rate" in str(e).lower():
                    wait = 60
                    logger.warning("Rate limited, waiting %ds (attempt %d)", wait, attempt + 1)
                    time.sleep(wait)
                else:
                    wait = 2 ** attempt
                    logger.warning("LLM error: %s, retrying in %ds (attempt %d)", e, wait, attempt + 1)
                    time.sleep(wait)
        raise last_error  # type: ignore[misc]

    def generate_json(self, prompt: str, system: str | None = None) -> dict | list:
        """Call LLM and parse response as JSON. Retries on parse failure.
        Note: calls _call_api directly to avoid compounding with generate() retries."""
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                text = self._call_api(prompt, system)
            except Exception as e:
                last_error = e
                wait = 2 ** attempt
                logger.warning("LLM error in generate_json: %s, retrying in %ds", e, wait)
                time.sleep(wait)
                continue
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                extracted = extract_json_from_text(text)
                if extracted is not None:
                    return extracted
                last_error = ValueError(f"Could not parse JSON from: {text[:200]}")
                logger.warning("JSON parse failed (attempt %d), retrying", attempt + 1)
        raise last_error  # type: ignore[misc]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_llm_base.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/llm/base.py tests/test_llm_base.py
git commit -m "feat: abstract LLM provider with retry, backoff, and JSON extraction"
```

---

### Task 5: Gemini Provider

**Files:**
- Create: `pipeline/llm/gemini.py`
- Create: `tests/test_llm_gemini.py`
- Create: `tests/fixtures/sample_gemini_response.json`

- [ ] **Step 1: Create test fixture**

```json
// tests/fixtures/sample_gemini_response.json
{
  "candidates": [
    {
      "content": {
        "parts": [{"text": "{\"category\": \"IP\", \"jurisdiction\": \"US\"}"}]
      }
    }
  ]
}
```

- [ ] **Step 2: Write tests for Gemini provider**

```python
# tests/test_llm_gemini.py
from unittest.mock import MagicMock, patch
from pipeline.llm.gemini import GeminiProvider


def test_gemini_provider_init():
    with patch("pipeline.llm.gemini.genai") as mock_genai:
        provider = GeminiProvider(api_key="test-key", model="gemini-3.1-flash-lite")
        mock_genai.configure.assert_called_once_with(api_key="test-key")


def test_gemini_call_api():
    with patch("pipeline.llm.gemini.genai") as mock_genai:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"result": "ok"}'
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        provider = GeminiProvider(api_key="test-key", model="gemini-3.1-flash-lite")
        result = provider._call_api("test prompt")
        assert result == '{"result": "ok"}'


def test_gemini_call_api_with_system():
    with patch("pipeline.llm.gemini.genai") as mock_genai:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"result": "ok"}'
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        provider = GeminiProvider(api_key="test-key", model="gemini-3.1-flash-lite")
        result = provider._call_api("test prompt", system="you are a legal analyst")
        assert result == '{"result": "ok"}'
        # System instruction should be passed to GenerativeModel
        call_kwargs = mock_genai.GenerativeModel.call_args
        assert call_kwargs[1].get("system_instruction") == "you are a legal analyst"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_llm_gemini.py -v`
Expected: FAIL

- [ ] **Step 4: Implement gemini.py**

```python
# pipeline/llm/gemini.py
from __future__ import annotations

import google.generativeai as genai

from pipeline.llm.base import LLMProvider


class GeminiProvider(LLMProvider):
    """Google Gemini API implementation."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.1-flash-lite",
        max_retries: int = 2,
        request_timeout_seconds: int = 30,
    ):
        super().__init__(max_retries=max_retries, request_timeout_seconds=request_timeout_seconds)
        genai.configure(api_key=api_key)
        self._model_name = model
        self._model_cache: dict[str | None, object] = {}

    def _get_model(self, system: str | None = None):
        """Get or create a cached model instance for the given system instruction."""
        if system not in self._model_cache:
            self._model_cache[system] = genai.GenerativeModel(
                model_name=self._model_name,
                system_instruction=system,
            )
        return self._model_cache[system]

    def _call_api(self, prompt: str, system: str | None = None) -> str:
        model = self._get_model(system)
        response = model.generate_content(prompt)
        return response.text
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_llm_gemini.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add pipeline/llm/gemini.py tests/test_llm_gemini.py tests/fixtures/sample_gemini_response.json
git commit -m "feat: Gemini LLM provider implementation"
```

---

### Task 6: Claude Provider (Fallback)

**Files:**
- Create: `pipeline/llm/claude.py`
- Create: `tests/test_llm_claude.py`

- [ ] **Step 1: Write tests for Claude provider**

```python
# tests/test_llm_claude.py
from unittest.mock import MagicMock, patch
from pipeline.llm.claude import ClaudeProvider


def test_claude_provider_init():
    with patch("pipeline.llm.claude.anthropic.Anthropic") as mock_cls:
        provider = ClaudeProvider(api_key="test-key", model="claude-haiku-4-5-20251001")
        mock_cls.assert_called_once_with(api_key="test-key")


def test_claude_call_api():
    with patch("pipeline.llm.claude.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"result": "ok"}')]
        mock_client.messages.create.return_value = mock_response
        mock_cls.return_value = mock_client

        provider = ClaudeProvider(api_key="test-key", model="claude-haiku-4-5-20251001")
        result = provider._call_api("test prompt", system="be helpful")
        assert result == '{"result": "ok"}'
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
        assert call_kwargs["system"] == "be helpful"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_llm_claude.py -v`
Expected: FAIL

- [ ] **Step 3: Implement claude.py**

```python
# pipeline/llm/claude.py
from __future__ import annotations

import anthropic

from pipeline.llm.base import LLMProvider


class ClaudeProvider(LLMProvider):
    """Anthropic Claude API implementation (fallback provider)."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-haiku-4-5-20251001",
        max_retries: int = 2,
        request_timeout_seconds: int = 30,
    ):
        super().__init__(max_retries=max_retries, request_timeout_seconds=request_timeout_seconds)
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def _call_api(self, prompt: str, system: str | None = None) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_llm_claude.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/llm/claude.py tests/test_llm_claude.py
git commit -m "feat: Claude LLM provider as fallback"
```

---

### Task 7: LLM Provider Factory

**Files:**
- Modify: `pipeline/llm/__init__.py`
- Create: `tests/test_llm_factory.py`

- [ ] **Step 1: Write tests for factory**

```python
# tests/test_llm_factory.py
from unittest.mock import patch
import pytest
from pipeline.llm import create_provider
from pipeline.llm.gemini import GeminiProvider
from pipeline.llm.claude import ClaudeProvider
from pipeline.config import LLMConfig


def test_create_gemini_provider():
    cfg = LLMConfig(provider="gemini", model="gemini-3.1-flash-lite")
    with patch("pipeline.llm.gemini.genai"):
        provider = create_provider(cfg, google_api_key="test-key")
    assert isinstance(provider, GeminiProvider)


def test_create_claude_provider():
    cfg = LLMConfig(provider="claude", model="claude-haiku-4-5-20251001")
    with patch("pipeline.llm.claude.anthropic.Anthropic"):
        provider = create_provider(cfg, anthropic_api_key="test-key")
    assert isinstance(provider, ClaudeProvider)


def test_create_provider_unknown_raises():
    cfg = LLMConfig(provider="unknown")
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        create_provider(cfg)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_llm_factory.py -v`
Expected: FAIL

- [ ] **Step 3: Implement factory in __init__.py**

```python
# pipeline/llm/__init__.py
from __future__ import annotations

from pipeline.config import LLMConfig
from pipeline.llm.base import LLMProvider


def create_provider(
    cfg: LLMConfig,
    google_api_key: str | None = None,
    anthropic_api_key: str | None = None,
) -> LLMProvider:
    """Create an LLM provider from config."""
    if cfg.provider == "gemini":
        from pipeline.llm.gemini import GeminiProvider
        if not google_api_key:
            raise ValueError("GOOGLE_API_KEY required for Gemini provider")
        return GeminiProvider(
            api_key=google_api_key,
            model=cfg.model,
            max_retries=cfg.max_retries,
            request_timeout_seconds=cfg.request_timeout_seconds,
        )
    elif cfg.provider == "claude":
        from pipeline.llm.claude import ClaudeProvider
        if not anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY required for Claude provider")
        return ClaudeProvider(
            api_key=anthropic_api_key,
            model=cfg.model,
            max_retries=cfg.max_retries,
            request_timeout_seconds=cfg.request_timeout_seconds,
        )
    else:
        raise ValueError(f"Unknown LLM provider: {cfg.provider}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_llm_factory.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/llm/__init__.py tests/test_llm_factory.py
git commit -m "feat: LLM provider factory for gemini/claude switching"
```

---

## Chunk 3: Sources + Dedup

### Task 8: RSS Feed Collection

**Files:**
- Create: `pipeline/sources/rss.py`
- Create: `tests/test_rss.py`
- Create: `tests/fixtures/sample_rss.xml`

- [ ] **Step 1: Create test fixture**

```xml
<!-- tests/fixtures/sample_rss.xml -->
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>EU Loot Box Regulation Update</title>
      <link>https://example.com/eu-lootbox</link>
      <description>The EU has updated its stance on loot boxes in games.</description>
      <pubDate>Mon, 23 Mar 2026 10:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Korean Age Rating System Changes</title>
      <link>https://example.com/kr-age-rating</link>
      <description>South Korea announces new age rating requirements for mobile games.</description>
      <pubDate>Sun, 22 Mar 2026 08:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
```

- [ ] **Step 2: Write tests for RSS collection**

```python
# tests/test_rss.py
import os
from unittest.mock import patch, MagicMock
from pipeline.sources.rss import fetch_feed, fetch_all_feeds, RawArticle
from pipeline.config import SourceEntry


FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample_rss.xml")


def test_raw_article_fields():
    article = RawArticle(
        title="Test", url="https://example.com", source="TestFeed",
        description="desc", pub_date="2026-03-23",
    )
    assert article.title == "Test"
    assert article.source == "TestFeed"


def test_fetch_feed_parses_fixture():
    with open(FIXTURE_PATH) as f:
        xml_content = f.read()

    with patch("pipeline.sources.rss.feedparser.parse") as mock_parse:
        mock_parse.return_value = MagicMock(
            entries=[
                MagicMock(title="EU Loot Box Regulation Update",
                         link="https://example.com/eu-lootbox",
                         get=lambda k, d="": {"summary": "The EU has updated..."}.get(k, d),
                         published_parsed=(2026, 3, 23, 10, 0, 0, 0, 82, 0)),
                MagicMock(title="Korean Age Rating System Changes",
                         link="https://example.com/kr-age-rating",
                         get=lambda k, d="": {"summary": "South Korea announces..."}.get(k, d),
                         published_parsed=(2026, 3, 22, 8, 0, 0, 6, 81, 0)),
            ]
        )
        source = SourceEntry(name="Test Feed", url="https://example.com/feed")
        articles = fetch_feed(source)
        assert len(articles) == 2
        assert articles[0].title == "EU Loot Box Regulation Update"
        assert articles[0].source == "Test Feed"


def test_fetch_feed_handles_error():
    with patch("pipeline.sources.rss.feedparser.parse", side_effect=Exception("Network error")):
        source = SourceEntry(name="BadFeed", url="https://bad.example.com/feed")
        articles = fetch_feed(source)
        assert articles == []


def test_fetch_all_feeds_combines_sources():
    source_a = SourceEntry(name="FeedA", url="https://a.com/feed")
    source_b = SourceEntry(name="FeedB", url="https://b.com/feed")

    def mock_fetch(source):
        return [RawArticle(title=f"Article from {source.name}", url=f"https://{source.name}",
                          source=source.name, description="", pub_date="2026-03-23")]

    with patch("pipeline.sources.rss.fetch_feed", side_effect=mock_fetch):
        articles = fetch_all_feeds(tier_a=[source_a], tier_b=[source_b])
        assert len(articles) == 2
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_rss.py -v`
Expected: FAIL

- [ ] **Step 4: Implement rss.py**

```python
# pipeline/sources/rss.py
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import feedparser

from pipeline.config import SourceEntry

logger = logging.getLogger(__name__)


@dataclass
class RawArticle:
    title: str
    url: str
    source: str
    description: str
    pub_date: str


def _format_date(parsed_time) -> str:
    """Convert feedparser time struct to YYYY-MM-DD string."""
    if parsed_time:
        return time.strftime("%Y-%m-%d", parsed_time)
    return ""


def fetch_feed(source: SourceEntry) -> list[RawArticle]:
    """Fetch and parse a single RSS feed. Returns empty list on error."""
    try:
        feed = feedparser.parse(source.url)
        articles = []
        for entry in feed.entries:
            articles.append(RawArticle(
                title=entry.title,
                url=entry.link,
                source=source.name,
                description=entry.get("summary", ""),
                pub_date=_format_date(getattr(entry, "published_parsed", None)),
            ))
        logger.info("Fetched %d articles from %s", len(articles), source.name)
        return articles
    except Exception as e:
        logger.warning("Failed to fetch %s: %s", source.name, e)
        return []


def fetch_all_feeds(
    tier_a: list[SourceEntry],
    tier_b: list[SourceEntry],
) -> list[RawArticle]:
    """Fetch all RSS feeds. tier_a failures are logged, tier_b are silent."""
    articles = []
    for source in tier_a:
        result = fetch_feed(source)
        if not result:
            logger.warning("tier_a source %s returned no articles", source.name)
        articles.extend(result)
    for source in tier_b:
        articles.extend(fetch_feed(source))
    logger.info("Total raw articles collected: %d", len(articles))
    return articles
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_rss.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add pipeline/sources/rss.py tests/test_rss.py tests/fixtures/sample_rss.xml
git commit -m "feat: RSS feed collection with graceful error handling"
```

---

### Task 9: Keyword Pre-Filtering

**Files:**
- Create: `pipeline/sources/filters.py`
- Create: `tests/test_filters.py`

- [ ] **Step 1: Write tests for keyword filtering**

```python
# tests/test_filters.py
from pipeline.sources.rss import RawArticle
from pipeline.sources.filters import keyword_filter

GAME_LEGAL_KEYWORDS = [
    "game", "gaming", "loot box", "microtransaction", "esports",
    "age rating", "PEGI", "ESRB", "CERO", "Nintendo", "Sony", "Microsoft",
    "Epic Games", "Steam", "Valve", "regulation", "FTC", "privacy",
    "data protection", "GDPR", "COPPA",
]


def _article(title: str, description: str = "") -> RawArticle:
    return RawArticle(title=title, url="https://example.com", source="Test",
                     description=description, pub_date="2026-03-23")


def test_keyword_filter_matches_title():
    articles = [
        _article("EU Loot Box Regulation"),
        _article("Weather Report for March"),
    ]
    result = keyword_filter(articles, GAME_LEGAL_KEYWORDS)
    assert len(result) == 1
    assert result[0].title == "EU Loot Box Regulation"


def test_keyword_filter_matches_description():
    articles = [_article("New Policy", description="FTC announces gaming probe")]
    result = keyword_filter(articles, GAME_LEGAL_KEYWORDS)
    assert len(result) == 1


def test_keyword_filter_case_insensitive():
    articles = [_article("NINTENDO Files Patent Lawsuit")]
    result = keyword_filter(articles, GAME_LEGAL_KEYWORDS)
    assert len(result) == 1


def test_keyword_filter_empty_keywords_returns_all():
    articles = [_article("Anything")]
    result = keyword_filter(articles, [])
    assert len(result) == 1


def test_keyword_filter_no_matches():
    articles = [_article("Cooking Recipes for Spring")]
    result = keyword_filter(articles, GAME_LEGAL_KEYWORDS)
    assert len(result) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_filters.py -v`
Expected: FAIL

- [ ] **Step 3: Implement filters.py**

```python
# pipeline/sources/filters.py
from __future__ import annotations

import logging

from pipeline.sources.rss import RawArticle

logger = logging.getLogger(__name__)


def keyword_filter(articles: list[RawArticle], keywords: list[str]) -> list[RawArticle]:
    """Filter articles by keyword match in title or description. Case-insensitive."""
    if not keywords:
        return articles

    keywords_lower = [kw.lower() for kw in keywords]
    result = []
    for article in articles:
        text = f"{article.title} {article.description}".lower()
        if any(kw in text for kw in keywords_lower):
            result.append(article)

    logger.info("Keyword filter: %d → %d articles", len(articles), len(result))
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_filters.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/sources/filters.py tests/test_filters.py
git commit -m "feat: keyword pre-filtering for RSS articles"
```

---

### Task 10: 3-Stage Deduplication

**Files:**
- Create: `pipeline/intelligence/dedup.py`
- Create: `tests/test_dedup.py`

- [ ] **Step 1: Write tests for dedup**

```python
# tests/test_dedup.py
import hashlib
from pipeline.intelligence.dedup import (
    url_hash, topic_tokens_hash, compute_event_key,
    deduplicate_articles, DedupIndex, DedupEntry,
)
from pipeline.sources.rss import RawArticle


def _article(title: str, url: str, description: str = "") -> RawArticle:
    return RawArticle(title=title, url=url, source="Test",
                     description=description, pub_date="2026-03-23")


def test_url_hash_deterministic():
    h1 = url_hash("https://example.com/article")
    h2 = url_hash("https://example.com/article")
    assert h1 == h2
    assert len(h1) == 16  # 8 bytes hex


def test_url_hash_different_urls():
    h1 = url_hash("https://example.com/a")
    h2 = url_hash("https://example.com/b")
    assert h1 != h2


def test_topic_tokens_hash():
    h1 = topic_tokens_hash("EU Loot Box Regulation Update")
    h2 = topic_tokens_hash("Update: EU Loot Box Regulation")
    # Same meaningful words, should produce same hash
    assert h1 == h2


def test_compute_event_key():
    key = compute_event_key(jurisdiction="EU", actors=["EU Commission"],
                           object_="loot box", action="regulation")
    assert isinstance(key, str)
    assert len(key) == 16


def test_deduplicate_by_url():
    articles = [
        _article("Article A", "https://example.com/same"),
        _article("Article B", "https://example.com/same"),
    ]
    result = deduplicate_articles(articles, DedupIndex(entries=[]))
    assert len(result) == 1


def test_deduplicate_by_topic_tokens():
    articles = [
        _article("EU Loot Box Regulation", "https://a.com/1"),
        _article("Loot Box Regulation EU", "https://b.com/2"),
    ]
    result = deduplicate_articles(articles, DedupIndex(entries=[]))
    assert len(result) == 1


def test_deduplicate_respects_existing_index():
    existing = DedupIndex(entries=[
        DedupEntry(event_key="", url_hash=url_hash("https://old.com/article"), date="2026-03-20"),
    ])
    articles = [
        _article("Old Article", "https://old.com/article"),
        _article("New Article", "https://new.com/article"),
    ]
    result = deduplicate_articles(articles, existing)
    assert len(result) == 1
    assert result[0].title == "New Article"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_dedup.py -v`
Expected: FAIL

- [ ] **Step 3: Implement dedup.py**

```python
# pipeline/intelligence/dedup.py
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field

from pipeline.sources.rss import RawArticle

logger = logging.getLogger(__name__)

# Common words to ignore in topic token hashing
STOP_WORDS = {"the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or", "is", "are",
              "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
              "will", "would", "could", "should", "may", "might", "can", "shall", "with", "by",
              "from", "up", "about", "into", "over", "after", "update", "new", "latest"}


@dataclass
class DedupEntry:
    event_key: str
    url_hash: str
    date: str


@dataclass
class DedupIndex:
    entries: list[DedupEntry] = field(default_factory=list)
    schema_version: int = 1
    retention_days: int = 30


def url_hash(url: str) -> str:
    """Deterministic 16-char hex hash of a URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def topic_tokens_hash(title: str) -> str:
    """Hash of sorted meaningful words in a title. Order-independent.
    Uses \\w to match Unicode characters (Korean, Japanese, etc.)."""
    words = re.findall(r"\w+", title.lower())
    meaningful = sorted(set(words) - STOP_WORDS)
    return hashlib.sha256(" ".join(meaningful).encode()).hexdigest()[:16]


def compute_event_key(
    jurisdiction: str, actors: list[str], object_: str, action: str,
) -> str:
    """Compute a deterministic event key from structured metadata."""
    parts = [jurisdiction.lower(), ",".join(sorted(a.lower() for a in actors)),
             object_.lower(), action.lower()]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def deduplicate_articles(
    articles: list[RawArticle],
    index: DedupIndex,
) -> list[RawArticle]:
    """3-stage dedup: URL hash → topic tokens → existing index."""
    existing_url_hashes = {e.url_hash for e in index.entries}

    # Stage 1: URL dedup
    seen_urls: set[str] = set()
    after_url = []
    for article in articles:
        h = url_hash(article.url)
        if h in existing_url_hashes or h in seen_urls:
            continue
        seen_urls.add(h)
        after_url.append(article)

    # Stage 2: Topic token dedup
    seen_topics: set[str] = set()
    after_topic = []
    for article in after_url:
        h = topic_tokens_hash(article.title)
        if h in seen_topics:
            continue
        seen_topics.add(h)
        after_topic.append(article)

    logger.info("Dedup: %d → %d (url) → %d (topic)", len(articles), len(after_url), len(after_topic))
    return after_topic
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dedup.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/intelligence/dedup.py tests/test_dedup.py
git commit -m "feat: 3-stage deduplication (URL, topic tokens, cross-run index)"
```

---

## Chunk 4: Intelligence

### Task 11: AI Article Selector

**Files:**
- Create: `pipeline/intelligence/selector.py`
- Create: `tests/test_selector.py`
- Create: `tests/fixtures/sample_selector_response.json`

- [ ] **Step 1: Create test fixture**

```json
// tests/fixtures/sample_selector_response.json
{
  "selected_indices": [0, 2, 4],
  "reasoning": "Selected articles most relevant to game industry regulation."
}
```

- [ ] **Step 2: Write tests for selector**

```python
# tests/test_selector.py
from unittest.mock import MagicMock
from pipeline.intelligence.selector import select_top_articles
from pipeline.sources.rss import RawArticle
from pipeline.llm.base import LLMProvider


def _articles(n: int) -> list[RawArticle]:
    return [
        RawArticle(title=f"Article {i}", url=f"https://example.com/{i}",
                  source="Test", description=f"Description {i}", pub_date="2026-03-23")
        for i in range(n)
    ]


def test_select_top_articles_returns_subset():
    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.generate_json.return_value = {"selected_indices": [0, 2, 4]}

    articles = _articles(10)
    result = select_top_articles(articles, mock_llm, top_n=3)
    assert len(result) == 3
    assert result[0].title == "Article 0"
    assert result[1].title == "Article 2"
    assert result[2].title == "Article 4"


def test_select_top_articles_fewer_than_top_n():
    """If fewer articles than top_n, return all."""
    mock_llm = MagicMock(spec=LLMProvider)
    articles = _articles(3)
    result = select_top_articles(articles, mock_llm, top_n=10)
    assert len(result) == 3
    # LLM should not be called if articles <= top_n
    mock_llm.generate_json.assert_not_called()


def test_select_handles_out_of_range_indices():
    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.generate_json.return_value = {"selected_indices": [0, 1, 99]}

    articles = _articles(5)
    result = select_top_articles(articles, mock_llm, top_n=3)
    # Should skip index 99 and return valid ones
    assert len(result) == 2


def test_select_handles_llm_failure():
    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.generate_json.side_effect = Exception("LLM failed")

    articles = _articles(10)
    result = select_top_articles(articles, mock_llm, top_n=5)
    # Fallback: return first top_n articles
    assert len(result) == 5
    assert result[0].title == "Article 0"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_selector.py -v`
Expected: FAIL

- [ ] **Step 4: Implement selector.py**

```python
# pipeline/intelligence/selector.py
from __future__ import annotations

import logging

from pipeline.llm.base import LLMProvider
from pipeline.sources.rss import RawArticle

logger = logging.getLogger(__name__)

SELECTOR_PROMPT = """You are a legal analyst specializing in the game industry.

Below are {count} articles. Select the top {top_n} most relevant to game industry regulation, policy, and legal developments.

Articles:
{articles_text}

Return a JSON object with key "selected_indices" containing a list of 0-based indices of the top articles.
Example: {{"selected_indices": [0, 3, 7]}}"""


def select_top_articles(
    articles: list[RawArticle],
    llm: LLMProvider,
    top_n: int = 10,
) -> list[RawArticle]:
    """Use LLM to select the top N most relevant articles."""
    if len(articles) <= top_n:
        return articles

    articles_text = "\n".join(
        f"[{i}] {a.title} — {a.source}\n    {a.description[:200]}"
        for i, a in enumerate(articles)
    )

    prompt = SELECTOR_PROMPT.format(count=len(articles), top_n=top_n, articles_text=articles_text)

    try:
        result = llm.generate_json(prompt)
        indices = result.get("selected_indices", [])
        selected = [articles[i] for i in indices if 0 <= i < len(articles)]
        logger.info("Selector: %d → %d articles", len(articles), len(selected))
        return selected
    except Exception as e:
        logger.warning("Selector LLM failed (%s), returning first %d", e, top_n)
        return articles[:top_n]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_selector.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add pipeline/intelligence/selector.py tests/test_selector.py tests/fixtures/sample_selector_response.json
git commit -m "feat: AI article selector with LLM fallback"
```

---

### Task 12: AI Classifier (Category + Jurisdiction + Phase)

**Files:**
- Create: `pipeline/intelligence/classifier.py`
- Create: `tests/test_classifier.py`
- Create: `tests/fixtures/sample_classifier_response.json`

- [ ] **Step 1: Create test fixture**

```json
// tests/fixtures/sample_classifier_response.json
{
  "category": "CONSUMER_MONETIZATION",
  "jurisdiction": "EU",
  "event_type": "legislation",
  "regulatory_phase": "enacted",
  "actors": ["EU Commission", "European Parliament"],
  "object": "loot box mechanics in games",
  "action": "enacted regulation requiring disclosure",
  "game_mechanic": "loot_box",
  "time_hint": "effective 2026 Q3"
}
```

- [ ] **Step 2: Write tests for classifier**

```python
# tests/test_classifier.py
import json
import os
from unittest.mock import MagicMock
from pipeline.intelligence.classifier import classify_article
from pipeline.sources.rss import RawArticle
from pipeline.llm.base import LLMProvider
from pipeline.models import Jurisdiction, EventType, RegulatoryPhase

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample_classifier_response.json")


def _article() -> RawArticle:
    return RawArticle(
        title="EU Enacts Loot Box Regulation",
        url="https://example.com/eu-lootbox",
        source="GamesIndustry.biz",
        description="The EU has enacted new regulations requiring disclosure of loot box mechanics.",
        pub_date="2026-03-23",
    )


def test_classify_article_returns_legal_event():
    with open(FIXTURE_PATH) as f:
        fixture = json.load(f)

    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.generate_json.return_value = fixture

    result = classify_article(_article(), mock_llm)
    assert result.category == "CONSUMER_MONETIZATION"
    assert result.event.jurisdiction == Jurisdiction.EU
    assert result.event.event_type == EventType.LEGISLATION
    assert result.event.regulatory_phase == RegulatoryPhase.ENACTED
    assert result.event.game_mechanic == "loot_box"
    assert "EU Commission" in result.event.actors


def test_classify_article_fallback_on_failure():
    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.generate_json.side_effect = Exception("LLM failed")

    result = classify_article(_article(), mock_llm)
    assert result.category == "ETC"
    assert result.event.jurisdiction == Jurisdiction.GLOBAL
    assert result.event.event_type == EventType.OTHER


def test_classify_article_invalid_category_defaults():
    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.generate_json.return_value = {
        "category": "INVALID_CATEGORY",
        "jurisdiction": "EU", "event_type": "legislation",
        "regulatory_phase": "enacted", "actors": [], "object": "test",
        "action": "test", "game_mechanic": None, "time_hint": "",
    }

    result = classify_article(_article(), mock_llm)
    assert result.category == "ETC"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_classifier.py -v`
Expected: FAIL

- [ ] **Step 4: Implement classifier.py**

```python
# pipeline/intelligence/classifier.py
from __future__ import annotations

import logging
from dataclasses import dataclass

from pipeline.llm.base import LLMProvider
from pipeline.models import (
    VALID_CATEGORIES, Jurisdiction, EventType, RegulatoryPhase, LegalEvent,
)
from pipeline.sources.rss import RawArticle

logger = logging.getLogger(__name__)

CLASSIFIER_SYSTEM = """You are a legal analyst specializing in the game industry.
Classify the given article and extract structured metadata."""

CLASSIFIER_PROMPT = """Analyze this article and return a JSON object with:
- category: one of {categories}
- jurisdiction: one of {jurisdictions}
- event_type: one of {event_types}
- regulatory_phase: one of {phases}
- actors: list of organizations/entities involved
- object: what is being regulated/affected (short phrase)
- action: what happened (short phrase)
- game_mechanic: relevant game mechanic if any (e.g., "loot_box", "age_rating", "data_collection", "ai_content") or null
- time_hint: any mentioned deadline or timeline

Article:
Title: {title}
Source: {source}
Description: {description}

Return ONLY valid JSON."""


@dataclass
class ClassificationResult:
    category: str
    event: LegalEvent


def _safe_enum(enum_cls, value, default):
    try:
        return enum_cls(value)
    except (ValueError, KeyError):
        return default


def classify_article(article: RawArticle, llm: LLMProvider) -> ClassificationResult:
    """Classify an article using LLM. Returns defaults on failure."""
    prompt = CLASSIFIER_PROMPT.format(
        categories=", ".join(sorted(VALID_CATEGORIES)),
        jurisdictions=", ".join(j.value for j in Jurisdiction),
        event_types=", ".join(e.value for e in EventType),
        phases=", ".join(p.value for p in RegulatoryPhase),
        title=article.title,
        source=article.source,
        description=article.description[:2000],
    )

    try:
        data = llm.generate_json(prompt, system=CLASSIFIER_SYSTEM)
        category = data.get("category", "ETC")
        if category not in VALID_CATEGORIES:
            category = "ETC"

        event = LegalEvent(
            jurisdiction=_safe_enum(Jurisdiction, data.get("jurisdiction", "Global"), Jurisdiction.GLOBAL),
            event_type=_safe_enum(EventType, data.get("event_type", "other"), EventType.OTHER),
            regulatory_phase=_safe_enum(RegulatoryPhase, data.get("regulatory_phase", "proposed"), RegulatoryPhase.PROPOSED),
            actors=data.get("actors", []),
            object=data.get("object", ""),
            action=data.get("action", ""),
            game_mechanic=data.get("game_mechanic"),
            time_hint=data.get("time_hint", ""),
        )
        return ClassificationResult(category=category, event=event)

    except Exception as e:
        logger.warning("Classification failed for '%s': %s", article.title, e)
        return ClassificationResult(
            category="ETC",
            event=LegalEvent(
                jurisdiction=Jurisdiction.GLOBAL,
                event_type=EventType.OTHER,
                regulatory_phase=RegulatoryPhase.PROPOSED,
                actors=[], object="", action="",
                game_mechanic=None, time_hint="",
            ),
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_classifier.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add pipeline/intelligence/classifier.py tests/test_classifier.py tests/fixtures/sample_classifier_response.json
git commit -m "feat: AI classifier for category, jurisdiction, and regulatory phase"
```

---

### Task 13: AI Summarizer (Korean)

**Files:**
- Create: `pipeline/intelligence/summarizer.py`
- Create: `tests/test_summarizer.py`

- [ ] **Step 1: Write tests for summarizer**

```python
# tests/test_summarizer.py
from unittest.mock import MagicMock
from pipeline.intelligence.summarizer import summarize_article
from pipeline.sources.rss import RawArticle
from pipeline.llm.base import LLMProvider


def _article() -> RawArticle:
    return RawArticle(
        title="EU Enacts Loot Box Regulation",
        url="https://example.com/eu-lootbox",
        source="GamesIndustry.biz",
        description="The European Union has enacted new regulations.",
        pub_date="2026-03-23",
    )


def test_summarize_returns_three_lines():
    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.generate_json.return_value = {
        "summary_ko": [
            "EU가 루트박스 규제를 확정했다.",
            "2026년 3분기부터 시행 예정.",
            "게임사 공시 의무화.",
        ]
    }
    result = summarize_article(_article(), mock_llm)
    assert len(result) == 3
    assert "루트박스" in result[0]


def test_summarize_fallback_on_failure():
    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.generate_json.side_effect = Exception("LLM failed")
    result = summarize_article(_article(), mock_llm)
    assert len(result) == 1
    assert result[0] == "EU Enacts Loot Box Regulation"


def test_summarize_handles_non_list_response():
    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.generate_json.return_value = {"summary_ko": "단일 문장 요약"}
    result = summarize_article(_article(), mock_llm)
    assert isinstance(result, list)
    assert len(result) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_summarizer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement summarizer.py**

```python
# pipeline/intelligence/summarizer.py
from __future__ import annotations

import logging

from pipeline.llm.base import LLMProvider
from pipeline.sources.rss import RawArticle

logger = logging.getLogger(__name__)

SUMMARIZER_SYSTEM = "You are a legal analyst specializing in the game industry. Summarize in Korean."

SUMMARIZER_PROMPT = """다음 기사를 게임 산업 법률/규제 관점에서 한국어 3줄 요약해주세요.

제목: {title}
출처: {source}
내용: {description}

Return JSON: {{"summary_ko": ["첫째 줄", "둘째 줄", "셋째 줄"]}}"""


def summarize_article(article: RawArticle, llm: LLMProvider) -> list[str]:
    """Summarize an article in Korean. Returns [title] as fallback."""
    prompt = SUMMARIZER_PROMPT.format(
        title=article.title,
        source=article.source,
        description=article.description[:3000],
    )

    try:
        data = llm.generate_json(prompt, system=SUMMARIZER_SYSTEM)
        summary = data.get("summary_ko", [])
        if isinstance(summary, str):
            summary = [summary]
        if not summary:
            return [article.title]
        return summary
    except Exception as e:
        logger.warning("Summarization failed for '%s': %s", article.title, e)
        return [article.title]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_summarizer.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/intelligence/summarizer.py tests/test_summarizer.py
git commit -m "feat: Korean summarizer with LLM fallback"
```

---

## Chunk 5: Store + Render + Deliver

### Task 14: BriefingNode Assembly

**Files:**
- Create: `pipeline/store/nodes.py`
- Create: `tests/test_nodes.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_nodes.py
from pipeline.store.nodes import assemble_node
from pipeline.sources.rss import RawArticle
from pipeline.intelligence.classifier import ClassificationResult
from pipeline.models import LegalEvent, Jurisdiction, EventType, RegulatoryPhase


def _article():
    return RawArticle(title="Test Article", url="https://example.com/test",
                     source="TestFeed", description="desc", pub_date="2026-03-23")


def _classification():
    return ClassificationResult(
        category="IP",
        event=LegalEvent(
            jurisdiction=Jurisdiction.US, event_type=EventType.LITIGATION,
            regulatory_phase=RegulatoryPhase.LITIGATION,
            actors=["Nintendo"], object="patent", action="filed suit",
            game_mechanic=None, time_hint="",
        ),
    )


def test_assemble_node():
    node = assemble_node(
        article=_article(),
        classification=_classification(),
        summary_ko=["요약 1", "요약 2", "요약 3"],
    )
    assert node.title == "Test Article"
    assert node.category == "IP"
    assert node.event.jurisdiction == Jurisdiction.US
    assert len(node.summary_ko) == 3
    assert isinstance(node.event_key, str)
    assert len(node.event_key) == 16
    assert node.is_primary is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_nodes.py -v`
Expected: FAIL

- [ ] **Step 3: Implement nodes.py**

```python
# pipeline/store/nodes.py
from __future__ import annotations

from pipeline.intelligence.classifier import ClassificationResult
from pipeline.intelligence.dedup import compute_event_key
from pipeline.models import BriefingNode
from pipeline.sources.rss import RawArticle


def assemble_node(
    article: RawArticle,
    classification: ClassificationResult,
    summary_ko: list[str],
) -> BriefingNode:
    """Assemble a BriefingNode from raw article + AI outputs."""
    event = classification.event
    event_key = compute_event_key(
        jurisdiction=event.jurisdiction.value,
        actors=event.actors,
        object_=event.object,
        action=event.action,
    )
    return BriefingNode(
        title=article.title,
        url=article.url,
        source=article.source,
        pub_date=article.pub_date,
        category=classification.category,
        summary_ko=summary_ko,
        event=event,
        event_key=event_key,
        is_primary=True,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_nodes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/store/nodes.py tests/test_nodes.py
git commit -m "feat: BriefingNode assembly from raw article + AI outputs"
```

---

### Task 15: JSON Daily Storage

**Files:**
- Create: `pipeline/store/daily.py`
- Create: `tests/test_daily.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_daily.py
import json
import os
import tempfile
from pipeline.store.daily import save_daily, load_daily
from pipeline.models import (
    BriefingNode, LegalEvent, Jurisdiction, EventType, RegulatoryPhase,
)


def _sample_node():
    return BriefingNode(
        title="Test", url="https://example.com", source="Test", pub_date="2026-03-23",
        category="IP", summary_ko=["요약"],
        event=LegalEvent(jurisdiction=Jurisdiction.US, event_type=EventType.LITIGATION,
                        regulatory_phase=RegulatoryPhase.LITIGATION, actors=["Test"],
                        object="test", action="tested", game_mechanic=None, time_hint=""),
        event_key="abc123", is_primary=True,
    )


def test_save_and_load_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        nodes = [_sample_node()]
        save_daily(nodes, "2026-03-23", data_dir=tmpdir)

        path = os.path.join(tmpdir, "2026-03-23.json")
        assert os.path.exists(path)

        loaded = load_daily("2026-03-23", data_dir=tmpdir)
        assert len(loaded) == 1
        assert loaded[0].title == "Test"
        assert loaded[0].event.jurisdiction == Jurisdiction.US


def test_load_missing_date_returns_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        loaded = load_daily("2099-01-01", data_dir=tmpdir)
        assert loaded == []


def test_save_creates_valid_json():
    with tempfile.TemporaryDirectory() as tmpdir:
        save_daily([_sample_node()], "2026-03-23", data_dir=tmpdir)
        path = os.path.join(tmpdir, "2026-03-23.json")
        with open(path) as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert data[0]["title"] == "Test"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_daily.py -v`
Expected: FAIL

- [ ] **Step 3: Implement daily.py**

```python
# pipeline/store/daily.py
from __future__ import annotations

import json
import os
import logging

from pipeline.models import BriefingNode, briefing_node_to_dict, dict_to_briefing_node

logger = logging.getLogger(__name__)


def save_daily(
    nodes: list[BriefingNode],
    date: str,
    data_dir: str = "output/data/daily",
) -> str:
    """Save briefing nodes to output/data/daily/{date}.json. Returns file path."""
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, f"{date}.json")
    data = [briefing_node_to_dict(n) for n in nodes]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("Saved %d nodes to %s", len(nodes), path)
    return path


def load_daily(
    date: str,
    data_dir: str = "output/data/daily",
) -> list[BriefingNode]:
    """Load briefing nodes from a daily JSON file. Returns empty list if missing."""
    path = os.path.join(data_dir, f"{date}.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [dict_to_briefing_node(d) for d in data]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_daily.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/store/daily.py tests/test_daily.py
git commit -m "feat: daily JSON storage for BriefingNodes"
```

---

### Task 16: Dedup Index Persistence

**Files:**
- Create: `pipeline/store/dedup_index.py`
- Create: `tests/test_dedup_index.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_dedup_index.py
import os
import tempfile
from pipeline.store.dedup_index import load_dedup_index, save_dedup_index, prune_old_entries
from pipeline.intelligence.dedup import DedupIndex, DedupEntry


def test_save_and_load_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "dedup_index.json")
        index = DedupIndex(entries=[
            DedupEntry(event_key="key1", url_hash="hash1", date="2026-03-23"),
        ])
        save_dedup_index(index, path)
        loaded = load_dedup_index(path)
        assert len(loaded.entries) == 1
        assert loaded.entries[0].event_key == "key1"


def test_load_missing_returns_empty():
    loaded = load_dedup_index("/nonexistent/path.json")
    assert len(loaded.entries) == 0


def test_prune_old_entries():
    entries = [
        DedupEntry(event_key="old", url_hash="h1", date="2026-01-01"),
        DedupEntry(event_key="recent", url_hash="h2", date="2026-03-20"),
    ]
    index = DedupIndex(entries=entries, retention_days=30)
    pruned = prune_old_entries(index, today="2026-03-28")
    assert len(pruned.entries) == 1
    assert pruned.entries[0].event_key == "recent"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_dedup_index.py -v`
Expected: FAIL

- [ ] **Step 3: Implement dedup_index.py**

```python
# pipeline/store/dedup_index.py
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta

from pipeline.intelligence.dedup import DedupIndex, DedupEntry

logger = logging.getLogger(__name__)


def load_dedup_index(path: str) -> DedupIndex:
    """Load dedup index from JSON file. Returns empty index if missing."""
    if not os.path.exists(path):
        return DedupIndex()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    entries = [
        DedupEntry(event_key=e["event_key"], url_hash=e["url_hash"], date=e["date"])
        for e in data.get("entries", [])
    ]
    return DedupIndex(
        entries=entries,
        schema_version=data.get("schema_version", 1),
        retention_days=data.get("retention_days", 30),
    )


def save_dedup_index(index: DedupIndex, path: str) -> None:
    """Save dedup index to JSON file."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    data = {
        "schema_version": index.schema_version,
        "retention_days": index.retention_days,
        "entries": [
            {"event_key": e.event_key, "url_hash": e.url_hash, "date": e.date}
            for e in index.entries
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.info("Saved dedup index with %d entries", len(index.entries))


def prune_old_entries(index: DedupIndex, today: str | None = None) -> DedupIndex:
    """Remove entries older than retention_days."""
    if today is None:
        today = datetime.now().strftime("%Y-%m-%d")
    cutoff = datetime.strptime(today, "%Y-%m-%d") - timedelta(days=index.retention_days)
    kept = [e for e in index.entries if datetime.strptime(e.date, "%Y-%m-%d") >= cutoff]
    pruned = len(index.entries) - len(kept)
    if pruned:
        logger.info("Pruned %d old dedup entries", pruned)
    return DedupIndex(entries=kept, schema_version=index.schema_version,
                     retention_days=index.retention_days)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dedup_index.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/store/dedup_index.py tests/test_dedup_index.py
git commit -m "feat: dedup index persistence with JSON and pruning"
```

---

### Task 17: Query Interface

**Files:**
- Create: `pipeline/store/query.py`
- Create: `tests/test_query.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_query.py
import tempfile
from pipeline.store.query import query_nodes, list_briefing_dates
from pipeline.store.daily import save_daily
from pipeline.models import (
    BriefingNode, LegalEvent, Jurisdiction, EventType, RegulatoryPhase,
)


def _node(title: str, jurisdiction: Jurisdiction, category: str, pub_date: str):
    return BriefingNode(
        title=title, url=f"https://example.com/{title}", source="Test",
        pub_date=pub_date, category=category, summary_ko=["요약"],
        event=LegalEvent(jurisdiction=jurisdiction, event_type=EventType.LEGISLATION,
                        regulatory_phase=RegulatoryPhase.ENACTED, actors=["Test"],
                        object="test", action="tested", game_mechanic=None, time_hint=""),
        event_key=f"key_{title}", is_primary=True,
    )


def test_query_all():
    with tempfile.TemporaryDirectory() as tmpdir:
        save_daily([_node("A", Jurisdiction.EU, "IP", "2026-03-23")], "2026-03-23", tmpdir)
        save_daily([_node("B", Jurisdiction.KR, "ETC", "2026-03-25")], "2026-03-25", tmpdir)
        result = query_nodes(data_dir=tmpdir)
        assert len(result) == 2
        # Newest first
        assert result[0].title == "B"


def test_query_by_jurisdiction():
    with tempfile.TemporaryDirectory() as tmpdir:
        save_daily([
            _node("EU Article", Jurisdiction.EU, "IP", "2026-03-23"),
            _node("KR Article", Jurisdiction.KR, "IP", "2026-03-23"),
        ], "2026-03-23", tmpdir)
        result = query_nodes(data_dir=tmpdir, jurisdiction=Jurisdiction.EU)
        assert len(result) == 1
        assert result[0].title == "EU Article"


def test_query_by_category():
    with tempfile.TemporaryDirectory() as tmpdir:
        save_daily([
            _node("IP Article", Jurisdiction.US, "IP", "2026-03-23"),
            _node("ETC Article", Jurisdiction.US, "ETC", "2026-03-23"),
        ], "2026-03-23", tmpdir)
        result = query_nodes(data_dir=tmpdir, category="IP")
        assert len(result) == 1


def test_list_briefing_dates():
    with tempfile.TemporaryDirectory() as tmpdir:
        save_daily([_node("A", Jurisdiction.US, "IP", "2026-03-23")], "2026-03-23", tmpdir)
        save_daily([_node("B", Jurisdiction.US, "IP", "2026-03-25")], "2026-03-25", tmpdir)
        dates = list_briefing_dates(data_dir=tmpdir)
        assert dates == ["2026-03-25", "2026-03-23"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_query.py -v`
Expected: FAIL

- [ ] **Step 3: Implement query.py**

```python
# pipeline/store/query.py
from __future__ import annotations

import glob
import os

from pipeline.models import BriefingNode, Jurisdiction, RegulatoryPhase
from pipeline.store.daily import load_daily


def list_briefing_dates(data_dir: str = "output/data/daily") -> list[str]:
    """Return sorted list of available briefing dates, newest first."""
    pattern = os.path.join(data_dir, "*.json")
    files = glob.glob(pattern)
    dates = [os.path.splitext(os.path.basename(f))[0] for f in files]
    return sorted(dates, reverse=True)


def query_nodes(
    data_dir: str = "output/data/daily",
    jurisdiction: Jurisdiction | None = None,
    category: str | None = None,
    phase: RegulatoryPhase | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[BriefingNode]:
    """Load and filter BriefingNodes from daily JSON files. Returns newest first."""
    dates = list_briefing_dates(data_dir)
    all_nodes: list[BriefingNode] = []

    for date in dates:
        if date_from and date < date_from:
            continue
        if date_to and date > date_to:
            continue
        nodes = load_daily(date, data_dir)
        for node in nodes:
            if jurisdiction and node.event.jurisdiction != jurisdiction:
                continue
            if category and node.category != category:
                continue
            if phase and node.event.regulatory_phase != phase:
                continue
            all_nodes.append(node)

    return all_nodes
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_query.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/store/query.py tests/test_query.py
git commit -m "feat: query interface for filtering BriefingNodes"
```

---

### Task 18: Jinja2 Site Renderer

**Files:**
- Create: `pipeline/render/site.py`
- Create: `templates/index.html`
- Create: `templates/archive.html`
- Create: `static/style.css`
- Create: `tests/test_site.py`

- [ ] **Step 1: Create templates**

`templates/index.html`:
```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Game Legal Briefing — {{ date }}</title>
  <link rel="stylesheet" href="{{ base_url }}/static/style.css">
</head>
<body>
  <header>
    <h1>Game Legal Briefing</h1>
    <nav>
      <span class="date">{{ date }}</span>
      <a href="{{ base_url }}/archive/">Archive</a>
    </nav>
  </header>
  <main>
    {% for node in nodes %}
    <article class="briefing-item">
      <div class="meta">
        <span class="category chip">{{ node.category }}</span>
        <span class="jurisdiction chip">{{ node.event.jurisdiction.value }}</span>
        <span class="phase badge">{{ node.event.regulatory_phase.value }}</span>
      </div>
      <h2><a href="{{ node.url }}" target="_blank">{{ node.title }}</a></h2>
      <p class="source">{{ node.source }} · {{ node.pub_date }}</p>
      <ul class="summary">
        {% for line in node.summary_ko %}
        <li>{{ line }}</li>
        {% endfor %}
      </ul>
      <div class="event-meta">
        {% if node.event.actors %}
        <span class="actors">{{ node.event.actors | join(", ") }}</span>
        {% endif %}
        {% if node.event.game_mechanic %}
        <span class="mechanic chip">{{ node.event.game_mechanic }}</span>
        {% endif %}
      </div>
    </article>
    {% endfor %}
  </main>
  <footer>
    <p>Game Legal Briefing — Open Source Game Industry Regulatory Intelligence</p>
  </footer>
</body>
</html>
```

`templates/archive.html`:
```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Archive — Game Legal Briefing</title>
  <link rel="stylesheet" href="{{ base_url }}/static/style.css">
</head>
<body>
  <header>
    <h1>Game Legal Briefing</h1>
    <nav><a href="{{ base_url }}/">Latest</a> · Archive</nav>
  </header>
  <main>
    <h2>Archive</h2>
    <ul class="archive-list">
      {% for entry in entries %}
      <li>
        <a href="{{ base_url }}/archive/{{ entry.date }}.html">{{ entry.date }}</a>
        <span class="count">{{ entry.count }}건</span>
      </li>
      {% endfor %}
    </ul>
  </main>
</body>
</html>
```

`static/style.css`:
```css
:root {
  --bg: #FAFAF8;
  --text: #1a1a1a;
  --muted: #666;
  --border: #e0e0e0;
  --accent: #2563eb;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--bg); color: var(--text);
  max-width: 720px; margin: 0 auto; padding: 2rem 1rem;
  line-height: 1.6;
}
header { border-bottom: 1px solid var(--border); padding-bottom: 1rem; margin-bottom: 2rem; }
header h1 { font-size: 1.5rem; }
header nav { margin-top: 0.5rem; color: var(--muted); }
header nav a { color: var(--accent); text-decoration: none; }
.briefing-item { margin-bottom: 2rem; padding-bottom: 1.5rem; border-bottom: 1px solid var(--border); }
.briefing-item h2 { font-size: 1.1rem; margin: 0.5rem 0; }
.briefing-item h2 a { color: var(--text); text-decoration: none; }
.briefing-item h2 a:hover { color: var(--accent); }
.source { color: var(--muted); font-size: 0.85rem; }
.summary { margin: 0.75rem 0; padding-left: 1.2rem; }
.summary li { margin-bottom: 0.25rem; font-size: 0.95rem; }
.chip {
  display: inline-block; padding: 0.15rem 0.5rem; border-radius: 3px;
  font-size: 0.75rem; font-weight: 600; background: #f0f0f0; margin-right: 0.25rem;
}
.badge {
  display: inline-block; padding: 0.15rem 0.5rem; border-radius: 3px;
  font-size: 0.75rem; background: #e8f4fd; color: #1e40af;
}
.event-meta { font-size: 0.85rem; color: var(--muted); margin-top: 0.5rem; }
.archive-list { list-style: none; }
.archive-list li { padding: 0.5rem 0; border-bottom: 1px solid var(--border); }
.archive-list a { color: var(--accent); text-decoration: none; font-weight: 500; }
.count { color: var(--muted); margin-left: 0.5rem; font-size: 0.85rem; }
footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border); color: var(--muted); font-size: 0.85rem; }
```

- [ ] **Step 2: Write tests for site renderer**

```python
# tests/test_site.py
import os
import tempfile
from pipeline.render.site import render_index, render_archive
from pipeline.models import (
    BriefingNode, LegalEvent, Jurisdiction, EventType, RegulatoryPhase,
)


def _node(title="Test"):
    return BriefingNode(
        title=title, url="https://example.com", source="Test", pub_date="2026-03-23",
        category="IP", summary_ko=["요약 1", "요약 2"],
        event=LegalEvent(jurisdiction=Jurisdiction.US, event_type=EventType.LITIGATION,
                        regulatory_phase=RegulatoryPhase.ENACTED, actors=["Nintendo"],
                        object="patent", action="filed", game_mechanic="loot_box", time_hint=""),
        event_key="key1", is_primary=True,
    )


def test_render_index_creates_html():
    with tempfile.TemporaryDirectory() as tmpdir:
        template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
        path = render_index(
            nodes=[_node()], date="2026-03-23",
            output_dir=tmpdir, template_dir=template_dir, base_url="",
        )
        assert os.path.exists(path)
        with open(path) as f:
            html = f.read()
        assert "Game Legal Briefing" in html
        assert "Test" in html
        assert "IP" in html


def test_render_archive_creates_html():
    with tempfile.TemporaryDirectory() as tmpdir:
        template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
        entries = [{"date": "2026-03-23", "count": 5}, {"date": "2026-03-20", "count": 3}]
        path = render_archive(
            entries=entries, output_dir=tmpdir,
            template_dir=template_dir, base_url="",
        )
        assert os.path.exists(path)
        with open(path) as f:
            html = f.read()
        assert "2026-03-23" in html
        assert "5건" in html
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_site.py -v`
Expected: FAIL

- [ ] **Step 4: Implement site.py**

```python
# pipeline/render/site.py
from __future__ import annotations

import os
import logging
import shutil

from jinja2 import Environment, FileSystemLoader

from pipeline.models import BriefingNode

logger = logging.getLogger(__name__)


def _get_env(template_dir: str) -> Environment:
    return Environment(loader=FileSystemLoader(template_dir), autoescape=True)


def render_index(
    nodes: list[BriefingNode],
    date: str,
    output_dir: str = "output",
    template_dir: str = "templates",
    base_url: str = "",
) -> str:
    """Render the main index.html with today's briefing."""
    env = _get_env(template_dir)
    template = env.get_template("index.html")
    html = template.render(nodes=nodes, date=date, base_url=base_url)

    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    # Also save as archive/{date}.html
    archive_dir = os.path.join(output_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)
    archive_path = os.path.join(archive_dir, f"{date}.html")
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info("Rendered index.html and archive/%s.html", date)
    return path


def render_archive(
    entries: list[dict],
    output_dir: str = "output",
    template_dir: str = "templates",
    base_url: str = "",
) -> str:
    """Render the archive listing page."""
    env = _get_env(template_dir)
    template = env.get_template("archive.html")
    html = template.render(entries=entries, base_url=base_url)

    archive_dir = os.path.join(output_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)
    path = os.path.join(archive_dir, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info("Rendered archive/index.html with %d entries", len(entries))
    return path


def copy_static(output_dir: str = "output", static_dir: str = "static") -> None:
    """Copy static assets to output directory."""
    dest = os.path.join(output_dir, "static")
    if os.path.exists(dest):
        shutil.rmtree(dest)
    if os.path.exists(static_dir):
        shutil.copytree(static_dir, dest)
        logger.info("Copied static assets to %s", dest)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_site.py -v`
Expected: All 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add pipeline/render/site.py templates/ static/style.css tests/test_site.py
git commit -m "feat: Jinja2 site renderer with index, archive, and CSS"
```

---

### Task 18b: Article Detail Page

**Files:**
- Create: `templates/article.html`
- Modify: `pipeline/render/site.py` — add `render_article_pages()`

- [ ] **Step 1: Create article.html template**

`templates/article.html`:
```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ node.title }} — Game Legal Briefing</title>
  <link rel="stylesheet" href="{{ base_url }}/static/style.css">
</head>
<body>
  <header>
    <h1><a href="{{ base_url }}/" style="text-decoration: none; color: inherit;">Game Legal Briefing</a></h1>
    <nav><a href="{{ base_url }}/">Latest</a> · <a href="{{ base_url }}/archive/">Archive</a></nav>
  </header>
  <main>
    <article class="briefing-item">
      <div class="meta">
        <span class="category chip">{{ node.category }}</span>
        <span class="jurisdiction chip">{{ node.event.jurisdiction.value }}</span>
        <span class="phase badge">{{ node.event.regulatory_phase.value }}</span>
      </div>
      <h2><a href="{{ node.url }}" target="_blank">{{ node.title }}</a></h2>
      <p class="source">{{ node.source }} · {{ node.pub_date }}</p>
      <ul class="summary">
        {% for line in node.summary_ko %}
        <li>{{ line }}</li>
        {% endfor %}
      </ul>
      <div class="event-meta">
        <p><strong>Event Type:</strong> {{ node.event.event_type.value }}</p>
        {% if node.event.actors %}<p><strong>Actors:</strong> {{ node.event.actors | join(", ") }}</p>{% endif %}
        {% if node.event.object %}<p><strong>Object:</strong> {{ node.event.object }}</p>{% endif %}
        {% if node.event.action %}<p><strong>Action:</strong> {{ node.event.action }}</p>{% endif %}
        {% if node.event.game_mechanic %}<p><strong>Game Mechanic:</strong> {{ node.event.game_mechanic }}</p>{% endif %}
        {% if node.event.time_hint %}<p><strong>Timeline:</strong> {{ node.event.time_hint }}</p>{% endif %}
      </div>
    </article>
  </main>
</body>
</html>
```

- [ ] **Step 2: Write test for render_article_pages**

Add to `tests/test_site.py`:

```python
def test_render_article_pages_creates_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
        from pipeline.render.site import render_article_pages
        render_article_pages(
            nodes=[_node()], output_dir=tmpdir,
            template_dir=template_dir, base_url="",
        )
        path = os.path.join(tmpdir, "article", "key1.html")
        assert os.path.exists(path)
        with open(path) as f:
            html = f.read()
        assert "Test" in html
```

- [ ] **Step 3: Add render_article_pages to site.py**

Append to `pipeline/render/site.py`:

```python
def render_article_pages(
    nodes: list[BriefingNode],
    output_dir: str = "output",
    template_dir: str = "templates",
    base_url: str = "",
) -> None:
    """Render individual article detail pages at output/article/{event_key}.html."""
    env = _get_env(template_dir)
    template = env.get_template("article.html")
    article_dir = os.path.join(output_dir, "article")
    os.makedirs(article_dir, exist_ok=True)
    for node in nodes:
        html = template.render(node=node, base_url=base_url)
        path = os.path.join(article_dir, f"{node.event_key}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
    logger.info("Rendered %d article detail pages", len(nodes))
```

- [ ] **Step 3: Commit**

```bash
git add templates/article.html pipeline/render/site.py
git commit -m "feat: article detail page template and renderer"
```

---

### Task 19: Email Renderer + Mailer

**Files:**
- Create: `pipeline/render/email.py`
- Create: `templates/email/briefing.html`
- Create: `pipeline/deliver/mailer.py`
- Create: `tests/test_email.py`
- Create: `tests/test_mailer.py`

- [ ] **Step 1: Create email template**

`templates/email/briefing.html`:
```html
<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #FAFAF8; color: #1a1a1a; line-height: 1.6;">
  <h1 style="font-size: 20px; border-bottom: 1px solid #e0e0e0; padding-bottom: 10px;">Game Legal Briefing — {{ date }}</h1>
  {% for node in nodes %}
  <div style="margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid #e0e0e0;">
    <div style="margin-bottom: 4px;">
      <span style="display: inline-block; padding: 2px 8px; background: #f0f0f0; border-radius: 3px; font-size: 12px; font-weight: 600;">{{ node.category }}</span>
      <span style="display: inline-block; padding: 2px 8px; background: #f0f0f0; border-radius: 3px; font-size: 12px;">{{ node.event.jurisdiction.value }}</span>
      <span style="display: inline-block; padding: 2px 8px; background: #e8f4fd; color: #1e40af; border-radius: 3px; font-size: 12px;">{{ node.event.regulatory_phase.value }}</span>
    </div>
    <h2 style="font-size: 16px; margin: 6px 0;"><a href="{{ node.url }}" style="color: #1a1a1a; text-decoration: none;">{{ node.title }}</a></h2>
    <p style="font-size: 13px; color: #666;">{{ node.source }} · {{ node.pub_date }}</p>
    <ul style="margin: 8px 0; padding-left: 20px;">
      {% for line in node.summary_ko %}
      <li style="margin-bottom: 4px; font-size: 14px;">{{ line }}</li>
      {% endfor %}
    </ul>
  </div>
  {% endfor %}
  <p style="font-size: 12px; color: #999; margin-top: 20px;">Game Legal Briefing — Open Source Game Industry Regulatory Intelligence</p>
</body>
</html>
```

- [ ] **Step 2: Write tests for email rendering**

```python
# tests/test_email.py
import os
from pipeline.render.email import render_email
from pipeline.models import (
    BriefingNode, LegalEvent, Jurisdiction, EventType, RegulatoryPhase,
)


def _node():
    return BriefingNode(
        title="Test", url="https://example.com", source="Test", pub_date="2026-03-23",
        category="IP", summary_ko=["요약"],
        event=LegalEvent(jurisdiction=Jurisdiction.US, event_type=EventType.LITIGATION,
                        regulatory_phase=RegulatoryPhase.ENACTED, actors=["Test"],
                        object="test", action="tested", game_mechanic=None, time_hint=""),
        event_key="key1", is_primary=True,
    )


def test_render_email_returns_html():
    template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
    html = render_email(nodes=[_node()], date="2026-03-23", template_dir=template_dir)
    assert "Game Legal Briefing" in html
    assert "Test" in html
```

- [ ] **Step 3: Write tests for mailer**

```python
# tests/test_mailer.py
from unittest.mock import patch, MagicMock
from pipeline.deliver.mailer import send_briefing_email


def test_send_email_calls_smtp():
    with patch("pipeline.deliver.mailer.smtplib.SMTP_SSL") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_briefing_email(
            html_body="<h1>Test</h1>",
            subject="[Game Legal Briefing] 2026-03-23",
            smtp_user="sender@gmail.com",
            smtp_pass="password",
            recipients=["a@example.com", "b@example.com"],
        )
        assert mock_smtp.sendmail.called or mock_smtp.send_message.called


def test_send_email_empty_recipients_skips():
    with patch("pipeline.deliver.mailer.smtplib.SMTP_SSL") as mock_smtp_cls:
        send_briefing_email(
            html_body="<h1>Test</h1>",
            subject="Test",
            smtp_user="sender@gmail.com",
            smtp_pass="password",
            recipients=[],
        )
        mock_smtp_cls.assert_not_called()
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python -m pytest tests/test_email.py tests/test_mailer.py -v`
Expected: FAIL

- [ ] **Step 5: Implement email.py**

```python
# pipeline/render/email.py
from __future__ import annotations

import logging

from jinja2 import Environment, FileSystemLoader

from pipeline.models import BriefingNode

logger = logging.getLogger(__name__)


def render_email(
    nodes: list[BriefingNode],
    date: str,
    template_dir: str = "templates",
) -> str:
    """Render briefing email as HTML string with inline CSS."""
    env = Environment(loader=FileSystemLoader(template_dir), autoescape=True)
    template = env.get_template("email/briefing.html")
    html = template.render(nodes=nodes, date=date)

    # Inline CSS via premailer (email clients strip <style> tags)
    from premailer import transform
    html = transform(html)

    return html
```

- [ ] **Step 6: Implement mailer.py**

```python
# pipeline/deliver/mailer.py
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_briefing_email(
    html_body: str,
    subject: str,
    smtp_user: str,
    smtp_pass: str,
    recipients: list[str],
) -> None:
    """Send briefing email via Gmail SMTP."""
    if not recipients:
        logger.info("No recipients, skipping email delivery")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        logger.info("Email sent to %d recipients", len(recipients))
    except Exception as e:
        logger.error("Email delivery failed: %s", e)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_email.py tests/test_mailer.py -v`
Expected: All 3 tests PASS

- [ ] **Step 8: Commit**

```bash
git add pipeline/render/email.py pipeline/deliver/mailer.py templates/email/briefing.html
git add tests/test_email.py tests/test_mailer.py
git commit -m "feat: email renderer with inline CSS and Gmail SMTP mailer"
```

---

## Chunk 6: Admin + Orchestrator + CI/CD

### Task 20: Google Sheets Admin Sync

**Files:**
- Create: `pipeline/admin/sheets.py`
- Create: `tests/test_sheets.py`

- [ ] **Step 1: Write tests for Sheets sync**

```python
# tests/test_sheets.py
from unittest.mock import MagicMock, patch
from pipeline.admin.sheets import sync_to_sheets, format_row
from pipeline.models import (
    BriefingNode, LegalEvent, Jurisdiction, EventType, RegulatoryPhase,
)


def _node():
    return BriefingNode(
        title="Test Article", url="https://example.com", source="TestFeed",
        pub_date="2026-03-23", category="IP", summary_ko=["요약 1", "요약 2"],
        event=LegalEvent(jurisdiction=Jurisdiction.US, event_type=EventType.LITIGATION,
                        regulatory_phase=RegulatoryPhase.ENACTED, actors=["Nintendo"],
                        object="patent", action="filed", game_mechanic=None, time_hint=""),
        event_key="key1", is_primary=True,
    )


def test_format_row():
    row = format_row(_node())
    assert row[0] == "2026-03-23"        # date
    assert row[1] == "Test Article"       # title
    assert row[2] == "https://example.com"  # url
    assert row[3] == "TestFeed"           # source
    assert row[4] == "IP"                 # category
    assert row[5] == "US"                 # jurisdiction
    assert row[6] == "enacted"            # phase
    assert "요약 1" in row[7]             # summary_ko
    assert row[8] == "key1"              # event_key
    assert row[9] == "published"          # status


def test_sync_to_sheets_appends_rows():
    mock_sheet = MagicMock()
    with patch("pipeline.admin.sheets._get_worksheet", return_value=mock_sheet):
        sync_to_sheets([_node()], credentials_json="{}", spreadsheet_id="test-id")
        mock_sheet.append_rows.assert_called_once()
        rows = mock_sheet.append_rows.call_args[0][0]
        assert len(rows) == 1


def test_sync_to_sheets_skips_on_missing_credentials():
    sync_to_sheets([_node()], credentials_json=None, spreadsheet_id=None)
    # Should not raise, just skip
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sheets.py -v`
Expected: FAIL

- [ ] **Step 3: Implement sheets.py**

```python
# pipeline/admin/sheets.py
from __future__ import annotations

import json
import logging

from pipeline.models import BriefingNode

logger = logging.getLogger(__name__)

SHEET_HEADERS = ["date", "title", "url", "source", "category", "jurisdiction",
                 "phase", "summary_ko", "event_key", "status"]


def format_row(node: BriefingNode) -> list[str]:
    """Format a BriefingNode as a spreadsheet row."""
    return [
        node.pub_date,
        node.title,
        node.url,
        node.source,
        node.category,
        node.event.jurisdiction.value,
        node.event.regulatory_phase.value,
        " | ".join(node.summary_ko),
        node.event_key,
        "published",
    ]


def _get_worksheet(credentials_json: str, spreadsheet_id: str):
    """Authenticate and return the first worksheet."""
    import gspread
    from google.oauth2.service_account import Credentials

    creds_data = json.loads(credentials_json)
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(creds_data, scopes=scopes)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(spreadsheet_id)
    return spreadsheet.sheet1


def sync_to_sheets(
    nodes: list[BriefingNode],
    credentials_json: str | None,
    spreadsheet_id: str | None,
) -> None:
    """Append briefing nodes as rows to Google Sheet. Skips if credentials missing."""
    if not credentials_json or not spreadsheet_id:
        logger.info("Google Sheets credentials not configured, skipping sync")
        return

    try:
        sheet = _get_worksheet(credentials_json, spreadsheet_id)
        rows = [format_row(node) for node in nodes]
        sheet.append_rows(rows)
        logger.info("Synced %d rows to Google Sheets", len(rows))
    except Exception as e:
        logger.error("Google Sheets sync failed: %s", e)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_sheets.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/admin/sheets.py tests/test_sheets.py
git commit -m "feat: Google Sheets admin log sync"
```

---

### Task 21: CLI Orchestrator (main.py)

**Files:**
- Create: `main.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_main.py
from unittest.mock import patch, MagicMock
import tempfile
import os


def test_main_dry_run():
    """Test the pipeline runs end-to-end with mocked LLM and no real network."""
    from pipeline.sources.rss import RawArticle

    mock_articles = [
        RawArticle(title="EU Loot Box Regulation", url="https://example.com/1",
                  source="TestFeed", description="EU regulates loot boxes",
                  pub_date="2026-03-23"),
    ]

    mock_classification = {
        "category": "CONSUMER_MONETIZATION", "jurisdiction": "EU",
        "event_type": "legislation", "regulatory_phase": "enacted",
        "actors": ["EU Commission"], "object": "loot box",
        "action": "enacted regulation", "game_mechanic": "loot_box", "time_hint": "",
    }

    mock_summary = {"summary_ko": ["EU가 루트박스 규제 확정", "2026년 시행", "게임사 영향"]}

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("main.fetch_all_feeds", return_value=mock_articles), \
             patch("main.keyword_filter", return_value=mock_articles), \
             patch("main.select_top_articles", return_value=mock_articles), \
             patch("main.create_provider") as mock_create, \
             patch("main.send_briefing_email"), \
             patch("main.sync_to_sheets"), \
             patch("main.load_config") as mock_cfg:

            mock_llm = MagicMock()
            mock_llm.generate_json.side_effect = [
                mock_classification,  # classifier
                mock_summary,         # summarizer
            ]
            mock_create.return_value = mock_llm

            # Minimal config mock
            cfg = MagicMock()
            cfg.llm.provider = "gemini"
            cfg.llm.model = "gemini-3.1-flash-lite"
            cfg.google_api_key = "fake-key"
            cfg.anthropic_api_key = None
            cfg.sources.tier_a = []
            cfg.sources.tier_b = []
            cfg.pipeline.top_n = 10
            cfg.dedup.retention_days = 30
            cfg.site.base_url = ""
            cfg.email.subject_prefix = "[Test]"
            cfg.smtp_user = None
            cfg.smtp_pass = None
            cfg.recipients = []
            cfg.google_sheets_credentials = None
            cfg.google_sheets_id = None
            mock_cfg.return_value = cfg

            from main import run_pipeline
            run_pipeline(
                config_path="config.yaml",
                output_dir=tmpdir,
                template_dir=os.path.join(os.path.dirname(__file__), "..", "templates"),
            )

            # Verify JSON was created
            data_dir = os.path.join(tmpdir, "data", "daily")
            assert os.path.exists(data_dir)
            json_files = [f for f in os.listdir(data_dir) if f.endswith(".json")]
            assert len(json_files) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_main.py -v`
Expected: FAIL

- [ ] **Step 3: Implement main.py**

```python
# main.py
"""Game Legal Briefing — CLI Orchestrator."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

from pipeline.config import load_config
from pipeline.sources.rss import fetch_all_feeds
from pipeline.sources.filters import keyword_filter
from pipeline.intelligence.selector import select_top_articles
from pipeline.intelligence.classifier import classify_article
from pipeline.intelligence.summarizer import summarize_article
from pipeline.intelligence.dedup import deduplicate_articles
from pipeline.store.nodes import assemble_node
from pipeline.store.daily import save_daily, load_daily
from pipeline.store.dedup_index import load_dedup_index, save_dedup_index, prune_old_entries
from pipeline.store.query import list_briefing_dates
from pipeline.render.site import render_index, render_archive, render_article_pages, copy_static
from pipeline.render.email import render_email
from pipeline.deliver.mailer import send_briefing_email
from pipeline.admin.sheets import sync_to_sheets
from pipeline.llm import create_provider

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def run_pipeline(
    config_path: str = "config.yaml",
    output_dir: str = "output",
    template_dir: str = "templates",
    static_dir: str = "static",
    dry_run: bool = False,
) -> None:
    """Run the full briefing pipeline. dry_run skips email and Sheets sync."""
    load_dotenv()
    cfg = load_config(config_path)
    today = datetime.now().strftime("%Y-%m-%d")
    data_dir = os.path.join(output_dir, "data", "daily")
    dedup_path = os.path.join(output_dir, "data", "dedup_index.json")
    base_url = cfg.site.base_url

    logger.info("=== Game Legal Briefing — %s ===", today)
    if dry_run:
        logger.info("DRY RUN — email and Sheets sync will be skipped")

    # 1. Create LLM provider
    llm = create_provider(cfg.llm, google_api_key=cfg.google_api_key,
                          anthropic_api_key=cfg.anthropic_api_key)

    # 2. Fetch RSS feeds
    articles = fetch_all_feeds(tier_a=cfg.sources.tier_a, tier_b=cfg.sources.tier_b)

    # 3. Keyword pre-filter
    articles = keyword_filter(articles, keywords=cfg.pipeline.keywords)

    # 4. Deduplicate against existing index (stages 1 & 2: URL + topic tokens)
    dedup_index = load_dedup_index(dedup_path)
    dedup_index = prune_old_entries(dedup_index, today=today)
    articles = deduplicate_articles(articles, dedup_index)

    # 5. AI selection
    articles = select_top_articles(articles, llm, top_n=cfg.pipeline.top_n)

    # 6. Classify + summarize each article → BriefingNode
    nodes = []
    for article in articles:
        classification = classify_article(article, llm)
        summary_ko = summarize_article(article, llm)
        node = assemble_node(article, classification, summary_ko)
        nodes.append(node)

    # 7. Dedup stage 3: EventKey dedup (post-classification)
    existing_event_keys = {e.event_key for e in dedup_index.entries if e.event_key}
    seen_event_keys: set[str] = set()
    deduped_nodes = []
    for node in nodes:
        if node.event_key in existing_event_keys or node.event_key in seen_event_keys:
            logger.info("EventKey dedup: skipping '%s' (key: %s)", node.title, node.event_key)
            continue
        seen_event_keys.add(node.event_key)
        deduped_nodes.append(node)
    nodes = deduped_nodes
    logger.info("Produced %d BriefingNodes (after EventKey dedup)", len(nodes))

    # 8. Save daily JSON
    save_daily(nodes, today, data_dir=data_dir)

    # 9. Update dedup index
    from pipeline.intelligence.dedup import url_hash, DedupEntry
    for node in nodes:
        dedup_index.entries.append(
            DedupEntry(event_key=node.event_key, url_hash=url_hash(node.url), date=today)
        )
    save_dedup_index(dedup_index, dedup_path)

    # 10. Render static site
    render_index(nodes, today, output_dir=output_dir, template_dir=template_dir, base_url=base_url)
    dates = list_briefing_dates(data_dir=data_dir)
    archive_entries = []
    for d in dates:
        count = len(load_daily(d, data_dir=data_dir))
        archive_entries.append({"date": d, "count": count})
    render_archive(archive_entries, output_dir=output_dir, template_dir=template_dir, base_url=base_url)
    render_article_pages(nodes, output_dir=output_dir, template_dir=template_dir, base_url=base_url)
    copy_static(output_dir=output_dir, static_dir=static_dir)

    # 11. Email delivery (skip in dry_run)
    if not dry_run and cfg.smtp_user and cfg.smtp_pass and cfg.recipients:
        html_body = render_email(nodes, today, template_dir=template_dir)
        subject = f"{cfg.email.subject_prefix} {today}"
        send_briefing_email(html_body, subject, cfg.smtp_user, cfg.smtp_pass, cfg.recipients)

    # 12. Google Sheets sync (skip in dry_run)
    if not dry_run:
        sync_to_sheets(nodes, cfg.google_sheets_credentials, cfg.google_sheets_id)

    logger.info("=== Pipeline complete ===")


def main():
    parser = argparse.ArgumentParser(description="Game Legal Briefing Pipeline")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--output", default="output", help="Output directory")
    parser.add_argument("--templates", default="templates", help="Template directory")
    parser.add_argument("--static", default="static", help="Static assets directory")
    parser.add_argument("--dry-run", action="store_true", help="Skip email and Sheets sync")
    args = parser.parse_args()
    run_pipeline(config_path=args.config, output_dir=args.output,
                template_dir=args.templates, static_dir=args.static, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_main.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS (30+ tests)

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: CLI orchestrator connecting all pipeline stages"
```

---

### Task 22: GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/briefing.yml`

- [ ] **Step 1: Create workflow**

```yaml
# .github/workflows/briefing.yml
name: Game Legal Briefing

on:
  schedule:
    # Mon/Wed/Fri at 01:07 UTC (10:07 KST)
    - cron: "7 1 * * 1,3,5"
  workflow_dispatch:  # Manual trigger

permissions:
  contents: write
  pages: write
  id-token: write

jobs:
  briefing:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Need full history to preserve output/data

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run pipeline
        env:
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_PASS: ${{ secrets.SMTP_PASS }}
          RECIPIENTS: ${{ secrets.RECIPIENTS }}
          GOOGLE_SHEETS_CREDENTIALS: ${{ secrets.GOOGLE_SHEETS_CREDENTIALS }}
          GOOGLE_SHEETS_ID: ${{ secrets.GOOGLE_SHEETS_ID }}
        run: python main.py

      # Commit JSON data files to main (preserves daily archive + dedup index)
      - name: Commit data files
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add output/data/
          git diff --cached --quiet || git commit -m "data: briefing $(date +%Y-%m-%d)"
          git push

      # Deploy rendered HTML to GitHub Pages (artifact-based, no gh-pages branch needed)
      - name: Setup Pages
        uses: actions/configure-pages@v4

      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: output

      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

Note: Only `output/data/` (JSON files, dedup index) is committed to main. The rendered HTML in `output/` is deployed to GitHub Pages via artifact upload, avoiding repo bloat from HTML files.

- [ ] **Step 2: Commit**

```bash
mkdir -p .github/workflows
git add .github/workflows/briefing.yml
git commit -m "feat: GitHub Actions workflow for Mon/Wed/Fri cron + Pages deploy"
```

---

### Task 23: Port RSS Source List from v1

**Files:**
- Modify: `config.yaml`

- [ ] **Step 1: Update config.yaml with full source list**

Port the complete RSS source list from v1's config. This is the full list of 50+ feeds covering game media, BigLaw blogs, tech policy, and Korean regulators. The exact list should be copied from the v1 repo's `config.yaml` `tier_a` and `tier_b` sections.

**Note for implementer:** You will need access to the v1 private repo at this step. Copy the `sources.tier_a` and `sources.tier_b` lists from the v1 `config.yaml`.

If v1 access is not available, build the list from these categories (aim for 50+ feeds total):
- **Game industry media** (10-15): GamesIndustry.biz, GameSpot, Polygon, Kotaku, IGN, PC Gamer, Eurogamer, VGC
- **BigLaw blogs with game/tech practice** (5-10): Morrison Foerster, Covington, Perkins Coie, Davis Wright Tremaine
- **Tech policy/regulation media** (5-10): The Verge Policy, Ars Technica Policy, TechCrunch Policy, Protocol, The Information
- **Korean regulators/media** (5-10): 게임물관리위원회, 방송통신위원회, 한국인터넷진흥원, 전자신문, 디스이즈게임
- **International regulators** (5-10): EU Commission, FTC, UK Competition & Markets Authority, Australia ACCC
- **Esports/gaming business** (3-5): Esports Observer, GamesIndustry.biz Business

Start with the feeds below and expand:

```yaml
sources:
  tier_a:
    - name: "GamesIndustry.biz"
      url: "https://www.gamesindustry.biz/feed"
    - name: "GameSpot"
      url: "https://www.gamespot.com/feeds/news/"
    - name: "The Verge - Policy"
      url: "https://www.theverge.com/rss/policy/index.xml"
    - name: "Ars Technica - Policy"
      url: "https://feeds.arstechnica.com/arstechnica/policy"
    - name: "TechCrunch - Policy"
      url: "https://techcrunch.com/tag/policy/feed/"
    # ... (add full list from v1)
  tier_b: []
```

- [ ] **Step 2: Commit**

```bash
git add config.yaml
git commit -m "feat: port RSS source list from v1"
```

---

### Task 24: Final Integration Test + README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Run full test suite**

```bash
python -m pytest tests/ -v --tb=short
```

Expected: All tests pass.

- [ ] **Step 2: Create README.md**

```markdown
# Game Legal Briefing

Open-source game industry regulatory intelligence platform. Collects articles from 50+ RSS sources, classifies them with structured metadata (jurisdiction, regulatory phase, event type) using AI, and publishes a browsable static site with email delivery.

## Quick Start

1. Clone the repo and install dependencies:
   ```bash
   pip install -r requirements.txt
   cp .env.example .env
   # Edit .env with your API keys
   ```

2. Run the pipeline:
   ```bash
   python main.py
   ```

3. View the output at `output/index.html`

## Architecture

```
RSS Feeds → Keyword Filter → Dedup → AI Selection → Classification + Summarization
    → BriefingNode JSON → Static HTML (GitHub Pages) + Email + Google Sheets
```

Every article produces a structured `BriefingNode` with jurisdiction, category, regulatory phase, and event metadata. The site, email, and admin log are all views on the same JSON data.

## Configuration

- `config.yaml` — Non-sensitive settings (sources, model, thresholds)
- Environment variables — Secrets (API keys, SMTP credentials, recipients)

See `.env.example` for required environment variables.

## License

Apache 2.0
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README with quick start and architecture overview"
```

- [ ] **Step 4: Verify project structure**

```bash
find . -type f -not -path './.git/*' -not -path './__pycache__/*' | sort
```

Verify the tree matches DESIGN.md architecture.
