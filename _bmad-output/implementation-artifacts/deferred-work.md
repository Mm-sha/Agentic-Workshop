- source_spec: `_bmad-output/specs/spec-epic-1/stories/1-triage-decision-schema.md`
  summary: Add `Field(description=...)` guidance to `TriageDecision` (route must match category, rationale is one sentence naming the rule applied) so the JSON schema Epic 2 hands the model carries it.
  evidence: The generated JSON schema has only enums and titles. The policy text in the agent's prompt may already cover this, so it's worth deciding when Epic 2 wires up structured output, not in Epic 1's validation-only scope.

## Deferred from: code review of 1-triage-decision-schema.md (2026-09-26)

- The JSON schema from `TriageDecision.model_json_schema()` shows `category` and `route` as independent enums, so provider-side structured output (Gemini) can't enforce the TRIAGE_POLICY.md pairing. A mismatch only shows up as a Pydantic `ValidationError` after the model call; Epic 2 should handle or retry it.
