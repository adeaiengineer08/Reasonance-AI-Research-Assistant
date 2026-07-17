"""Scratch demo: chunk two IAM doc paragraphs, embed, compare cosine similarity."""
from pathlib import Path

from langchain.embeddings import init_embeddings

path = Path(__file__).resolve().parents[2] / "data/sample-corpus/aws-docs/iam-rotation.md"
chunks = [c.strip() for c in path.read_text().split("\n\n") if c.strip()][:2]

embedder = init_embeddings("bedrock:amazon.titan-embed-text-v2:0")
vecs = embedder.embed_documents(chunks)


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb)


print(f"chunk 0: {chunks[0][:72]}...")
print(f"chunk 1: {chunks[1][:72]}...")
print(f"cosine similarity: {cosine(vecs[0], vecs[1]):.4f}")
