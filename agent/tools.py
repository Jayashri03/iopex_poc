import re

from pexgit_adapter.base import PexGitAdapter

MAX_OBSERVATION_CHARS = 2000
MAX_MATCHES = 20


def _truncate(text: str) -> str:
    return text if len(text) <= MAX_OBSERVATION_CHARS else text[:MAX_OBSERVATION_CHARS] + "\n...[truncated]"


def build_tools(adapter: PexGitAdapter) -> dict:
    """
    Returns {tool_name: {"description": str, "func": callable(**kwargs) -> str}}.
    Descriptions are injected verbatim into the agent's system prompt.

    No RAG/embeddings here - the PR's own commit history is already in the
    prompt. These tools exist only to pull in codebase context the diffs
    alone don't show (e.g. "is there already a similar function?", "what
    does the rest of this file look like around the hunk?").
    """

    def list_files_tool() -> str:
        return "\n".join(adapter.list_repo_files())

    def get_file_tool(file_path: str) -> str:
        try:
            return _truncate(adapter.get_file_content(file_path))
        except FileNotFoundError:
            return f"File not found: {file_path}"

    def search_repo_tool(pattern: str) -> str:
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            return f"Invalid regex '{pattern}': {exc}"

        matches = []
        for file_path in adapter.list_repo_files():
            content = adapter.get_file_content(file_path)
            for line_no, line in enumerate(content.splitlines(), start=1):
                if regex.search(line):
                    matches.append(f"{file_path}:{line_no}: {line.strip()}")
                    if len(matches) >= MAX_MATCHES:
                        break
            if len(matches) >= MAX_MATCHES:
                break

        if not matches:
            return f"No matches for pattern '{pattern}'."
        return _truncate("\n".join(matches))

    return {
        "list_files": {
            "description": (
                "List every file path in the target branch's codebase. Args: {} "
                "(no arguments). Use this to see what's available before deciding "
                "what to search or read."
            ),
            "func": list_files_tool,
        },
        "search_repo": {
            "description": (
                "Plain-text/regex search (like grep) across every file in the "
                "codebase. Args: {\"pattern\": string}. Use this to check whether "
                "similar logic already exists elsewhere (duplication) or to find "
                "where a function/symbol touched by the PR is used or defined."
            ),
            "func": search_repo_tool,
        },
        "get_file": {
            "description": (
                "Fetch the full current content of one file on the target branch. "
                "Args: {\"file_path\": string}. Use this when a diff hunk needs "
                "surrounding context that isn't in the hunk itself."
            ),
            "func": get_file_tool,
        },
    }
