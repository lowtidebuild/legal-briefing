<div align="center">

# Game Legal Briefing

**Open-source regulatory intelligence for the game industry**

<p>
  <img src="https://img.shields.io/badge/License-Apache_2.0-1F6FEB?style=for-the-badge" alt="Apache 2.0" />
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/RSS_Feeds-54-15803D?style=for-the-badge" alt="54 RSS feeds" />
  <img src="https://img.shields.io/badge/LLM-Gemini_%2B_Claude-8B5CF6?style=for-the-badge" alt="Gemini and Claude" />
</p>

**[Self-Host](#self-host)** · **[Architecture](#architecture)** · **[Roadmap](#roadmap)**

**Language:** [**English**](README.md) | [한국어](docs/ko/README.md)

</div>

---

## What This Does

Collects articles from 54 RSS feeds across game industry media, tech policy outlets, Korean press, and BigLaw blogs. Filters for legal and regulatory relevance, deduplicates by URL and EventKey, classifies each article with structured metadata via AI (Gemini), summarizes in Korean, and publishes as a static briefing site with email delivery.

> [!IMPORTANT]
> This is not legal advice. It is an open-source tool for structured regulatory monitoring.

## Why

Enterprise RegTech (CUBE, Regology, Compliance.ai) costs $50k-$500k+/year and targets banks and pharma. No open-source tool exists for game industry lawyers tracking regulatory changes across jurisdictions.

Most news briefers stop at headlines and summaries. This project attaches **structured legal metadata** to every article:

| Field | Example |
|-------|---------|
| Jurisdiction | EU, KR, US, JP, UK, AU, CN |
| Category | Consumer monetization, age rating, privacy, IP |
| Regulatory phase | Proposed, public comment, enacted, enforced, litigation |
| Event Key | `eu_lootbox_transparency_directive_2026` |
| Game mechanic | Loot box, age rating, data collection |

Over time, this turns a mailing list into a searchable regulatory archive for the game industry.

## Self-Host

Want to fork this project and run your own briefing pipeline? Follow the steps below.

### 1. Install

```bash
git clone https://github.com/lowtidebuild/game-legal-briefing.git
cd game-legal-briefing
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Try with sample data first

No API keys needed:

```bash
python main.py --dry-run --sample-data
open output/index.html
```

### 3. Set up API keys

```bash
cp .env.example .env
```

Edit `.env` and fill in the values:

| Variable | Purpose | Required |
|----------|---------|----------|
| `GROQ_API_KEY` | Groq API key ([get one](https://console.groq.com/keys)) | **Yes** |
| `GOOGLE_API_KEY` | Gemini API key (legacy configuration only) | No |
| `ANTHROPIC_API_KEY` | Claude API key (legacy configuration only) | No |
| `SMTP_USER` | Gmail address (e.g., `you@gmail.com`) | For email |
| `SMTP_PASS` | Gmail app password (16 chars, keep spaces) | For email |
| `RECIPIENTS` | Comma-separated recipient emails | For email |
| `GOOGLE_SHEETS_CREDENTIALS` | Sheets service account JSON | For Sheets |
| `GOOGLE_SHEETS_ID` | Spreadsheet ID | For Sheets |

> **Only `GROQ_API_KEY` is required for the current LLM configuration.** Email and Sheets are skipped automatically when not configured.

### 4. Run

```bash
python main.py --dry-run   # Generate site only (skip email/Sheets)
python main.py              # Full run (email + Sheets included)
```

Output:
- `output/index.html` — Latest briefing
- `output/archive/` — Date-based archive
- `output/article/` — Article detail pages
- `output/data/daily/*.json` — Structured data

### 5. Set up GitHub Actions

To automate delivery from your fork:

1. **Add GitHub Secrets:** repo Settings → Secrets and variables → Actions → add each env var as a Secret
2. **Enable GitHub Pages:** repo Settings → Pages → Source → "GitHub Actions"
3. **Automatic schedule:** Mon/Wed/Fri at 10:07 AM KST (manual: Actions tab → Run workflow)

### Google Sheets setup (optional)

Sheets serves as an admin log and EventKey dedup authority. EventKey-based dedup prevents the same regulatory event from being sent twice, even when covered by different sources.

1. [Google Cloud Console](https://console.cloud.google.com) → APIs & Services → Library → enable "Google Sheets API"
2. IAM & Admin → Service Accounts → create account → Keys → download JSON
3. Create a spreadsheet → share with the service account email (Editor)
4. Add `GOOGLE_SHEETS_CREDENTIALS` (paste full JSON) and `GOOGLE_SHEETS_ID` (from spreadsheet URL) to GitHub Secrets

Backfill existing archive data:
```bash
GOOGLE_SHEETS_CREDENTIALS='path/to/credentials.json' \
GOOGLE_SHEETS_ID='your-spreadsheet-id' \
python scripts/backfill_sheets.py
```

### Gmail app password

1. [Google Account Security](https://myaccount.google.com/security) → enable 2-Step Verification
2. Generate an app password → copy the 16-character password
3. `SMTP_USER` = your full Gmail address, `SMTP_PASS` = the 16 chars (keep spaces)

---

## Pipeline

```mermaid
flowchart LR
    A["54 RSS feeds"] --> B["Keyword filter"]
    B --> B2["Recency filter (7 days)"]
    B2 --> C["URL dedup"]
    C --> D["LLM selection (top 10)"]
    D --> E["Classification + EventKey"]
    E --> F["Korean title + summary"]
    F --> G["EventKey dedup (Sheets)"]
    G --> H["BriefingNode JSON"]
    H --> I["Static site"]
    H --> J["Email"]
    H --> K["Google Sheets"]
    I --> L["GitHub Pages"]
```

## Dedup Strategy

Three layers prevent duplicate articles and events from being sent:

| Layer | Method | Description |
|-------|--------|-------------|
| 1 | URL hash | Exact URL match (rolling 30-day JSON index) |
| 2 | Topic tokens | Title word similarity (catches same article from different URLs) |
| 3 | EventKey | LLM-generated event identifier (e.g., `eu_lootbox_directive_2026`), Google Sheets as authority |

EventKey can be reviewed and edited by humans in Sheets, so LLM inconsistencies can be corrected manually.

## Architecture

```text
game-legal-briefing/
├── main.py                 # Pipeline entry point
├── config.yaml             # Non-secret config (54 RSS sources)
├── pipeline/
│   ├── sources/            # RSS collection, keyword/recency filter
│   ├── intelligence/       # Selection, classification, summarization, dedup
│   ├── llm/                # Provider abstraction (Gemini default, Claude fallback)
│   ├── store/              # JSON storage, dedup index, query
│   ├── render/             # Site + email rendering (Jinja2)
│   ├── deliver/            # Gmail SMTP delivery
│   └── admin/              # Google Sheets sync + EventKey read
├── templates/              # Web + email Jinja2 templates
├── static/                 # CSS (Pretendard + Noto Serif KR)
├── scripts/                # Utilities (backfill_sheets.py)
├── tests/                  # pytest (47 tests)
└── output/                 # Generated site + data (GitHub Pages)
```

## Tests

```bash
python -m pytest tests -q                  # 47 unit tests
python main.py --dry-run --sample-data     # Integration check (no API keys needed)
```

## Roadmap

| Stage | Focus |
|:------|:------|
| **Done** | MVP pipeline, 54 feeds, Gemini+Claude fallback, EventKey dedup, Korean titles, category grouping, Sheets admin, GitHub Pages, email delivery |
| **Next** | Tier C scrapers (government sites without RSS), English summaries |
| **Later** | Jurisdiction Pulse dashboard, topic timelines |
| **Future** | Cross-jurisdiction event linking, per-topic/phase RSS feeds |

## License

Apache 2.0
