"""Writer node: produces a markdown research report from findings."""
from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.state import ResearchState
from app.llm import get_chat_model

SYSTEM_PROMPT = (
    "You are writing a research report. Produce a markdown report with: "
    "1) a 2-3 sentence executive summary, "
    "2) one H2 section per sub-question, "
    "3) inline [n] citations after each factual claim, "
    "4) a numbered Sources section at the end listing each unique URL once. "
    "Never invent a URL or fact - only use the supplied findings."
)


def _extract_urls_from_report(report: str) -> set[str]:
    """Extract all URLs from markdown links and the Sources section."""
    urls: set[str] = set()
    # Markdown links: [text](url)
    for match in re.finditer(r"\[.*?\]\((https?://[^\s)]+)\)", report):
        urls.add(match.group(1))
    # Bare URLs in the Sources section (lines starting with a number)
    in_sources = False
    for line in report.splitlines():
        if re.match(r"^#+\s*Sources", line, re.IGNORECASE):
            in_sources = True
            continue
        if in_sources:
            if line.startswith("#"):
                break
            for match in re.finditer(r"(https?://[^\s)>]+)", line):
                urls.add(match.group(1))
    return urls


def writer_node(state: ResearchState) -> dict:
    model = get_chat_model()

    payload = json.dumps(
        {
            "question": state["question"],
            "sub_questions": state["sub_questions"],
            "findings": state["findings"],
        },
        indent=2,
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=payload),
    ]

    ai_msg = model.invoke(messages)
    content = ai_msg.content
    if isinstance(content, str):
        report = content
    elif isinstance(content, list):
        report = "".join(
            block.get("text", "") if isinstance(block, dict) and block.get("type") == "text"
            else block if isinstance(block, str)
            else ""
            for block in content
        )
    else:
        report = str(content)

    # Post-process: validate citations against allowed URLs from findings
    allowed_urls = {f["evidence_url"] for f in state["findings"] if f.get("evidence_url")}
    report_urls = _extract_urls_from_report(report)
    bad_urls = report_urls - allowed_urls

    if bad_urls:
        report += f"\n\n> WARNING: filtered hallucinated citations: {sorted(bad_urls)}"

    step_log = state["step_log"] + ["Writer: report drafted"]
    return {"report": report, "step_log": step_log}
