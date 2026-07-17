"""Search domain-specific runbooks via pgvector for the Investigator agent."""
from __future__ import annotations

from typing import Annotated

from langchain_core.tools import InjectedToolArg, tool

from app.tools.search_local_docs import search_local_docs


@tool
def search_runbooks(
    query: str,
    k: int = 3,
    *,
    domain: Annotated[str, InjectedToolArg] = "support",
) -> list[dict]:
    """Search internal runbooks for troubleshooting steps relevant to a query. Use this to find standard operating procedures for known issues."""
    table = "runbooks_" + domain.replace("-", "_")
    return search_local_docs.invoke({"query": query, "k": k, "table": table})


if __name__ == "__main__":
    print(search_runbooks.invoke({"query": "MFA loop", "k": 3, "domain": "support"}))
