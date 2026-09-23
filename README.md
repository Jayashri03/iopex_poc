# PR Review Agent (PoC)

An agent that reviews pull requests: analyzes diffs, searches the codebase
for context (code-RAG), reasons in multiple steps, and generates review
comments, merge-conflict flags, and a visible reasoning trace. Built for an
internal pexgit setup, but the pexgit connection is mocked here so the focus
stays on the agent/RAG/review pipeline.

Built only with: VS Code, Git, MySQL, Ollama, Python 3.12.

## Architecture

```
pexgit_adapter/   interface + mock implementation (fixture PRs + a small sample codebase)
code_rag/         chunk -> embed (Ollama) -> store in MySQL -> cosine-similarity search in Python
agent/            multistep ReAct-style loop: LLM (Ollama) decides to call a tool or give a final answer
jobs/             offline scripts: build_index.py (index codebase), run_review.py (review all PRs -> MySQL)
api/              FastAPI app, read-only, serves what jobs/run_review.py already wrote
db/               schema.sql + connection pooling
```

Review generation is **offline**, not on-demand: `jobs/run_review.py` runs
the agent per PR and persists results (comments, conflicts, full reasoning
trace) to MySQL. The API only reads. This keeps `GET /prs/{id}` fast and
lets you iterate on the agent without touching the API.

Swapping in the real pexgit integration later means implementing
`pexgit_adapter/base.py`'s `PexGitAdapter` interface against pexgit's API -
nothing in `code_rag/`, `agent/`, `jobs/`, or `api/` needs to change.

## Setup

1. `python -m venv .venv && .venv\Scripts\activate`
2. `pip install -r requirements.txt`
3. `copy .env.example .env` and adjust MySQL credentials.
4. Pull the Ollama models referenced in `.env`:
   ```
   ollama pull qwen2.5-coder:7b
   ollama pull nomic-embed-text
   ```
5. Create the database and tables: `python scripts/init_db.py`
6. Build the code-RAG index over the sample codebase: `python jobs/build_index.py`
7. Run the agent over all mock PRs and persist results: `python jobs/run_review.py`
8. Start the API: `uvicorn api.main:app --reload`

## Endpoints

- `GET /prs` — list all PRs (author, source/target branch, status, review status, timestamps)
- `GET /prs/{pexgit_pr_id}` — full detail: diffs, merge conflicts, review comments, and the agent's
  full step-by-step reasoning trace (thought / action / tool input / observation for each step)

Example: `GET /prs/PR-102` shows a PR with an unresolved merge conflict left in the diff.
`GET /prs/PR-101` shows a PR with a real bug (division by zero when `discount_percent == 100`).
`GET /prs/PR-103` shows a PR the agent should flag as duplicating existing logic, found via
`search_code` over the indexed codebase.

## Re-running after changing the agent or fixtures

`jobs/run_review.py` is idempotent per PR (`pexgit_pr_id`) - re-run it any time after changing
the agent prompt, tools, or fixture data, and it overwrites that PR's comments/conflicts/reasoning.
