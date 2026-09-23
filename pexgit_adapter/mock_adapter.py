import json
import pathlib

from pexgit_adapter.base import PexGitAdapter, PullRequest, PRFile

FIXTURES_DIR = pathlib.Path(__file__).resolve().parent / "fixtures"
REPO_DIR = FIXTURES_DIR / "repo"
PRS_FILE = FIXTURES_DIR / "prs.json"


class MockPexGitAdapter(PexGitAdapter):
    """
    Fixture-backed stand-in for the real pexgit integration. Swap this out
    for an HTTP-based adapter later without touching the RAG index, agent,
    jobs, or API layers - they only depend on pexgit_adapter/base.py.
    """

    def __init__(self):
        self._prs_raw = json.loads(PRS_FILE.read_text(encoding="utf-8"))

    def list_prs(self) -> list[PullRequest]:
        return [self._to_pr(raw) for raw in self._prs_raw]

    def get_pr(self, pexgit_pr_id: str) -> PullRequest:
        for raw in self._prs_raw:
            if raw["pexgit_pr_id"] == pexgit_pr_id:
                return self._to_pr(raw)
        raise KeyError(f"No PR found with id {pexgit_pr_id}")

    def list_repo_files(self) -> list[str]:
        return [
            str(p.relative_to(REPO_DIR)).replace("\\", "/")
            for p in REPO_DIR.rglob("*.py")
        ]

    def get_file_content(self, file_path: str) -> str:
        full_path = REPO_DIR / file_path
        if not full_path.exists():
            raise FileNotFoundError(file_path)
        return full_path.read_text(encoding="utf-8")

    @staticmethod
    def _to_pr(raw: dict) -> PullRequest:
        return PullRequest(
            pexgit_pr_id=raw["pexgit_pr_id"],
            title=raw["title"],
            description=raw["description"],
            author=raw["author"],
            source_branch=raw["source_branch"],
            target_branch=raw["target_branch"],
            status=raw["status"],
            created_at=raw["created_at"],
            updated_at=raw["updated_at"],
            files=[
                PRFile(
                    file_path=f["file_path"],
                    change_type=f["change_type"],
                    diff_text=f["diff_text"],
                )
                for f in raw.get("files", [])
            ],
        )
