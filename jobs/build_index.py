"""Offline job: (re)build the code-RAG index from the target branch codebase."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from code_rag.indexer import build_index  # noqa: E402
from pexgit_adapter.mock_adapter import MockPexGitAdapter  # noqa: E402


def main():
    adapter = MockPexGitAdapter()
    total = build_index(adapter)
    print(f"Indexed {total} chunks across {len(adapter.list_repo_files())} files.")


if __name__ == "__main__":
    main()
