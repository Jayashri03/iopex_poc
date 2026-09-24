"""
Interface the rest of the system codes against. A real pexgit-backed
implementation just needs to satisfy this contract - nothing else in
the agent, jobs, or API layers depends on how PRs/files are actually
fetched.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class CommitFile:
    file_path: str
    change_type: str  # added | modified | deleted
    diff_text: str


@dataclass
class Commit:
    commit_sha: str
    author: str
    message: str
    committed_at: str
    files: list[CommitFile] = field(default_factory=list)


@dataclass
class PullRequest:
    pexgit_pr_id: str
    title: str
    description: str
    author: str
    source_branch: str
    target_branch: str
    status: str
    created_at: str
    updated_at: str
    commits: list[Commit] = field(default_factory=list)


class PexGitAdapter(ABC):
    @abstractmethod
    def list_prs(self) -> list[PullRequest]:
        """Return PR metadata only (no commits) - used for the list endpoint."""

    @abstractmethod
    def get_pr(self, pexgit_pr_id: str) -> PullRequest:
        """Return full PR detail including every commit, in order, with per-file diffs."""

    @abstractmethod
    def list_repo_files(self) -> list[str]:
        """Return all file paths in the target branch's codebase (for the agent's tools)."""

    @abstractmethod
    def get_file_content(self, file_path: str) -> str:
        """Return the full current content of a file on the target branch."""
