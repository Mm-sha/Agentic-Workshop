"""Offline tests for eval/run_eval.py: no network, no real model. MLflow writes to a temporary SQLite store."""

import importlib.util
import os
import time
from pathlib import Path

import mlflow
import pytest
from mlflow.tracking import fluent as mlflow_fluent

import agent
import load_seed
from test_agent import ScriptedChatModel, decide, get_customer_step, get_ticket_step

EVAL_ENV_VARS = ("MLFLOW_GENAI_EVAL_MAX_WORKERS", "MLFLOW_GENAI_EVAL_SKIP_TRACE_VALIDATION")
SCORER_NAMES = ("valid_schema", "category_match", "priority_match", "tool_order")

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("run_eval", ROOT / "eval" / "run_eval.py")
run_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_eval)

GOOD = {
    "category": "billing",
    "priority": "P2",
    "route": "billing-team",
    "rationale": "Double charge is a money problem.",
}
EXPECTED = {"expected_category": "billing", "expected_priority": "P2"}


def _isolate_mlflow_state(monkeypatch):
    """Let monkeypatch restore the active experiment and MLflow's env vars when the test ends."""
    monkeypatch.setattr(mlflow_fluent, "_active_experiment_id", None)
    for var in ("MLFLOW_EXPERIMENT_ID", "MLFLOW_TRACKING_URI", *EVAL_ENV_VARS):
        monkeypatch.setenv(var, "")  # records the original value (or its absence) for teardown
        monkeypatch.delenv(var)


@pytest.fixture
def tmp_mlflow(tmp_path, monkeypatch):
    """Point MLflow at a fresh SQLite store in tmp_path; restore the URI and active experiment afterwards."""
    old_uri = mlflow.get_tracking_uri()
    _isolate_mlflow_state(monkeypatch)
    uri = f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}"
    mlflow.set_tracking_uri(uri)
    experiment_id = mlflow.set_experiment("triage-agent-test").experiment_id
    yield experiment_id
    mlflow.set_tracking_uri(old_uri)


# --- build_data --------------------------------------------------------------


def test_build_data_reads_all_20_rows():
    data = run_eval.build_data()
    assert len(data) == 20
    first = data[0]
    assert first["inputs"] == {"ticket_id": "T-1042"}
    assert first["expectations"]["expected_category"] == "billing"
    assert first["expectations"]["expected_priority"] == "P2"
    assert first["expectations"]["expected_tools"] == ["get_ticket", "get_customer_history"]
    assert first["expectations"]["judge_notes"].startswith("Double charge")
    assert len({row["inputs"]["ticket_id"] for row in data}) == 20
    for row in data:
        assert set(row["inputs"]) == {"ticket_id"}
        assert row["expectations"]["expected_category"] in {"billing", "bug", "access", "performance", "how-to"}
        assert row["expectations"]["expected_priority"] in {"P1", "P2", "P3", "P4"}


# --- code scorers ------------------------------------------------------------


def test_valid_schema():
    assert run_eval.valid_schema(outputs=GOOD) == 1
    assert run_eval.valid_schema(outputs={**GOOD, "route": "bug-team"}) == 0  # route doesn't fit the category
    assert run_eval.valid_schema(outputs={"category": "billing"}) == 0
    assert run_eval.valid_schema(outputs="not a dict") == 0
    assert run_eval.valid_schema(outputs=None) == 0


@pytest.mark.parametrize(("name", "field", "wrong"), [("category_match", "category", "bug"), ("priority_match", "priority", "P1")])
def test_label_matchers(name, field, wrong):
    score = getattr(run_eval, name)
    assert score(outputs=GOOD, expectations=EXPECTED) == 1
    assert score(outputs={**GOOD, field: wrong}, expectations=EXPECTED) == 0
    assert score(outputs={"rationale": "no fields"}, expectations=EXPECTED) == 0  # invalid output
    assert score(outputs="garbage", expectations=EXPECTED) == 0
    assert score(outputs=None, expectations=EXPECTED) == 0


def _trace_with_tools(*tool_names):
    @mlflow.trace(name="triage", span_type="AGENT")
    def run():
        for tool in tool_names:
            with mlflow.start_span(name=tool, span_type="TOOL"):
                time.sleep(0.02)  # Windows clocks can give spans in quick succession the same start time.

    run()
    trace = mlflow.get_trace(mlflow.get_last_active_trace_id(), flush=True)
    assert trace is not None
    return trace


def test_tool_order_in_order(tmp_mlflow):
    assert run_eval.tool_order(trace=_trace_with_tools("get_ticket", "get_customer_history")) == 1


def test_tool_order_reversed(tmp_mlflow):
    assert run_eval.tool_order(trace=_trace_with_tools("get_customer_history", "get_ticket")) == 0


@pytest.mark.parametrize("tools", [("get_ticket",), ("get_customer_history",), ()])
def test_tool_order_missing_tool(tmp_mlflow, tools):
    assert run_eval.tool_order(trace=_trace_with_tools(*tools)) == 0


def test_tool_order_no_trace():
    assert run_eval.tool_order(trace=None) == 0


# --- one evaluate run --------------------------------------------------------


async def fake_triage(ticket_id: str) -> dict:
    """Stands in for agent.triage: makes tool spans and returns a canned decision per ticket.

    T-FAIL calls both tools in order and then raises, like a provider error after the lookups.
    """
    order = ["get_customer_history", "get_ticket"] if ticket_id == "T-REVERSED" else ["get_ticket", "get_customer_history"]
    for tool in order:
        with mlflow.start_span(name=tool, span_type="TOOL"):
            time.sleep(0.02)  # Windows clocks can give spans in quick succession the same start time.
    if ticket_id == "T-FAIL":
        raise agent.TriageError("quota exhausted")
    if ticket_id == "T-WRONG":
        return {"category": "bug", "priority": "P2", "route": "bug-team", "rationale": "Looks like a bug."}
    return dict(GOOD)


def test_evaluate_run(tmp_mlflow, monkeypatch):
    monkeypatch.setenv("MLFLOW_GENAI_EVAL_MAX_WORKERS", "1")
    monkeypatch.setenv("MLFLOW_GENAI_EVAL_SKIP_TRACE_VALIDATION", "true")
    monkeypatch.setattr(agent, "triage", fake_triage)
    data = [
        {"inputs": {"ticket_id": tid}, "expectations": dict(EXPECTED)}
        for tid in ("T-GOOD", "T-WRONG", "T-REVERSED", "T-FAIL")
    ]

    result = mlflow.genai.evaluate(data=data, scorers=run_eval.SCORERS, predict_fn=run_eval.predict_fn)

    runs = mlflow.search_runs(experiment_ids=[tmp_mlflow])
    assert len(runs) == 1
    assert runs.iloc[0]["run_id"] == result.run_id
    assert float(result.metrics["valid_schema/mean"]) == pytest.approx(0.75)
    assert float(result.metrics["category_match/mean"]) == pytest.approx(0.5)
    assert float(result.metrics["priority_match/mean"]) == pytest.approx(0.75)
    assert float(result.metrics["tool_order/mean"]) == pytest.approx(0.5)

    traces = mlflow.search_traces(locations=[tmp_mlflow], run_id=result.run_id, return_type="list")
    assert len(traces) == 4
    failed = [t for t in traces if t.info.state.value == "ERROR"]
    assert len(failed) == 1
    failed = mlflow.get_trace(failed[0].info.trace_id)

    # The failing row scores 0 on all four scorers, tool_order included, though both tools ran.
    scores = {a.name: a.value for a in failed.info.assessments if a.name in SCORER_NAMES}
    assert scores == dict.fromkeys(SCORER_NAMES, 0)

    # The error is kept on the row's trace.
    root = next(s for s in failed.data.spans if s.parent_id is None)
    messages = [e.attributes.get("exception.message", "") for e in root.events if e.name == "exception"]
    assert any("quota exhausted" in m for m in messages)


def test_main_logs_one_run_to_triage_agent(tmp_path, monkeypatch, capsys):
    old_uri = mlflow.get_tracking_uri()
    _isolate_mlflow_state(monkeypatch)  # also deletes both MLFLOW_GENAI_EVAL_* vars
    uri = f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}"
    monkeypatch.setattr(run_eval, "TRACKING_URI", uri)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)  # keep the real .env out of the test
    monkeypatch.setattr(agent, "triage", fake_triage)
    rows = [{"inputs": {"ticket_id": tid}, "expectations": dict(EXPECTED)} for tid in ("T-GOOD", "T-WRONG")]
    monkeypatch.setattr(run_eval, "build_data", lambda: rows)
    seen_env = {}
    real_evaluate = mlflow.genai.evaluate

    def spy_evaluate(**kwargs):
        seen_env.update({var: os.environ.get(var) for var in EVAL_ENV_VARS})
        return real_evaluate(**kwargs)

    monkeypatch.setattr(mlflow.genai, "evaluate", spy_evaluate)
    try:
        run_eval.main()
    finally:
        mlflow.langchain.autolog(disable=True)
        mlflow.set_tracking_uri(old_uri)

    assert seen_env == {"MLFLOW_GENAI_EVAL_MAX_WORKERS": "1", "MLFLOW_GENAI_EVAL_SKIP_TRACE_VALIDATION": "true"}
    client = mlflow.MlflowClient(tracking_uri=uri)
    experiment = client.get_experiment_by_name("triage-agent")
    assert experiment is not None
    runs = client.search_runs([experiment.experiment_id])
    assert len(runs) == 1
    assert float(runs[0].data.metrics["category_match/mean"]) == pytest.approx(0.5)
    assert f"Eval run ID: {runs[0].info.run_id}" in capsys.readouterr().out


def test_tool_order_on_autologged_agent_trace(tmp_mlflow, monkeypatch):
    """The real agent over the real MCP server, with a scripted model: autolog's tool spans pass tool_order."""
    load_seed.load_seed()
    decision = {"category": "billing", "priority": "P2", "route": "billing-team", "rationale": "Double charge, P2."}
    model = ScriptedChatModel(
        steps=[get_ticket_step("T-1042"), get_customer_step, decide(decision, 3)], calls=[], bound_tools=[]
    )
    monkeypatch.setattr(agent, "build_model", lambda: model)
    mlflow.langchain.autolog()
    try:
        assert run_eval.predict_fn("T-1042") == decision
    finally:
        mlflow.langchain.autolog(disable=True)

    trace = mlflow.get_trace(mlflow.get_last_active_trace_id(), flush=True)
    assert trace is not None
    assert trace.search_spans(name="get_ticket") and trace.search_spans(name="get_customer_history")
    assert run_eval.tool_order(trace=trace) == 1
