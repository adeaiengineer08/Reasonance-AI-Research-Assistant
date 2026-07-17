from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class S(TypedDict):
    q: str
    a: str


def respond(state: S) -> dict:
    return {"a": f"You asked: {state['q']}"}


g = StateGraph(S)
g.add_node("respond", respond)
g.add_edge(START, "respond")
g.add_edge("respond", END)
app = g.compile()

if __name__ == "__main__":
    from dotenv import load_dotenv
    from langsmith import trace

    load_dotenv()
    with trace(name="tiny_graph") as run:
        print(app.invoke({"q": "hello"}))
    print(run.get_url())
