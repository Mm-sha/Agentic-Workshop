---
title: 'Seed loader'
type: 'feature'
created: '2026-09-26'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: ['{project-root}/_bmad-output/specs/spec-epic-1/SPEC.md', '{project-root}/mcp/triage_server.py']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `mcp/triage_server.py` reads `app.db`, but nothing creates it, so the agent's tools have no data (SPEC-epic-1 CAP-2, CAP-3).

**Approach:** Add `load_seed.py` so `uv run python load_seed.py` loads `seed/tickets.csv` and `seed/customers.csv` into `app.db` as tables `tickets` (24 rows) and `customers` (20 rows) with the CSV columns, `open_tickets` as an integer and every other column as text. `get_ticket("T-1042")` and `get_customer_history("C-77")` then return data, and a second run leaves the same tables, columns and rows, with no duplicates and no error.

</frozen-after-approval>

## Implementation Notes

- `load_seed.py` at the repo root, next to `triage_schema.py` and `run_agent.py`, as AGENTS.md's command list expects. Standard library only (`csv`, `sqlite3`, `pathlib`): no new dependency, no network, no API key.
- Paths resolve from the script's own folder, like `DB_PATH` in `mcp/triage_server.py`, so it works from any working directory.
- Columns come from each CSV's header row, so they match the CSVs exactly; `open_tickets` is declared `INTEGER` and converted with `int()`, the rest `TEXT`.
- Reruns are safe because each table is dropped and recreated inside one transaction before the rows are inserted: same result every time, no duplicates, and a failed load leaves the previous tables in place.
- `seed/` is only read. `app.db` is already in `.gitignore`.
- Tests in `tests/test_load_seed.py` load into a temporary database (via a `db_path` parameter) so they never touch the real `app.db`.
- Built: `load_seed.py` (`load_seed(db_path, seed_dir)` returns the row count per table; the `__main__` block prints them) and `tests/test_load_seed.py` (7 tests).
- The connection uses `autocommit=False` (Python 3.12+), so the `DROP`/`CREATE` statements are inside the transaction too. In the legacy mode, DDL runs outside it and a failed load would leave empty tables. A test feeds a bad `open_tickets` value and checks the previous tables survive.
- Surprise: `import mcp.triage_server` resolves to the installed `mcp` package, not the repo's `mcp/` folder. The server test loads `mcp/triage_server.py` by file path and points its `DB_PATH` at the test database.

## Review Triage Log

Blind Hunter, 8 findings:

- **low, patched.** Test connections opened with `with sqlite3.connect(...)`, which doesn't close them. Now `contextlib.closing`; the suite passes with `-W error::ResourceWarning`.
- **low, patched.** `open_tickets >= 3` count proved nothing: in SQLite any TEXT value compares greater than an integer (`'1' >= 3` is true; checked). Removed; the `typeof(open_tickets) = 'integer'` assertion already proves the type.
- **low, patched.** The final message printed only `app.db`; it now prints the resolved path.
- **low, rejected.** The `uv run python load_seed.py` command itself isn't tested. Running it for real in tests would overwrite the real `app.db`, and redirecting it needs a new option; both runs were checked by hand (24 and 20 rows each time).
- **low, rejected.** Headers aren't checked against the names `mcp/triage_server.py` needs. `seed/` is read-only and the column and server tests already fail on a renamed header.
- **false.** BOM, empty-CSV and duplicate-ID guards: the seed files have no BOM, no duplicate IDs and aren't empty (checked), and `seed/` is read-only.
- **false.** "Rollback depends on implicit behaviour": `sqlite3` discards an uncommitted transaction on `close()`, and `test_failed_load_keeps_previous_tables` proves it.
- **false.** "Validation and DDL are mixed together": no harm named; the whole load is one transaction.
