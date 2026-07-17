import sqlite3
from collections.abc import AsyncGenerator
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.state import ResearchState


def guard_node(state: ResearchState) -> dict:
    """Post-writer citation guard: flags any URL not backed by findings."""
    from app.guardrails import validate_citations

    allowed_urls = {f["evidence_url"] for f in state["findings"] if f.get("evidence_url")}
    ok, bad_urls = validate_citations(state["report"], allowed_urls)
    report = state["report"]
    step_log: list[str] = []
    if not ok:
        report = f"> WARNING: hallucinated citations detected: {bad_urls}\n\n{report}"
        step_log.append(f"Guard: flagged {len(bad_urls)} bad URL(s)")
    else:
        step_log.append("Guard: all citations valid")
    return {"report": report, "step_log": step_log}


def _build_state_graph() -> StateGraph:
    from app.memory import extract_node, recall_node
    from app.nodes.planner import planner_node
    from app.nodes.researcher import researcher_node
    from app.nodes.writer import writer_node

    graph = StateGraph(ResearchState)
    graph.add_node("recall", recall_node)
    graph.add_node("planner", planner_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("writer", writer_node)
    graph.add_node("guard", guard_node)
    graph.add_node("extract", extract_node)
    graph.add_edge(START, "recall")
    graph.add_edge("recall", "planner")
    graph.add_edge("planner", "researcher")
    graph.add_edge("researcher", "writer")
    graph.add_edge("writer", "guard")
    graph.add_edge("guard", "extract")
    graph.add_edge("extract", END)
    return graph


def build_graph():
    from langgraph.checkpoint.sqlite import SqliteSaver

    graph = _build_state_graph()
    conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
    saver = SqliteSaver(conn)
    return graph.compile(checkpointer=saver)


async def stream_research(question: str, thread_id: str) -> AsyncGenerator[dict[str, Any], None]:
    graph = _build_state_graph()
    saver = MemorySaver()
    app = graph.compile(checkpointer=saver)
    async for event in app.astream_events(
        {
            "question": question,
            "user_id": thread_id,
            "memories": [],
            "sub_questions": [],
            "findings": [],
            "report": "",
            "step_log": [],
        },
        config={"configurable": {"thread_id": thread_id}},
        version="v2",
    ):
        yield event
