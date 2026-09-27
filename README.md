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
scripts/          init_db.py (drop+recreate schema), ingest_mock_data.py (load PRs/commits into MySQL)
jobs/             run_review.py - reviews already-ingested PRs, writes results -> MySQL
api/              FastAPI app, read-only, serves what scripts/jobs already wrote
db/               schema.sql, connection pooling, pr_repository.py (reconstructs a PR from MySQL rows)
```

Three separate steps, each owning one thing:
1. `scripts/init_db.py` - drops and recreates every table. Always a clean slate.
2. `scripts/ingest_mock_data.py` - the only thing that writes `prs`/`commits`/`commit_files`.
   Wipes and reloads all PR rows from the adapter every run.
3. `jobs/run_review.py` - iterates whatever's already in `prs`, loads each PR's full commit
   history back out of MySQL (`db/pr_repository.py`, not a second fetch from the adapter), runs
   the agent against that, and writes review output (comments/conflicts/reasoning) onto the row.

The agent's commit-diff input and the API's commit-diff output are deliberately the same read:
both come from `commits`/`commit_files` in MySQL. Nothing re-fetches from the adapter for a PR
that's already been ingested - that would let the two diverge (the agent reviewing a commit set
the DB, and therefore the API, doesn't actually have). The adapter is still used for one thing:
`agent/tools.py`'s `list_files`/`search_repo`/`get_file`, which browse the wider codebase rather
than this PR's own commits - MySQL never stores the full repo, only what commits touched.

The API only reads whatever those scripts already wrote. This keeps `GET /prs/{id}` fast and lets
you iterate on the agent without touching ingestion, or reload fixtures without re-running the
(slower, Ollama-calling) review step.

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
6. Load the mock PRs/commits into MySQL: `python scripts/ingest_mock_data.py`
7. Run the agent over all ingested PRs and persist results: `python jobs/run_review.py`
8. Start the API: `uvicorn api.main:app --reload`

## Endpoints

- `GET /prs` — every PR's repository, branches, status, review status, timestamps, and every
  commit's id/author/message/timestamp (no diffs - that's `GET /prs/{id}`)
- `GET /prs/{pexgit_pr_id}` — full detail: repository, branches, every commit with its own
  files+diffs, merge conflicts, review comments, and the agent's full step-by-step reasoning
  trace (thought / action / tool input / observation for each step)

What the agent is actually given as input: for each PR, its repository/branches plus every
commit's id, author, message, and diff, read back from MySQL via `db/pr_repository.py`
(`agent/context_builder.py` assembles it into the prompt) - literally the same rows
`GET /prs/{id}` reads, minus the review output (that's the agent's *output*, not its input).
It is not hunk-level line context beyond the diff itself, and it is not the full content of
every touched file by default - the agent can fetch a full file on demand via the `get_file`
tool if a diff alone isn't enough, but nothing forces that on every review.

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

## Re-running after changing things

- Changed the agent prompt/tools only? Re-run `python jobs/run_review.py` - it overwrites each
  PR's comments/conflicts/reasoning in place, no need to touch ingestion.
- Changed `pexgit_adapter/fixtures/prs.json`? Re-run `python scripts/ingest_mock_data.py` (reloads
  PR/commit rows from scratch) then `python jobs/run_review.py`.
- Changed `db/schema.sql` itself? Re-run `python scripts/init_db.py` first (drops everything),
  then both scripts above.
