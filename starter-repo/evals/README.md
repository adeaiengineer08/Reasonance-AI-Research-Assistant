# Evals

Eval scripts for Project 1 (Research Assistant):

- `golden.jsonl` - the golden dataset.
- `planner_eval.py` - planner node eval.
- Additional Project 1 evals (`citation_eval.py`, `e2e_eval.py`) as added in class.

We use **LangSmith** as the eval backbone. Each script:

1. Loads a golden dataset.
2. Runs the agent / node against each row.
3. Scores with a mix of programmatic checks and LLM-as-judge.
4. Uploads to LangSmith as an experiment for side-by-side comparison.
