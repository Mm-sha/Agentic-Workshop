---
title: 'Triage decision schema'
type: 'feature'
created: '2026-09-26'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: ['{project-root}/_bmad-output/specs/spec-epic-1/SPEC.md', '{project-root}/TRIAGE_POLICY.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The agent (Epic 2) and the eval (Epic 3) need one shared definition of a valid triage decision, and none exists (SPEC-epic-1 CAP-1).

**Approach:** Add a schema that accepts a JSON object with `category`, `priority`, `route` and `rationale` only when every value is allowed, the route is the one `TRIAGE_POLICY.md` pairs with the category, and the rationale is a non-empty single line. Anything else is rejected with an error naming the offending field: missing field, unknown extra field, out-of-set value, category–route mismatch, blank or multi-line rationale.

</frozen-after-approval>

## Implementation Notes

- `triage_schema.py` at the repo root, next to `run_agent.py` and the future `load_seed.py`: a Pydantic model `TriageDecision`. Pydantic is already a dependency, and Epic 2's LangChain structured output takes a Pydantic model directly. No spec downstream names the module, so this choice is recorded here.
- The allowed values are `Literal` types, case-sensitive with no coercion. `extra="forbid"` rejects unknown fields.
- The category–route pairing is a `route` field validator that looks at the already-validated `category`, so the error's location is `route`. The pairing table matches `TRIAGE_POLICY.md` exactly.
- The rationale validator rejects blank or whitespace-only text and any `\n` or `\r`. It doesn't count sentences.
- Invalid input raises Pydantic's `ValidationError`, whose `loc` names the field. `TriageDecision.model_validate(dict)` handles dicts and `model_validate_json(str)` handles JSON text.
- Tests go in `tests/test_triage_schema.py`, in the `tests/` folder `pyproject.toml` already points at.
- Built: `triage_schema.py` (`TriageDecision`, the `Category`/`Priority`/`Route` literals, `ROUTE_FOR_CATEGORY`) and `tests/test_triage_schema.py` (32 tests).
- `strict=True` on top of `extra="forbid"`, so there's no type coercion: an integer priority `2` or rationale `42` is rejected, not converted to a string.
- If `category` is invalid, the route validator skips the pairing check (`category` is missing from `info.data`), so the error names only `category`.
- Surprise: pytest couldn't import root-level modules, because the repo root isn't on `sys.path`. Fixed by adding `pythonpath = ["."]` under `[tool.pytest.ini_options]` in `pyproject.toml`. Story 2's `load_seed.py` tests will need it too.

## Review Triage Log

Blind Hunter, 9 findings:

- **low, patched.** Unicode line breaks (` `, `\x85`, `\v`, `\f`) passed the single-line check; confirmed by running them. Now `rationale.splitlines() != [rationale]`, with a test for each.
- **low, patched.** Assigning a field after validation skipped validation (`d.route = "bug-team"` was accepted; confirmed). The model is now `frozen=True`, with a test.
- **low, patched.** The policy-table test compared `ROUTE_FOR_CATEGORY` with a copy of itself. It now parses the table in `TRIAGE_POLICY.md` and compares against that.
- **low, rejected (fixed incidentally).** `ROUTE_FOR_CATEGORY` isn't tied to the `Category`/`Route` literals. The possible `KeyError` can't happen with today's code, but the new policy test also asserts that the mapping, `Category` and `Route` match, which covers it.
- **low, deferred.** No `Field` descriptions to guide the model. This is additive guidance for Epic 2 and beyond CAP-1's validation scope; logged in `deferred-work.md`.
- **low, rejected.** A rationale with padding like `"  padded  "` is accepted. It's still a non-empty single line per the spec, and stripping it would silently change what the agent said.
- **low, patched.** The JSON input path had only a success test. Behaviour was already correct (checked: extra field, mismatch and numeric priority are all rejected from JSON); rejection tests are now added.
- **low, patched.** No test covered an invalid category with a mismatched route. Behaviour was already correct (only `category` is reported; checked); a test is now added.
- **false.** "Frontmatter says in-progress." That was the expected mid-workflow state, set to `done` at finalize. The `pythonpath` change in `pyproject.toml` is already recorded above.
