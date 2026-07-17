"""Vector search over ingested document chunks stored in pgvector."""
from __future__ import annotations

import os
import re

import psycopg
from langchain.embeddings import init_embeddings
from langchain_core.tools import tool

DEFAULT_DSN = "postgresql://postgres:postgres@localhost:5433/monk"
DEFAULT_EMBEDDINGS = "bedrock:amazon.titan-embed-text-v2:0"


def _sanitize_table(table: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        raise ValueError(f"invalid table name: {table!r}")
    return table


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


@tool
def search_local_docs(query: str, k: int = 5, table: str = "docs") -> list[dict]:
    """Search the ingested document corpus for content relevant to a query. Use this when the user asks about content in our internal documentation. Returns a list of citations each with a real source_url that you MUST cite back."""
    table = _sanitize_table(table)
    dsn = os.getenv("POSTGRES_DSN", DEFAULT_DSN)
    embedder = init_embeddings(os.getenv("MONK_EMBEDDINGS", DEFAULT_EMBEDDINGS))
    vec_lit = _vec_literal(embedder.embed_query(query))

    with psycopg.connect(dsn, connect_timeout=5) as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT chunk_id, source_url, 1 - (embedding <=> %s::vector) AS score, text
            FROM {table}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (vec_lit, vec_lit, k),
        )
        rows = cur.fetchall()

    return [
        {"chunk_id": str(chunk_id), "source_url": source_url, "score": float(score), "text": text}
        for chunk_id, source_url, score, text in rows
    ]
