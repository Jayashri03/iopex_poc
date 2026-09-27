"""
Reconstructs a PullRequest from what's already in MySQL, rather than the
agent re-fetching from the adapter a second time. This guarantees the agent
reviews exactly the commit set scripts/ingest_mock_data.py persisted - a
reasoning step or review_comment that references a commit_sha is always a
commit that actually exists in this PR's stored history, even if the
underlying adapter/pexgit source has since moved on.
"""
from db.connection import get_cursor
from pexgit_adapter.base import Commit, CommitFile, PullRequest


def load_pr(pexgit_pr_id: str) -> PullRequest:
    with get_cursor() as cursor:
        cursor.execute("SELECT * FROM prs WHERE pexgit_pr_id = %s", (pexgit_pr_id,))
        pr_row = cursor.fetchone()
        if not pr_row:
            raise KeyError(f"No PR found with id {pexgit_pr_id}")

        cursor.execute(
            """
            SELECT id, commit_sha, author, message, committed_at
            FROM commits WHERE pr_id = %s
            ORDER BY commit_order ASC
            """,
            (pr_row["id"],),
        )
        commit_rows = cursor.fetchall()

        commits = []
        for c in commit_rows:
            cursor.execute(
                "SELECT file_path, change_type, diff_text FROM commit_files WHERE commit_id = %s",
                (c["id"],),
            )
            files = cursor.fetchall()
            commits.append(
                Commit(
                    commit_sha=c["commit_sha"],
                    author=c["author"],
                    message=c["message"],
                    committed_at=str(c["committed_at"]),
                    files=[CommitFile(**f) for f in files],
                )
            )

    return PullRequest(
        pexgit_pr_id=pr_row["pexgit_pr_id"],
        repository=pr_row["repository"],
        title=pr_row["title"],
        description=pr_row["description"] or "",
        author=pr_row["author"],
        source_branch=pr_row["source_branch"],
        target_branch=pr_row["target_branch"],
        status=pr_row["status"],
        created_at=str(pr_row["created_at"]),
        updated_at=str(pr_row["updated_at"]),
        commits=commits,
    )
