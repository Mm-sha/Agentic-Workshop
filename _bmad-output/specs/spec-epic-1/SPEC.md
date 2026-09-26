---
id: SPEC-epic-1
companions: [../../../TRIAGE_POLICY.md, ../../../mcp/triage_server.py]
sources: [../../../INTENT.md]
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# Epic 1: triage data and schema

## Why

The workshop's triage agent (Epic 2) and its eval (Epic 3) both need two things that don't exist yet: a single definition of what a valid triage decision is, and the seed tickets and customers in a database the MCP server can read. `mcp/triage_server.py` already queries `app.db`, but nothing creates it. This epic lays that foundation, offline and with no model calls, so the later epics build against a fixed contract.

## Capabilities

- **CAP-1**
  - **intent:** Any triage decision can be checked against one schema that accepts only well-formed decisions.
  - **success:** A JSON object with a `category` (billing, bug, access, performance, how-to), a `priority` (P1–P4), a `route` (billing-team, bug-team, access-team, performance-team, how-to-team) and a `rationale` validates when the route is the one `TRIAGE_POLICY.md` pairs with its category and the rationale is non-empty and a single line. Everything else is rejected with an error that names the offending field: a missing field, an unknown extra field, an out-of-set value, a category–route mismatch (e.g. `bug` with `billing-team`), or a blank or multi-line rationale.

- **CAP-2**
  - **intent:** One command loads the seed data into a local SQLite database.
  - **success:** `uv run python load_seed.py` creates `app.db` with tables `tickets` (24 rows) and `customers` (20 rows) whose columns match `seed/tickets.csv` and `seed/customers.csv`. `open_tickets` is stored as an integer, all other columns as text. Both `get_ticket("T-1042")` and `get_customer_history("C-77")` in `mcp/triage_server.py` then return data.

- **CAP-3**
  - **intent:** Reloading the seed data is safe to repeat.
  - **success:** Running `load_seed.py` a second time leaves `app.db` with the same tables, columns and rows as after the first run, with no duplicates and no error.

## Constraints

- Python 3.12 or newer, managed with uv.
- Everything under `seed/` is read-only.
- No network calls and no API keys in this epic.
- `mcp/triage_server.py` is unchanged and must keep working: tables `tickets` (`ticket_id`, `customer_id`, `created_at`, `text`) and `customers` (`customer_id`, `name`, `plan`, `open_tickets`) keep those names.
- The category–route pairing comes from `TRIAGE_POLICY.md`'s table, which is read-only; the schema follows it, not the other way round.
- `app.db` is git-ignored and never committed.
- Epics 2 and 3 treat this schema and loader as read-only once built: Epic 2 returns the schema as structured output, and Epic 3's `valid_schema` check scores against it.

## Non-goals

- The agent, the MCP tools, evals and any user interface (Epics 2 and 3).

## Success signal

On a fresh clone, `uv run python load_seed.py` run twice produces the same `app.db`, and `get_ticket("T-1042")` returns customer `C-77`. The decision `{category: billing, priority: P2, route: billing-team, rationale: "Double charge puts money at stake, so P2."}` validates, while the same decision with `route: bug-team` is rejected with an error naming `route`.
