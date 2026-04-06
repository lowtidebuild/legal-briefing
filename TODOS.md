# TODOS

## Phase 2

- [ ] **Makefile with dev setup targets** — `make setup && make test` for new contributors. venv + pip install + test in one command. No blockers.
- [ ] **LLM call parallelization** — ThreadPoolExecutor for classify+summarize. ~5x speedup (40s → 8s). Depends on: Gemini retry fix + fallback provider.
