"""Citation-validation utilities for the research report."""
from __future__ import annotations

import re


def extract_urls(text: str) -> set[str]:
    """Find all URLs in markdown [text](url) patterns and bare https://... patterns."""
    urls: set[str] = set()
    for match in re.finditer(r"\[.*?\]\((https?://[^\s)]+)\)", text):
        urls.add(match.group(1))
    for match in re.finditer(r"(?<!\()(https?://[^\s)>]+)", text):
        urls.add(match.group(1))
    return urls


def validate_citations(
    report: str, allowed_urls: set[str]
) -> tuple[bool, list[str]]:
    """Return (ok, bad_urls) — True when every URL in the report is allowed."""
    report_urls = extract_urls(report)
    bad = sorted(report_urls - allowed_urls)
    return (len(bad) == 0, bad)
