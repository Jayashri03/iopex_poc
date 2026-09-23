import json

from fastapi import FastAPI, HTTPException

from api.schemas import (
    MergeConflictOut,
    PRDetailOut,
    PRFileOut,
    PRListItem,
    ReasoningStepOut,
    ReviewCommentOut,
)
from db.connection import get_cursor

app = FastAPI(title="PR Review Agent (PoC)")


@app.get("/prs", response_model=list[PRListItem])
def list_prs():
    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, pexgit_pr_id, title, author, source_branch, target_branch,
                   status, review_status, created_at, updated_at
            FROM prs
            ORDER BY created_at DESC
            """
        )
        rows = cursor.fetchall()
    return rows


@app.get("/prs/{pexgit_pr_id}", response_model=PRDetailOut)
def get_pr_detail(pexgit_pr_id: str):
    with get_cursor() as cursor:
        cursor.execute("SELECT * FROM prs WHERE pexgit_pr_id = %s", (pexgit_pr_id,))
        pr = cursor.fetchone()
        if not pr:
            raise HTTPException(status_code=404, detail=f"PR {pexgit_pr_id} not found")

        pr_id = pr["id"]

        cursor.execute(
            "SELECT file_path, change_type, diff_text FROM pr_files WHERE pr_id = %s",
            (pr_id,),
        )
        files = cursor.fetchall()

        cursor.execute(
            "SELECT file_path, detail FROM merge_conflicts WHERE pr_id = %s",
            (pr_id,),
        )
        conflicts = cursor.fetchall()

        cursor.execute(
            """
            SELECT file_path, line_hint, severity, category, comment, suggested_fix
            FROM review_comments WHERE pr_id = %s
            ORDER BY FIELD(severity, 'high', 'medium', 'low')
            """,
            (pr_id,),
        )
        comments = cursor.fetchall()

        cursor.execute(
            """
            SELECT step_number, thought, action, action_input, observation
            FROM reasoning_steps WHERE pr_id = %s
            ORDER BY step_number ASC
            """,
            (pr_id,),
        )
        steps = cursor.fetchall()
        for step in steps:
            try:
                step["action_input"] = json.loads(step["action_input"]) if step["action_input"] else {}
            except json.JSONDecodeError:
                step["action_input"] = {}

    return PRDetailOut(
        id=pr["id"],
        pexgit_pr_id=pr["pexgit_pr_id"],
        title=pr["title"],
        description=pr["description"],
        author=pr["author"],
        source_branch=pr["source_branch"],
        target_branch=pr["target_branch"],
        status=pr["status"],
        review_status=pr["review_status"],
        review_summary=pr["review_summary"],
        created_at=pr["created_at"],
        updated_at=pr["updated_at"],
        reviewed_at=pr["reviewed_at"],
        files=[PRFileOut(**f) for f in files],
        merge_conflicts=[MergeConflictOut(**c) for c in conflicts],
        review_comments=[ReviewCommentOut(**c) for c in comments],
        reasoning_steps=[ReasoningStepOut(**s) for s in steps],
    )
