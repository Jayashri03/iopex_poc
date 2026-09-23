from datetime import datetime

from pydantic import BaseModel


class PRListItem(BaseModel):
    id: int
    pexgit_pr_id: str
    title: str
    author: str
    source_branch: str
    target_branch: str
    status: str
    review_status: str
    created_at: datetime
    updated_at: datetime


class PRFileOut(BaseModel):
    file_path: str
    change_type: str
    diff_text: str


class MergeConflictOut(BaseModel):
    file_path: str
    detail: str


class ReviewCommentOut(BaseModel):
    file_path: str
    line_hint: str | None
    severity: str
    category: str
    comment: str
    suggested_fix: str | None


class ReasoningStepOut(BaseModel):
    step_number: int
    thought: str | None
    action: str
    action_input: dict
    observation: str | None


class PRDetailOut(BaseModel):
    id: int
    pexgit_pr_id: str
    title: str
    description: str | None
    author: str
    source_branch: str
    target_branch: str
    status: str
    review_status: str
    review_summary: str | None
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None
    files: list[PRFileOut]
    merge_conflicts: list[MergeConflictOut]
    review_comments: list[ReviewCommentOut]
    reasoning_steps: list[ReasoningStepOut]
