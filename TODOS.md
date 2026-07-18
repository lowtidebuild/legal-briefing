# TODOS

## Phase 2

- [ ] **Makefile with dev setup targets** — `make setup && make test` for new contributors. venv + pip install + test in one command. No blockers.

## Completed design decisions

- [x] **LLM call reduction** — Replaced per-item parallel calls with bounded batches, ID validation, shared rate-limit state, and batch fallback. Parallel LLM calls are intentionally not reintroduced because free-tier burst limits were the primary reliability problem.
