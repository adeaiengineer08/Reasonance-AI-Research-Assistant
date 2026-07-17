"""Episodic memory: similar past ticket resolutions via pgvector."""
from __future__ import annotations

import os

import psycopg

from app.llm import get_embeddings

DEFAULT_DSN = "postgresql://postgres:postgres@localhost:5433/monk"


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def similar_past_cases(ticket_text: str, domain: str, k: int = 3) -> list[dict]:
    """Return the k most similar past resolutions for a given ticket and domain."""
    dsn = os.getenv("POSTGRES_DSN", DEFAULT_DSN)
    embedder = get_embeddings()
    vec_lit = _vec_literal(embedder.embed_query(ticket_text))

    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, ticket_text, resolution_text,
                       1 - (embedding <=> %s::vector) AS score
                FROM past_resolutions
                WHERE domain = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (vec_lit, domain, vec_lit, k),
            )
            rows = cur.fetchall()
    except Exception:
        return []

    return [
        {
            "id": row_id,
            "ticket_text": ticket,
            "resolution_text": resolution,
            "score": float(score),
        }
        for row_id, ticket, resolution, score in rows
    ]
