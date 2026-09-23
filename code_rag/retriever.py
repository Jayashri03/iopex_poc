import json
from dataclasses import dataclass

import numpy as np

from code_rag.embeddings import embed_text
from config import config
from db.connection import get_cursor


@dataclass
class RetrievedChunk:
    file_path: str
    chunk_index: int
    content: str
    score: float


def search_code(query: str, top_k: int = None) -> list[RetrievedChunk]:
    """
    Brute-force cosine similarity over all indexed chunks. MySQL has no
    native vector search here, so we pull embeddings into numpy and rank
    in Python - fine at POC scale (hundreds to low thousands of chunks).
    """
    top_k = top_k or config.RAG_TOP_K
    query_vec = np.array(embed_text(query), dtype=np.float32)

    with get_cursor() as cursor:
        cursor.execute("SELECT file_path, chunk_index, content, embedding FROM code_chunks")
        rows = cursor.fetchall()

    if not rows:
        return []

    matrix = np.array([json.loads(r["embedding"]) for r in rows], dtype=np.float32)
    query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-8)
    matrix_norm = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8)
    scores = matrix_norm @ query_norm

    ranked_idx = np.argsort(-scores)[:top_k]
    return [
        RetrievedChunk(
            file_path=rows[i]["file_path"],
            chunk_index=rows[i]["chunk_index"],
            content=rows[i]["content"],
            score=float(scores[i]),
        )
        for i in ranked_idx
    ]
