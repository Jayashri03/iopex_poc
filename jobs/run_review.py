"""
Offline job: run the multistep review agent over every PR already ingested
into MySQL (via scripts/ingest_mock_data.py) and persist review comments,
merge conflicts, and the full reasoning trace back onto that PR row.

This script does not write prs/commits/commit_files - it only reviews rows
that are already there. Commit data for the agent's context comes from
db/pr_repository.py (i.e. MySQL itself), NOT a second fetch from the
adapter - this guarantees the agent reasons about exactly the commit set
that's stored, so a review_comment's introduced_in_commit always points at
a commit that actually exists in this PR's row. The adapter is only used
here to build the agent's tools (list_files/search_repo/get_file), which
browse the wider codebase rather than this PR's own commits.

PRs whose full commit history doesn't fit the phase-1 single-shot context
budget (see agent/context_builder.py) are marked review_status='needs_batching'
instead of reviewed - they need the phase 2 batch+aggregate strategy, not
built yet.
"""
import json
import pathlib
import sys
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from agent.context_builder import CommitContextTooLarge  # noqa: E402
from agent.review_agent import review_pr  # noqa: E402
from db.connection import get_cursor  # noqa: E402
from db.pr_repository import load_pr  # noqa: E402
from pexgit_adapter.mock_adapter import MockPexGitAdapter  # noqa: E402


def _persist_result(cursor, pr_id: int, result):
    for table in ("merge_conflicts", "review_comments", "reasoning_steps"):
        cursor.execute(f"DELETE FROM {table} WHERE pr_id = %s", (pr_id,))

    for c in result.review_comments:
        cursor.execute(
            """
            INSERT INTO review_comments
                (pr_id, file_path, line_hint, severity, category, comment, suggested_fix, introduced_in_commit)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                pr_id,
                c.get("file_path", ""),
                c.get("line_hint", ""),
                c.get("severity", "medium"),
                c.get("category", "bug"),
                c.get("comment", ""),
                c.get("suggested_fix", ""),
                c.get("introduced_in_commit", ""),
            ),
        )

    for mc in result.merge_conflicts:
        cursor.execute(
            "INSERT INTO merge_conflicts (pr_id, file_path, detail) VALUES (%s, %s, %s)",
            (pr_id, mc.get("file_path", ""), mc.get("detail", "")),
        )

    for step in result.steps:
        cursor.execute(
            """
            INSERT INTO reasoning_steps (pr_id, step_number, thought, action, action_input, observation)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                pr_id,
                step.step_number,
                step.thought,
                step.action,
                json.dumps(step.action_input),
                step.observation,
            ),
        )

    cursor.execute(
        "UPDATE prs SET review_status='reviewed', review_summary=%s, reviewed_at=%s WHERE id=%s",
        (result.summary, datetime.now(), pr_id),
    )


def main():
    adapter = MockPexGitAdapter()  # only for the agent's codebase-browsing tools

    with get_cursor() as cursor:
        cursor.execute("SELECT id, pexgit_pr_id FROM prs ORDER BY created_at ASC")
        ingested_prs = cursor.fetchall()

    if not ingested_prs:
        print("No PRs ingested yet - run scripts/ingest_mock_data.py first.")
        return

    for row in ingested_prs:
        pr_id = row["id"]
        pr = load_pr(row["pexgit_pr_id"])
        print(f"Reviewing {pr.pexgit_pr_id}: {pr.title} ({len(pr.commits)} commits)")

        try:
            result = review_pr(pr, adapter)
        except CommitContextTooLarge as exc:
            print(f"  -> SKIPPED: {exc}")
            with get_cursor(commit=True) as cursor:
                cursor.execute(
                    "UPDATE prs SET review_status='needs_batching', review_summary=%s WHERE id=%s",
                    (str(exc), pr_id),
                )
            continue

        with get_cursor(commit=True) as cursor:
            _persist_result(cursor, pr_id, result)

        print(
            f"  -> {len(result.review_comments)} comment(s), "
            f"{len(result.merge_conflicts)} conflict(s), "
            f"{len(result.steps)} reasoning step(s)"
        )


if __name__ == "__main__":
    main()
