---
title: 'The eval run and the four code scorers'
type: 'feature'
created: '2026-09-26'
status: 'done'
baseline_commit: 'db612ce0680406b7f743ef32455f09bd8fb77c81'
route: 'dispatch'
review_loop_iteration: 0
context: ['{project-root}/_bmad-output/specs/spec-epic-3/SPEC.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing measures the Epic 2 agent. There is no eval run over the 20 labelled tickets and no scores (SPEC-epic-3 CAP-1–CAP-5).

**Approach:** Add `eval/run_eval.py`. `uv run python eval/run_eval.py` runs the existing `agent.triage` on every row of `eval/labelled_tickets.csv` through `mlflow.genai.evaluate`, and logs exactly one MLflow run to the `triage-agent` experiment in `sqlite:///mlflow.db`. Four code scorers are attached: `valid_schema`, `category_match`, `priority_match` and `tool_order`.

**Decision (2026-09-26, user):** CAP-8, auto-approving escalations, is split out and logged in `deferred-work.md`. Escalation (Epic 2 story 2) isn't built yet, so there is nothing to approve. The rationale judge and the printed report with `eval/latest_report.json` are Epic 3 story 2.

## Boundaries & Constraints

**Always:** Use `mlflow.genai.evaluate`, not a hand-rolled loop. Each ticket's prediction is a single trace (`@mlflow.trace` on the predict function). Call the agent as-is through `triage(ticket_id)`. Set up MLflow the same way as `run_agent.py`: tracking URI `sqlite:///mlflow.db`, experiment `triage-agent`, `mlflow.langchain.autolog()`. The four scorers run locally on schema, label and trace data, and return 0/1.

**Never:** Change `agent.py`, `triage_schema.py`, `TRIAGE_POLICY.md`, `eval/labelled_tickets.csv` or anything under `seed/`. No LLM judge, no printed means, no `eval/latest_report.json` (story 2). No escalation handling (deferred). No new dependency. No real model call in `uv run pytest`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Full run | 20 labelled rows, working provider | One MLflow run in `triage-agent`, 20 traces, each scored by the 4 scorers | N/A |
| Correct decision | Output matches the label, valid schema, tools in order | All 4 scorers give 1 | N/A |
| Wrong category or priority | Output differs from the label | `category_match` / `priority_match` give 0 | N/A |
| Invalid output | Output fails `TriageDecision` | `valid_schema` gives 0 | N/A |
| Tools out of order or missing | `get_customer_history` first, or a tool span missing | `tool_order` gives 0 | N/A |
| Agent fails on a ticket | `triage()` raises (for example quota or network) | Run continues; that row scores 0 on all 4 scorers | Error kept on the row, run not aborted |

</frozen-after-approval>

## Code Map

- `agent.py` -- `async triage(ticket_id) -> dict` with keys `category, priority, route, rationale`; raises `TriageError` or the provider error. `PROVIDER=groq` selects Groq, since the Gemini free tier allows 20 requests a day. Read-only.
- `run_agent.py` -- the MLflow setup to mirror, plus `load_dotenv()`. Read-only.
- `triage_schema.py` -- `TriageDecision` for `valid_schema`.
- `eval/labelled_tickets.csv` -- `ticket_id, expected_category, expected_priority, expected_tools, judge_notes`, 20 rows. Read-only.
- MLflow 3.16.1 (checked):
  - `mlflow.genai.evaluate(data, scorers, predict_fn)` takes `data` as `[{"inputs": {"ticket_id": ...}, "expectations": {...}}]` and calls `predict_fn(**inputs)`. It reuses or opens one run.
  - Scorers: `from mlflow.genai.scorers import scorer`, declaring only the parameters they need (`outputs`, `expectations`, `trace`).
  - When `predict_fn` raises, scorers still run with `outputs=None`. A scorer that raises is left out of the mean, so return 0 instead.
  - `trace.search_spans(name="get_ticket")` returns spans with `.start_time_ns`.
  - `result.metrics["<name>/mean"]` values are numpy floats.
- Gotchas (checked):
  - `predict_fn` runs in 10 threads by default. Set `MLFLOW_GENAI_EVAL_MAX_WORKERS` to 1 unless the caller set it, to avoid parallel MCP servers and provider rate limits.
  - evaluate makes one extra untraced `predict_fn` call first. Set `MLFLOW_GENAI_EVAL_SKIP_TRACE_VALIDATION=true`, since `predict_fn` is already traced.
  - A sync `predict_fn` wrapping `asyncio.run(triage(...))` nests the autologged tool spans under its trace.
  - `uv run python eval/run_eval.py` puts `eval/` on `sys.path`, not the repo root, so the script adds the root before `import agent`.

## Tasks & Acceptance

**Execution:**
- [x] `eval/run_eval.py` -- build `data` from the CSV; add a traced sync `predict_fn`; add the four `@scorer` functions, where `valid_schema`, `category_match` and `priority_match` return 0 when `outputs` is None; `main()` sets up dotenv and MLflow and the two environment defaults, calls `mlflow.genai.evaluate`, and prints the run ID. Keep `build_data`, the scorers and `predict_fn` importable for story 2 and the tests.
- [x] `tests/test_run_eval.py` -- offline, loading `eval/run_eval.py` by path. Cover: `build_data` gives 20 rows with the right inputs and expectations; each scorer on a matching output, a mismatching output, an invalid output and `None`; `tool_order` on traces with the tools in order, reversed, and one missing; and one `mlflow.genai.evaluate` run on a temporary SQLite store with a fake `triage` that makes tool spans. That run must give exactly one run and the expected means, with one failing row scoring 0.

**Acceptance Criteria:**
- Given a working provider (for example `PROVIDER=groq`), when `uv run python eval/run_eval.py` runs, then `mlflow.db` gains exactly one run in `triage-agent` with 20 traces and the metrics `valid_schema/mean`, `category_match/mean`, `priority_match/mean` and `tool_order/mean`.
- Given no network or keys, when `uv run pytest` runs, then every test passes.

## Implementation Notes

- Built: `eval/run_eval.py` (`build_data`, traced `predict_fn`, the four `@scorer`s, `SCORERS`, `main`) and `tests/test_run_eval.py` (11 tests; full suite 81, offline).
- `tool_order` returns 0 for an ERROR trace. The first live run showed failed tickets that had already called both tools scoring 1, against the matrix's "that row scores 0 on all 4 scorers".
- Live run on Groq (2026-09-26), run `f042cddcf9294d39be23bdbf9bcb431a`, 20 traces: `valid_schema` 0.90, `category_match` 0.85, `priority_match` 0.80, `tool_order` 0.90; 65,174 agent tokens in total. T-1044 and T-1057 failed because the model called `escalate_to_human`, which doesn't exist until Epic 2 story 2 (Groq 400).
- Surprise: each live run prints a harmless `Event loop is closed` message on Windows when the Groq client is cleaned up after `asyncio.run`.
- After review patches: `tests/test_run_eval.py` has 13 tests; the full suite is 83. `eval/run_eval.py` didn't change in review, so the live run above stands.
- An accidental partial second live run (`88a97641b18b4ca0a71cd4761309f716`) was soft-deleted from `triage-agent` at the user's request.

## Spec Change Log

## Review Triage Log

Blind Hunter, Edge Case Hunter and Verification Gap, pass 1 (2026-09-26):

- **low, patched.** The failing-row test checked a constant (`valid_schema(None)`) and re-ran `tool_order` by hand, never the row's logged scores or its error. It now asserts the four logged assessments on the ERROR trace are 0, and that "quota exhausted" is on the root span. (Blind Hunter, Edge Case Hunter claim, Verification Gap other findings.)
- **low, patched.** `main()` was never run (Verification Gap, Blind Hunter), so its env defaults, experiment and `build_data()` wiring were unchecked. `test_main_logs_one_run_to_triage_agent` added.
- **low, patched.** `tool_order` was only tested on hand-made spans (Verification Gap). `test_tool_order_on_autologged_agent_trace` drives the real agent and MCP server with a scripted model under autolog.
- **low, patched.** The `tmp_mlflow` fixture left the active experiment pointing at the deleted temp store, and its `monkeypatch` was unused. MLflow state is now restored per test. (Blind Hunter, Edge Case Hunter.)
- **false.** `category_match` and `priority_match` don't require a valid schema: SPEC-epic-3 CAP-3 and CAP-4 score the field alone. (Blind Hunter, Edge Case Hunter.)
- **false.** `expected_tools` is unused by `tool_order`: CAP-5 defines the scorer as trace order of `get_ticket` before `get_customer_history`.
- **false.** An errored `get_ticket` span counts as success: `agent.triage` refuses a decision without a successful `get_ticket`, so that trace is ERROR and scores 0.
- **false.** Caller env can override the two defaults: intended ("unless the caller set it").
- **false.** Tied span start times: the two MCP calls are separated by a model call in the real path.
- **false.** `predict_fn` fails inside a running event loop: MLflow runs `predict_fn` in worker threads without a loop (checked in planning).
- **low, rejected.** The tracking URI is relative to the working directory: it matches `run_agent.py` and AGENTS.md's commands, which run from the repo root.
- **low, rejected.** A trace state other than OK or ERROR: not reachable at scoring time; low at most.
- **low, rejected.** Broad `except` and the `"ERROR"` string in `tool_order`: no named harm beyond hypothetical MLflow changes.
- **low, rejected.** CSV missing columns: `eval/labelled_tickets.csv` is read-only and complete.
- **low, rejected.** Test category and priority sets hardcoded instead of read from the schema: test-only duplication.

## Verification

**Commands:**
- `uv run pytest` -- expected: all tests pass, no network.
- `PROVIDER=groq uv run python eval/run_eval.py` -- expected: one new run in `triage-agent` with the four `/mean` metrics and 20 traces.
