"""
Builds the commit-history block that gets dropped into the agent's prompt.

Phase 1 design: every commit's message + diffs for a PR is passed to the
agent in a single shot - no RAG, no chunking. This is simple and gives the
model true cross-commit context (an issue introduced in commit 2 and only
half-fixed in commit 5 is visible in one place), which batching would lose.

The tradeoff is the context window. A PR with hundreds of commits won't fit.
Rather than silently truncate (which would hide the exact failure mode we
built this to catch - cross-commit issues) or silently proceed over budget,
`build_commit_context` raises `CommitContextTooLarge` so the caller can make
an explicit decision. Phase 2 is where that decision becomes real: batch
commits into groups, review each group, then run a second aggregation pass
over the per-batch summaries to catch cross-batch issues. That aggregation
step is exactly what determines how much cross-commit context survives
batching, so it needs its own design rather than being bolted on here.
"""
from dataclasses import dataclass

from config import config
from pexgit_adapter.base import PullRequest


class CommitContextTooLarge(Exception):
    def __init__(self, char_count: int, limit: int):
        self.char_count = char_count
        self.limit = limit
        super().__init__(
            f"Commit history is {char_count} chars, over the {limit} char "
            "single-shot budget (MAX_COMMIT_CONTEXT_CHARS). Batching/aggregation "
            "for large PRs is a phase 2 feature - not implemented yet."
        )


@dataclass
class CommitContext:
    text: str
    char_count: int
    commit_count: int


def format_commits(pr: PullRequest) -> str:
    blocks = []
    for i, commit in enumerate(pr.commits, start=1):
        file_blocks = "\n".join(
            f"  --- {f.file_path} ({f.change_type}) ---\n{f.diff_text}" for f in commit.files
        )
        blocks.append(
            f"Commit {i}/{len(pr.commits)} [{commit.commit_sha}] by {commit.author} "
            f"at {commit.committed_at}\nMessage: {commit.message}\n{file_blocks}"
        )
    return "\n\n".join(blocks)


def build_commit_context(pr: PullRequest) -> CommitContext:
    text = format_commits(pr)
    char_count = len(text)

    if char_count > config.MAX_COMMIT_CONTEXT_CHARS:
        raise CommitContextTooLarge(char_count, config.MAX_COMMIT_CONTEXT_CHARS)

    return CommitContext(text=text, char_count=char_count, commit_count=len(pr.commits))
