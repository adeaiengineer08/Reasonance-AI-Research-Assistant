import logging
import os

from bedrock_agentcore import BedrockAgentCoreApp

logger = logging.getLogger(__name__)
app = BedrockAgentCoreApp()

_graph = None


def _build_graph():
    from langgraph.checkpoint.memory import MemorySaver

    from app.ticket_graph import build_graph_with_backends

    backend = os.getenv("MONK_CHECKPOINTER", "postgres").strip().lower()
    if backend == "memory":
        logger.info("Using MemorySaver checkpointer for AgentCore runtime")
        return build_graph_with_backends(saver=MemorySaver(), store=None)

    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.store.postgres import PostgresStore

    dsn = os.environ["POSTGRES_DSN"]
    saver_cm = PostgresSaver.from_conn_string(dsn)
    saver = saver_cm.__enter__()
    saver.setup()
    store_cm = PostgresStore.from_conn_string(dsn)
    store = store_cm.__enter__()
    if hasattr(store, "setup"):
        store.setup()
    logger.info("Using Postgres checkpointer for AgentCore runtime")
    return build_graph_with_backends(saver=saver, store=store)


@app.entrypoint
async def handler(payload, context):
    yield {"status": "starting", "session_id": context.session_id}

    global _graph
    if _graph is None:
        _graph = _build_graph()

    config = {
        "configurable": {"thread_id": context.session_id},
        "recursion_limit": 50,
    }
    async for event in _graph.astream_events(payload, config=config, version="v2"):
        yield event
