"""Ticket triage graph — slim import surface for AgentCore and production deploy."""

from langgraph.graph import END, START, StateGraph

from app.state import TicketState


def _build_ticket_state_graph() -> StateGraph:
    from app.agents.investigator import investigator_node
    from app.agents.responder import responder_node
    from app.agents.send import send_node
    from app.agents.supervisor import supervisor_node
    from app.agents.triager import triager_node
    from app.hitl import hitl_node

    graph = StateGraph(TicketState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("triager", triager_node)
    graph.add_node("investigator", investigator_node)
    graph.add_node("responder", responder_node)
    graph.add_node("hitl", hitl_node)
    graph.add_node("send", send_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        lambda s: s["next"],
        {
            "triager": "triager",
            "investigator": "investigator",
            "responder": "responder",
            "hitl": "hitl",
            "send": "send",
            "END": END,
        },
    )
    for worker in ("triager", "investigator", "responder", "hitl", "send"):
        graph.add_edge(worker, "supervisor")
    return graph


def build_graph_with_backends(saver, store=None):
    """Compile the ticket triage graph with injected checkpointer/store backends."""
    graph = _build_ticket_state_graph()
    return graph.compile(checkpointer=saver, store=store)
