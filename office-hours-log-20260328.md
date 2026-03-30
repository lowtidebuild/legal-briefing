# Office Hours Log — 2026-03-28

## Session Info
- **Skill:** /office-hours
- **Mode:** Builder (Open source / research)
- **Project:** game-policy-briefing (v1) → game-legal-briefing (v2)
- **Branch:** main
- **Duration:** ~30 min

---

## Phase 1: Context Gathering

**Current state (v1):**
- Single monolithic Python script (`news_archiver.py`, ~1,700 lines)
- 50+ RSS sources: game media, BigLaw blogs, tech policy, Korean regulators
- Claude Haiku for filtering top 10 articles + Korean summarization
- 3-stage dedup: URL → topic tokens → EventKey
- Notion upload + Gmail SMTP email to ~27 recipients
- Recipients: Pearl Abyss, Smilegate, Supercent, law firms, individuals
- GitHub Actions cron: Mon/Wed/Fri at KST 10:07
- Private repo, secrets in config.yaml
- Running reliably since early 2026

**User's motivation:**
- First vibe-coding project, works great but not sophisticated
- Experience has grown significantly since then
- Wants to preserve v1 untouched (sentimental + safety net)
- New public repo with production-grade architecture
- Reference daily-brief project for patterns

---

## Phase 2B: Builder Mode Questions

**Goal:** Open source / research

**Q: What's the coolest version?**
- Web UI with browsable archive of past briefings
- Referenced daily-brief's web implementation (GitHub Pages, Jinja2 templates)
- Wants historical browsing, clean archive navigation

**Q: Who would you show this to?**
- A: Game industry legal teams worldwide
- The public site becomes a shared resource

**Q: What's the 10x version?**
- A: Jurisdiction tracker — visual dashboard showing active regulatory changes by country
- EU battery law, US FTC actions, Korea age ratings — with status and impact

**User correction during session:**
- Weekly recaps unnecessary at 3x/week frequency
- "주 3회 발송이라 weekly recap이 필요 없을거 같긴 하다"
- Just make the archive browsable and clean

---

## Phase 2.75: Landscape Research

**Layer 1 (tried and true):**
- Enterprise RegTech (CUBE, Regology, Compliance.ai) costs $50k-$500k+/year
- Targets banks, pharma, insurance — not game industry

**Layer 2 (current discourse):**
- AI being layered onto every RegTech tool
- Regology uses AI agents, Visualping monitors page changes
- All enterprise SaaS, closed source, none game-industry specific

**Layer 3 (our insight):**
- User already proved single Python script + Claude Haiku serves 27 legal professionals
- Enterprise RegTech wildly overbuilt for game industry needs
- The niche (game industry lawyers worldwide) is real and completely unserved
- No eureka moment, just strong confirmation

---

## Phase 3: Premises (All Agreed)

1. Original repo stays untouched — new repo, fresh history
2. Public repo = zero secrets in code (emails, API keys → GitHub Secrets)
3. Static site on GitHub Pages (Jinja2 → HTML, no server/DB)
4. Jurisdiction tracker is stretch goal, not MVP
5. daily-brief architecture is reference implementation
6. Weekly recaps unnecessary at 3x/week — clean archive is sufficient

---

## Phase 3.5: Cross-Model Second Opinion (Claude Subagent)

**Key insights:**
1. **Coolest version not considered:** Living regulatory knowledge graph — each article as a node with jurisdiction, topic, phase metadata. Enables timeline pages, cross-jurisdiction pattern detection, per-topic RSS feeds
2. **What excites user most:** "The public site becomes a shared resource" — "not someone who wants a better internal tool, excited about owning the category"
3. **50% solution:** Pelican (static site generator) for archives/feeds/i18n. But raw Jinja2 like daily-brief gives more control
4. **Weekend build plan:** Saturday AM: pipeline → JSON. Saturday PM: Pelican site. Sunday AM: GitHub Actions. Sunday PM: email + weekly recap

**Cross-model synthesis:**
- Agreed: Knowledge graph / structured metadata idea is the right primitive
- Disagreed on Pelican: daily-brief's raw Jinja2 approach is simpler and more controllable
- Strong signal: User is building the first open-source game industry regulatory intelligence platform

---

## Phase 4: Approaches Considered

### A) daily-brief Clone — Modular Pipeline + Raw Jinja2
- Proven architecture, full control, no framework lock-in
- Completeness: 7/10

### B) Pelican-Powered — Static Site Generator + Pipeline
- Faster to browsable site, but adds dependency
- Completeness: 6/10

### C) Structured Metadata First (CHOSEN)
- Every article → structured JSON node (jurisdiction, topic, phase, event_key)
- Site, email, jurisdiction tracker all views on same data
- Jurisdiction tracker becomes natural extension, not bolt-on
- Completeness: 9/10

**User chose: C**

---

## Visual Wireframe

Generated at `/tmp/gstack-sketch-game-policy-v2.html` and screenshotted.

Key design elements:
- Header with date navigation (◀ ▶), Archive/EN links
- Jurisdiction Pulse (stretch goal) — country chips with activity levels
- Articles with category chips (AI_EMERGING, CONSUMER, CONTENT_AGE)
- Jurisdiction tags (🇪🇺 EU, 🇰🇷 Korea, 🇺🇸 US)
- Regulatory phase badges (Enacted, Litigation, Proposed)
- Structured event metadata (actors, event type)
- Recent Briefings archive with article counts
- Editorial style: warm ivory #FAFAF8, clean typography, mobile-first 720px

---

## Phase 5: Design Doc

Written to: `~/.gstack/projects/lowtidebuild-game-policy-briefing/kpsfamily-main-design-20260328-231310.md`
Copied to: `/Users/kpsfamily/코딩 프로젝트/game-legal-briefing/DESIGN.md`

### Spec Review Results
- **Round 1:** 16 issues found, all fixed. Score: 7/10
- **Round 2:** 5 minor issues found, all fixed. Score: 8/10
- **Total issues caught and fixed:** 21

### Key fixes from review:
- Renamed "knowledge graph" to "structured metadata" (accurate terminology)
- Added retry/rate limiting specification
- Added dedup persistence mechanism (dedup_index.json)
- Resolved English support contradiction (Phase 2, not MVP)
- Fixed "zero cost" to "near-zero" (Claude API has per-call cost)
- Added query interface with method signatures
- Defined RegulatoryPhase, EventType, Jurisdiction as Python enums
- Removed premature Gemini provider from MVP tree
- Created clear MVP vs Phase 2 boundary
- Added test fixture strategy (cassette pattern)
- Added CSS strategy (external for web, inline via premailer for email)
- Added data migration section (clean slate with rationale)

---

## Architecture Summary

```
game-legal-briefing/
├── main.py                          # CLI orchestrator
├── config.yaml                      # Committed config (no secrets)
├── pipeline/
│   ├── sources/rss.py, filters.py
│   ├── intelligence/selector.py, summarizer.py, classifier.py, dedup.py
│   ├── llm/base.py, claude.py
│   ├── store/nodes.py, daily.py, dedup_index.py, query.py
│   ├── render/site.py, email.py
│   └── deliver/mailer.py
├── templates/index.html, archive.html, article.html, email/
├── static/style.css
├── output/ → GitHub Pages
├── .github/workflows/briefing.yml
└── tests/fixtures/, test_*.py
```

---

## Key Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | Structured Metadata First | Jurisdiction tracker falls out naturally |
| Site generator | Raw Jinja2 (no Pelican) | More control, daily-brief proves it works |
| LLM | Gemini 3.1 Flash-Lite (default), Claude Haiku (fallback) | 5x+ 가성비, 추상 인터페이스로 전환 가능 |
| Weekly recap | Dropped | 3x/week makes it redundant |
| English | Phase 2 | Korean audience first |
| Admin UI | Google Sheets (Notion 대체) | 로그 확인, 수정/삭제 가능. Notion보다 가볍고 무료 |
| Secrets | GitHub Secrets only | Public repo requirement |
| Dedup | Rolling JSON index | Sufficient for ~400 entries |

---

## Next Steps

1. Create new public repo `game-legal-briefing`
2. Port pipeline into modular structure
3. Enhance AI prompt for jurisdiction/phase/game_mechanic extraction
4. Build JSON store (data/daily/{date}.json)
5. Build Jinja2 templates with wireframe design
6. Set up GitHub Actions with secrets
7. Test side-by-side with v1
8. Migrate email recipients to RECIPIENTS secret
9. Stretch: Jurisdiction Pulse dashboard

---

## Resolved Questions (Session 2, 2026-03-30)

| Question | Decision |
|----------|----------|
| Repo name | `game-legal-briefing` |
| LLM | Gemini 3.1 Flash-Lite (default), Claude Haiku (fallback) |
| Admin UI | Google Sheets (Notion 대체) — 로그 확인/수정/삭제 가능 |
| Domain | `lowtidebuild.github.io/game-legal-briefing` (기본값) |
| License | Apache 2.0 |
