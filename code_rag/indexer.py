import json

from code_rag.chunker import chunk_file
from code_rag.embeddings import embed_text
from db.connection import get_cursor
from pexgit_adapter.base import PexGitAdapter


def build_index(adapter: PexGitAdapter) -> int:
    """
    Chunk + embed every file in the codebase and (re)write it into
    code_chunks. Safe to re-run: existing chunks for a file are replaced.
    """
    total_chunks = 0
    for file_path in adapter.list_repo_files():
        content = adapter.get_file_content(file_path)
        chunks = chunk_file(content)

        with get_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM code_chunks WHERE file_path = %s", (file_path,))
            for idx, chunk in enumerate(chunks):
                embedding = embed_text(chunk)
                cursor.execute(
                    """
                    INSERT INTO code_chunks (file_path, chunk_index, content, embedding)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (file_path, idx, chunk, json.dumps(embedding)),
                )
        total_chunks += len(chunks)
    return total_chunks
