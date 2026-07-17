"""Fetch and extract text content from a URL."""
from __future__ import annotations

import httpx
from bs4 import BeautifulSoup
from langchain_core.tools import tool

_USER_AGENT = "Mozilla/5.0 (compatible; MonkResearchBot/1.0)"
_MAX_CHARS = 8000


@tool
def fetch_url(url: str) -> str:
    """Fetch a web page and return its text content. Use this to read the full content of a URL found by web_search."""
    try:
        resp = httpx.get(url, timeout=10, headers={"User-Agent": _USER_AGENT}, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        return f"[Source: {url}]\nError fetching URL: {e}"
    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text(separator="\n", strip=True)[:_MAX_CHARS]
    return f"[Source: {url}]\n{text}"


if __name__ == "__main__":
    print(fetch_url.invoke({"url": "https://example.com"}))
