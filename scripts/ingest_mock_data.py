"""
Load every PR (and every commit, with full per-file diffs) from the pexgit
adapter into MySQL. This is the only script that writes prs/commits/
commit_files - jobs/run_review.py reads them back by pexgit_pr_id and only
ever writes review output (comments/conflicts/reasoning) on top.

Clears all existing PR rows first (cascades to commits/commit_files/
review output via ON DELETE CASCADE), so re-running this always leaves you
with exactly the current fixture data - no leftover rows from a previous
version of prs.json.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from db.connection import get_cursor  # noqa: E402
from pexgit_adapter.mock_adapter import MockPexGitAdapter  # noqa: E402


def _insert_pr(cursor, pr) -> int:
    cursor.execute(
        """
        INSERT INTO prs (pexgit_pr_id, repository, title, description, author,
            source_branch, target_branch, status, review_status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s)
        """,
        (pr.pexgit_pr_id, pr.repository, pr.title, pr.description, pr.author,
         pr.source_branch, pr.target_branch, pr.status, pr.created_at, pr.updated_at),
    )
    pr_id = cursor.lastrowid

    for order, commit in enumerate(pr.commits):
        cursor.execute(
            """
            INSERT INTO commits (pr_id, commit_sha, commit_order, author, message, committed_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (pr_id, commit.commit_sha, order, commit.author, commit.message, commit.committed_at),
        )
        commit_id = cursor.lastrowid
        for f in commit.files:
            cursor.execute(
                """
                INSERT INTO commit_files (commit_id, file_path, change_type, diff_text)
                VALUES (%s, %s, %s, %s)
                """,
                (commit_id, f.file_path, f.change_type, f.diff_text),
            )

    return pr_id


def main():
    adapter = MockPexGitAdapter()

    with get_cursor(commit=True) as cursor:
        cursor.execute("DELETE FROM prs")  # cascades to commits/commit_files/review output

    total_commits = 0
    for pr_summary in adapter.list_prs():
        pr = adapter.get_pr(pr_summary.pexgit_pr_id)
        with get_cursor(commit=True) as cursor:
            _insert_pr(cursor, pr)
        total_commits += len(pr.commits)
        print(f"Ingested {pr.pexgit_pr_id}: {pr.title} ({len(pr.commits)} commits)")

    print(f"Done: {len(adapter.list_prs())} PRs, {total_commits} commits.")


if __name__ == "__main__":
    main()
