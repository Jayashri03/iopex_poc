"""
Offline job: run the multistep review agent over every open PR and persist
PR metadata, files, review comments, merge conflicts, and the full reasoning
trace into MySQL. The API layer only ever reads from these tables.
"""
import json
import pathlib
import sys
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from agent.review_agent import review_pr  # noqa: E402
from db.connection import get_cursor  # noqa: E402
from pexgit_adapter.mock_adapter import MockPexGitAdapter  # noqa: E402


def _upsert_pr(cursor, pr) -> int:
    cursor.execute("SELECT id FROM prs WHERE pexgit_pr_id = %s", (pr.pexgit_pr_id,))
    existing = cursor.fetchone()

    if existing:
        pr_id = existing["id"]
        cursor.execute(
            """
            UPDATE prs SET title=%s, description=%s, author=%s, source_branch=%s,
                target_branch=%s, status=%s, updated_at=%s
            WHERE id=%s
            """,
            (pr.title, pr.description, pr.author, pr.source_branch, pr.target_branch,
             pr.status, pr.updated_at, pr_id),
        )
    else:
        cursor.execute(
            """
            INSERT INTO prs (pexgit_pr_id, title, description, author, source_branch,
                target_branch, status, review_status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s)
            """,
            (pr.pexgit_pr_id, pr.title, pr.description, pr.author, pr.source_branch,
             pr.target_branch, pr.status, pr.created_at, pr.updated_at),
        )
        pr_id = cursor.lastrowid

    # Clear anything from a previous run of this job for this PR.
    for table in ("pr_files", "merge_conflicts", "review_comments", "reasoning_steps"):
        cursor.execute(f"DELETE FROM {table} WHERE pr_id = %s", (pr_id,))

    for f in pr.files:
        cursor.execute(
            "INSERT INTO pr_files (pr_id, file_path, change_type, diff_text) VALUES (%s, %s, %s, %s)",
            (pr_id, f.file_path, f.change_type, f.diff_text),
        )

    return pr_id


def _persist_result(cursor, pr_id: int, result):
    for c in result.review_comments:
        cursor.execute(
            """
            INSERT INTO review_comments (pr_id, file_path, line_hint, severity, category, comment, suggested_fix)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                pr_id,
                c.get("file_path", ""),
                c.get("line_hint", ""),
                c.get("severity", "medium"),
                c.get("category", "bug"),
                c.get("comment", ""),
                c.get("suggested_fix", ""),
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
    adapter = MockPexGitAdapter()

    for pr_summary in adapter.list_prs():
        pr = adapter.get_pr(pr_summary.pexgit_pr_id)
        print(f"Reviewing {pr.pexgit_pr_id}: {pr.title}")

        with get_cursor(commit=True) as cursor:
            pr_id = _upsert_pr(cursor, pr)

        result = review_pr(pr, adapter)

        with get_cursor(commit=True) as cursor:
            _persist_result(cursor, pr_id, result)

        print(
            f"  -> {len(result.review_comments)} comment(s), "
            f"{len(result.merge_conflicts)} conflict(s), "
            f"{len(result.steps)} reasoning step(s)"
        )


if __name__ == "__main__":
    main()
