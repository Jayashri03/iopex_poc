# PR Review Agent (PoC)

An agent that reviews pull requests: reads every commit in the PR, reasons
in multiple steps (optionally using tools to pull in extra codebase
context), and generates review comments, merge-conflict flags, and a
visible reasoning trace. Built for an internal pexgit setup, but the pexgit
connection is mocked here so the focus stays on the agent/review pipeline.

Built only with: VS Code, Git, MySQL, Ollama, Python 3.12.

## Architecture

```
pexgit_adapter/   interface + mock implementation (fixture PRs, each with several commits)
agent/            context_builder (assembles + size-guards the commit history),
                   tools (list_files / search_repo / get_file - plain grep, no RAG),
                   reasoning (multistep ReAct loop), review_agent (entrypoint)
jobs/             offline script: run_review.py reviews all PRs -> MySQL
api/              FastAPI app, read-only, serves what jobs/run_review.py already wrote
db/               schema.sql + connection pooling
```

Review generation is **offline**, not on-demand: `jobs/run_review.py` runs
the agent per PR and persists results (comments, conflicts, full reasoning
trace) to MySQL. The API only reads. This keeps `GET /prs/{id}` fast and
lets you iterate on the agent without touching the API.

## Why no RAG

The agent isn't retrieving snippets of the codebase to guess at what changed
- it's given the PR's **entire commit history** (every commit's message and
diff, in order) directly in the prompt. That's what makes cross-commit
reasoning possible: an issue introduced in commit 2 and only partially
addressed in commit 5 is visible to the model in one pass, because it can
see both commits at once. A RAG/chunking approach would only surface
whichever fragment happened to score highest on a similarity search, which
is the wrong tool for "did this PR actually fix what it claims to fix."

The agent still has tools (`list_files`, `search_repo`, `get_file` in
`agent/tools.py`), but they're plain listing/grep/read over the mock repo,
used only to answer questions the diffs alone can't (e.g. "does something
like this already exist elsewhere?"). No embeddings, no vector store.

## Phase 1 vs. Phase 2: PRs with a lot of commits

Passing the full commit history to the model only works if it fits the
context window. Phase 1 (this PoC) makes that assumption explicit instead
of hiding it:

- `agent/context_builder.py` builds the commit-history block and checks its
  size against `MAX_COMMIT_CONTEXT_CHARS` (`.env`, default 6000 chars).
- If a PR's commits are within budget, the full history goes straight into
  the prompt - see `PR-101`/`PR-102`/`PR-103` in the fixtures.
- If a PR is over budget, `build_commit_context` raises
  `CommitContextTooLarge` rather than silently truncating (which would
  quietly hide the exact cross-commit issues this design exists to catch).
  `jobs/run_review.py` catches that and marks the PR `review_status =
  'needs_batching'` instead of crashing the job - see `PR-104`, a
  deliberately oversized 10-commit fixture that exercises this path.

**Phase 2** (not built yet) is where large PRs actually get handled: batch
commits into groups, review each group, then run a second aggregation pass
over the per-batch summaries to catch issues that span batches. That
aggregation step is the hard part - it's exactly what determines how much
cross-commit context survives batching - so it deserves its own design
rather than being bolted on here.

## Setup

1. `python -m venv .venv && .venv\Scripts\activate`
2. `pip install -r requirements.txt`
3. `copy .env.example .env` and adjust MySQL credentials.
4. Pull the Ollama chat model referenced in `.env`:
   ```
   ollama pull qwen2.5-coder:7b
   ```
5. Create the database and tables: `python scripts/init_db.py`
6. Run the agent over all mock PRs and persist results: `python jobs/run_review.py`
7. Start the API: `uvicorn api.main:app --reload`

## Endpoints

- `GET /prs` — list all PRs (author, source/target branch, status, review status, timestamps)
- `GET /prs/{pexgit_pr_id}` — full detail: every commit (with its own diffs), merge conflicts,
  review comments, and the agent's full step-by-step reasoning trace (thought / action / tool
  input / observation for each step)

Mock PRs and what they demonstrate:
- `PR-101` — 6 commits against a small `app/` package (`payments.py`, `orders.py`, `config.py`,
  `notifications.py`, `utils.py`, plus `tests/`). A bug introduced in commit 1
  (`ZeroDivisionError` when `discount_percent == 100`) is never actually fixed by the later
  commits, even though commit 3 looks like a fix. Two of the six commits are unrelated noise (a
  type hint, a changelog entry) mixed in, like a real branch - not just the commits that matter.
  Tests whether the agent tracks cumulative state and filters noise instead of judging each commit
  in isolation.
- `PR-102` — 2 commits; commit 1 is a clean fix, commit 2 is a merge that reintroduces unresolved
  `<<<<<<<` conflict markers. Tests that final state (not first impressions) drives the verdict.
- `PR-103` — 3 commits; adds `money_to_string`, which duplicates the existing `format_currency`,
  with an unrelated TODO-comment commit mixed in between. Tests the `search_repo` tool for
  catching duplication across files without RAG.
- `PR-104` — 11 commits, deliberately large enough to exceed `MAX_COMMIT_CONTEXT_CHARS`. Tests the
  phase-1 guard: review is skipped and `review_status` is set to `needs_batching`.

None of this is special-cased in the agent's code - `agent/tools.py` and `agent/reasoning.py`
contain no logic that knows about `discount_percent`, `money_to_string`, or any other fixture
specifics. Every review comment in the output comes from the Ollama chat model's own
`final_answer` JSON; there is no fallback or stub path if Ollama is unreachable, so a review can
only be produced by an actual model call (see `agent/llm.py`).

## Re-running after changing the agent or fixtures

`jobs/run_review.py` is idempotent per PR (`pexgit_pr_id`) - re-run it any time after changing
the agent prompt, tools, or fixture data, and it overwrites that PR's commits/comments/conflicts/reasoning.
