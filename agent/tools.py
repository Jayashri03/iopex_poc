from code_rag.retriever import search_code
from pexgit_adapter.base import PexGitAdapter

MAX_OBSERVATION_CHARS = 2000


def _truncate(text: str) -> str:
    return text if len(text) <= MAX_OBSERVATION_CHARS else text[:MAX_OBSERVATION_CHARS] + "\n...[truncated]"


def build_tools(adapter: PexGitAdapter) -> dict:
    """
    Returns {tool_name: {"description": str, "func": callable(**kwargs) -> str}}.
    Descriptions are injected verbatim into the agent's system prompt, so the
    model knows what each tool does and what arguments it takes.
    """

    def search_code_tool(query: str, top_k: int = 5) -> str:
        results = search_code(query, top_k=top_k)
        if not results:
            return "No matching code found."
        lines = []
        for r in results:
            lines.append(f"[{r.file_path}#chunk{r.chunk_index} score={r.score:.3f}]\n{r.content}")
        return _truncate("\n\n".join(lines))

    def get_file_tool(file_path: str) -> str:
        try:
            return _truncate(adapter.get_file_content(file_path))
        except FileNotFoundError:
            return f"File not found: {file_path}"

    return {
        "search_code": {
            "description": (
                "Semantic search over the current codebase (RAG). Args: "
                "{\"query\": string, \"top_k\": int (optional)}. Use this to find "
                "similar/existing functions, check for duplication, or pull in "
                "context the diff alone doesn't show."
            ),
            "func": search_code_tool,
        },
        "get_file": {
            "description": (
                "Fetch the full current content of a file on the target branch. "
                "Args: {\"file_path\": string}. Use this when a diff hunk needs "
                "surrounding context (e.g. checking existing validation in a function "
                "being extended)."
            ),
            "func": get_file_tool,
        },
    }
