"""Evaluate the triage agent over every ticket in eval/labelled_tickets.csv with mlflow.genai.evaluate.

Usage: uv run python eval/run_eval.py   (PROVIDER=groq to run the agent on Groq)

Logs one MLflow run to the triage-agent experiment in sqlite:///mlflow.db, one trace per ticket,
scored by four code scorers: valid_schema, category_match, priority_match and tool_order.
"""

import asyncio
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# `uv run python eval/run_eval.py` puts eval/ on sys.path, not the repo root.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mlflow  # noqa: E402
from mlflow.entities import Trace  # noqa: E402
from mlflow.genai.scorers import scorer  # noqa: E402
from pydantic import ValidationError  # noqa: E402

import agent  # noqa: E402
from triage_schema import TriageDecision  # noqa: E402

LABELS_PATH = ROOT / "eval" / "labelled_tickets.csv"
TRACKING_URI = "sqlite:///mlflow.db"
EXPERIMENT = "triage-agent"


def build_data(path: Path = LABELS_PATH) -> list[dict]:
    """One evaluate row per labelled ticket: inputs for predict_fn, expectations for the scorers."""
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [
        {
            "inputs": {"ticket_id": row["ticket_id"]},
            "expectations": {
                "expected_category": row["expected_category"],
                "expected_priority": row["expected_priority"],
                "expected_tools": [t.strip() for t in row["expected_tools"].split(",") if t.strip()],
                "judge_notes": row["judge_notes"],
            },
        }
        for row in rows
    ]


@mlflow.trace(name="triage", span_type="AGENT")
def predict_fn(ticket_id: str) -> dict:
    """Triage one ticket with the agent as-is. The autologged model and tool spans nest under this trace."""
    return asyncio.run(agent.triage(ticket_id))


@scorer
def valid_schema(outputs) -> int:
    """1 when the output validates as a TriageDecision, else 0."""
    if outputs is None:
        return 0
    try:
        TriageDecision.model_validate(outputs)
    except (ValidationError, TypeError, ValueError):
        return 0
    return 1


def _field_matches(outputs, expected, field: str) -> int:
    if not isinstance(outputs, dict) or not isinstance(expected, dict):
        return 0
    return int(outputs.get(field) is not None and outputs.get(field) == expected.get(f"expected_{field}"))


@scorer
def category_match(outputs, expectations) -> int:
    """1 when the output's category equals expected_category, else 0."""
    return _field_matches(outputs, expectations, "category")


@scorer
def priority_match(outputs, expectations) -> int:
    """1 when the output's priority equals expected_priority, else 0."""
    return _field_matches(outputs, expectations, "priority")


@scorer
def tool_order(trace: Trace) -> int:
    """1 when the trace has a get_ticket span starting before the first get_customer_history span, else 0.

    A failed prediction (an ERROR trace) scores 0 even if both tools ran, so a failing row scores 0 everywhere.
    """
    if trace is None:
        return 0
    try:
        if trace.info.state.value == "ERROR":
            return 0
        tickets = trace.search_spans(name="get_ticket")
        histories = trace.search_spans(name="get_customer_history")
    except Exception:
        return 0
    if not tickets or not histories:
        return 0
    first_ticket = min(s.start_time_ns for s in tickets)
    first_history = min(s.start_time_ns for s in histories)
    return int(first_ticket < first_history)


SCORERS = [valid_schema, category_match, priority_match, tool_order]


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    # One ticket at a time: avoids parallel MCP servers and provider rate limits.
    os.environ.setdefault("MLFLOW_GENAI_EVAL_MAX_WORKERS", "1")
    # predict_fn is already traced; skip evaluate's extra untraced validation call.
    os.environ.setdefault("MLFLOW_GENAI_EVAL_SKIP_TRACE_VALIDATION", "true")

    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT)
    mlflow.langchain.autolog()

    result = mlflow.genai.evaluate(data=build_data(), scorers=SCORERS, predict_fn=predict_fn)
    print(f"Eval run ID: {result.run_id}")


if __name__ == "__main__":
    main()
