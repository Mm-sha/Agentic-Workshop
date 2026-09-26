import csv
import importlib.util
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

import load_seed

ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = ROOT / "seed"


def read_csv(name: str) -> tuple[list[str], list[list[str]]]:
    with (SEED_DIR / name).open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        return next(reader), list(reader)


def dump(db_path: Path) -> dict:
    with closing(sqlite3.connect(db_path)) as conn:
        return {
            table: (
                [(c[1], c[2]) for c in conn.execute(f"PRAGMA table_info({table})")],
                sorted(conn.execute(f"SELECT * FROM {table}").fetchall()),
            )
            for table in ("tickets", "customers")
        }


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "app.db"


def test_row_counts(db_path):
    assert load_seed.load_seed(db_path) == {"tickets": 24, "customers": 20}
    with closing(sqlite3.connect(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM tickets").fetchone() == (24,)
        assert conn.execute("SELECT COUNT(*) FROM customers").fetchone() == (20,)


@pytest.mark.parametrize("table", ["tickets", "customers"])
def test_columns_and_rows_match_csv(db_path, table):
    load_seed.load_seed(db_path)
    header, rows = read_csv(f"{table}.csv")
    columns, stored = dump(db_path)[table]
    assert [name for name, _ in columns] == header
    assert sorted(tuple(str(v) for v in row) for row in stored) == sorted(tuple(r) for r in rows)


def test_open_tickets_is_integer_and_the_rest_text(db_path):
    load_seed.load_seed(db_path)
    types = {table: dict(columns) for table, (columns, _) in dump(db_path).items()}
    assert types["customers"] == {"customer_id": "TEXT", "name": "TEXT", "plan": "TEXT", "open_tickets": "INTEGER"}
    assert set(types["tickets"].values()) == {"TEXT"}
    with closing(sqlite3.connect(db_path)) as conn:
        assert conn.execute("SELECT DISTINCT typeof(open_tickets) FROM customers").fetchall() == [("integer",)]


def test_second_run_gives_the_same_database(db_path):
    load_seed.load_seed(db_path)
    first = dump(db_path)
    assert load_seed.load_seed(db_path) == {"tickets": 24, "customers": 20}
    assert dump(db_path) == first


def test_triage_server_queries_return_data(db_path, monkeypatch):
    # Loaded by path: the folder name mcp/ clashes with the installed mcp package.
    spec = importlib.util.spec_from_file_location("triage_server", ROOT / "mcp" / "triage_server.py")
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    load_seed.load_seed(db_path)
    monkeypatch.setattr(server, "DB_PATH", db_path)
    assert server.get_ticket("T-1042")["customer_id"] == "C-77"
    history = server.get_customer_history("C-77")
    assert history["customer_id"] == "C-77"
    assert "T-1042" in history["ticket_ids"]


def test_failed_load_keeps_previous_tables(db_path, tmp_path):
    load_seed.load_seed(db_path)
    before = dump(db_path)
    bad_seed = tmp_path / "seed"
    bad_seed.mkdir()
    (bad_seed / "tickets.csv").write_text((SEED_DIR / "tickets.csv").read_text(encoding="utf-8"), encoding="utf-8")
    (bad_seed / "customers.csv").write_text("customer_id,name,plan,open_tickets\nC-1,X,Team,many\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_seed.load_seed(db_path, bad_seed)
    assert dump(db_path) == before
