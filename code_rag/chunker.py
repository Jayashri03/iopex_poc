def chunk_file(content: str, max_lines: int = 40, overlap: int = 5) -> list[str]:
    """
    Fixed-size line chunking with overlap. Good enough for a POC codebase;
    swap for an AST/function-boundary chunker if files get large or dense.
    """
    lines = content.splitlines()
    if not lines:
        return []

    chunks = []
    start = 0
    while start < len(lines):
        end = min(start + max_lines, len(lines))
        chunk = "\n".join(lines[start:end])
        if chunk.strip():
            chunks.append(chunk)
        if end == len(lines):
            break
        start = end - overlap
    return chunks
