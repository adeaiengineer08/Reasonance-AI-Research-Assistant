"""Web search tool using Tavily."""
from __future__ import annotations

import os

from langchain_core.tools import tool


@tool
def web_search(query: str, k: int = 5) -> list[dict]:
    """Search the web for current information on a topic. Returns up to k results each with title, url, and content."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return [{"title": "mock", "url": "https://example.com", "content": query}]

    try:
        from tavily import TavilyClient
    except ImportError:
        return [{"title": "mock (tavily not installed)", "url": "https://example.com", "content": query}]

    client = TavilyClient(api_key=api_key)
    resp = client.search(query=query, max_results=k)
    return [
        {"title": r["title"], "url": r["url"], "content": r["content"]}
        for r in resp.get("results", [])
    ]


if __name__ == "__main__":
    print(web_search.invoke({"query": "LangGraph tutorial", "k": 3}))
