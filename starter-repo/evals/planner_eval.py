"""Planner-node eval: checks that sub-questions cover the expected topic areas.

Run with:  uv run python -m evals.planner_eval
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from langsmith import Client
from langsmith.evaluation import evaluate
from rich.console import Console

from app.llm import get_chat_model
from app.nodes.planner import planner_node

load_dotenv()
console = Console()

GOLDEN_PATH = Path(__file__).parent / "golden.jsonl"
DATASET_NAME = "planner-golden"
PASS_THRESHOLD = 0.5


def _load_golden() -> list[dict]:
    rows = []
    with open(GOLDEN_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _ensure_dataset(client: Client, golden: list[dict]) -> str:
    """Create or update the LangSmith dataset, return its name."""
    try:
        ds = client.read_dataset(dataset_name=DATASET_NAME)
    except Exception:
        ds = client.create_dataset(dataset_name=DATASET_NAME)

    existing = list(client.list_examples(dataset_id=ds.id))
    if len(existing) != len(golden):
        for ex in existing:
            client.delete_example(ex.id)
        for row in golden:
            client.create_example(
                dataset_id=ds.id,
                inputs={
                    "question": row["question"],
                    "expected_sections": row["expected_sections"],
                },
                outputs={
                    "expected_sections": row["expected_sections"],
                    "min_citations": row["min_citations"],
                },
            )
    return DATASET_NAME


def _extract_text(content) -> str:
    """Extract the visible text from a model response content field.

    Reasoning models (e.g. gpt-oss-120b) return content as a list of typed
    blocks.  We want only the 'text' blocks, not 'reasoning_content'.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(content)


def _parse_score(raw: str) -> float:
    """Pull a 0.0-1.0 float from the model's textual reply."""
    raw = raw.strip()
    try:
        return float(raw)
    except ValueError:
        pass
    numbers = re.findall(r"\d+\.\d+|\d+", raw)
    for n in numbers:
        val = float(n)
        if 0.0 <= val <= 1.0:
            return val
    return 0.0


def _target(inputs: dict) -> dict:
    """Run the planner node in isolation and return its output."""
    state = {
        "question": inputs["question"],
        "sub_questions": [],
        "findings": [],
        "report": "",
        "step_log": [],
    }
    result = planner_node(state)
    return {"sub_questions": result.get("sub_questions", [])}


def _judge_once(judge, sq_texts: list[str], expected: list[str]) -> float:
    """Single judge call — returns a 0.0-1.0 score."""
    prompt = (
        f"Given the sub-questions {sq_texts} and the expected coverage areas "
        f"{expected}, return a number 0.0-1.0 representing how well the "
        f"sub-questions cover the expected areas. Return only a number."
    )
    resp = judge.invoke(prompt)
    text = _extract_text(resp.content)
    return max(0.0, min(1.0, _parse_score(text)))


def _coverage_evaluator(run, example) -> dict:
    """LLM-as-judge: score how well sub-questions cover the expected sections."""
    sqs = run.outputs.get("sub_questions", [])
    expected = example.inputs.get("expected_sections", [])

    sq_texts = [sq.get("text", "") for sq in sqs] if sqs else []

    judge = get_chat_model()
    scores = [_judge_once(judge, sq_texts, expected) for _ in range(2)]
    score = max(scores)
    return {"key": "coverage", "score": score}


def main() -> int:
    golden = _load_golden()
    console.rule("[bold orange1]Planner Eval[/]")
    console.print(f"Loaded {len(golden)} golden rows from {GOLDEN_PATH.name}\n")

    client = Client()
    dataset_name = _ensure_dataset(client, golden)
    console.print(f"LangSmith dataset: [cyan]{dataset_name}[/]\n")

    results = evaluate(
        _target,
        data=dataset_name,
        evaluators=[_coverage_evaluator],
        experiment_prefix="planner-coverage",
        description="Planner sub-question coverage vs golden expected sections",
        max_concurrency=2,
        client=client,
    )

    scores = []
    for i, result in enumerate(results):
        eval_results = result.get("evaluation_results", {})
        eval_list = eval_results.get("results", []) if isinstance(eval_results, dict) else []
        score = None
        for er in eval_list:
            if hasattr(er, "score"):
                score = er.score
                break
        if score is None:
            score = 0.0
        scores.append(score)
        status = "[green]PASS[/]" if score >= PASS_THRESHOLD else "[red]FAIL[/]"
        q = golden[i]["question"][:70] if i < len(golden) else "?"
        console.print(f"  {status}  {score:.2f}  {q}")

    avg = sum(scores) / len(scores) if scores else 0.0
    passed = sum(1 for s in scores if s >= PASS_THRESHOLD)
    console.print(f"\n[bold]Aggregate:[/] {passed}/{len(scores)} passed, avg score {avg:.2f}")

    if avg < PASS_THRESHOLD:
        console.print("[bold red]Overall FAIL[/]")
        return 1
    console.print("[bold green]Overall PASS[/]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
