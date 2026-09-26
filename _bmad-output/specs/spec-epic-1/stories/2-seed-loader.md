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

### Review Findings

Code review of `story/Manjula-1.2` vs `main` (2026-09-26): Blind Hunter, Edge Case Hunter, Verification Gap, Acceptance Auditor.

- [x] [Review][Patch] The documented command path is untested: no test checks that the loader's default `DB_PATH` is the server's `DB_PATH`, or runs `load_seed.py` as a script. Both can be checked without touching the real `app.db` (path equality; copy `load_seed.py` and `seed/` into `tmp_path` and run it twice). This reverses the earlier "CLI not tested" rejection, whose reason was wrong. [tests/test_load_seed.py:70]
- [x] [Review][Patch] The server test doesn't check that `open_tickets` comes back as an `int` through `get_customer_history`, or that `ticket_ids` is the full C-77 set (`T-1042`, `T-1047`). [tests/test_load_seed.py:70]
- [x] [Review][Defer] `import mcp.triage_server` resolves to the installed `mcp` package, which Epic 2 hits if it imports the server as a module [mcp/triage_server.py:1] — deferred: Epic 2 concern; running it as a script over stdio works.

Rejected:
- low — no `PRIMARY KEY` on the ID columns: `seed/` is read-only with no duplicate IDs (checked), and the row-count and row-match tests would catch one.
- low — validation happens mid-load with bare errors (blank lines, wrong row widths, bad `int`): the seed has no blank lines and clean integers (checked), and a failed load rolls back (tested). Adding guards covers inputs the read-only seed doesn't produce.
- low — empty CSV, UTF-8 BOM, or a `"` in a header (SQL in the DDL): none occur in the read-only, trusted seed (checked); `seed_dir` is only overridden by tests.
- false — `int("03")` loses data: CAP-2 asks for integers, and the seed values are plain `0`–`4`.
- low — `database is locked` while the server is open: the server holds its connection only for the length of one query, well under the 5 s default timeout.
- false — a failed first load leaves a half-built table: the same single transaction is discarded on `close()`, fresh or not.
- false — unquoted table names in the test helper, and `review_loop_iteration: 0`: no harm named; the oneshot route had no review loopback.
- false — the story file is in the diff: it is the new story's own spec, and `SPEC.md` is untouched.
