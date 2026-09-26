"""Load seed/tickets.csv and seed/customers.csv into app.db, the database mcp/triage_server.py reads.

Run it with: uv run python load_seed.py
Running it again rebuilds both tables, so the result is always the same.
"""

import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEED_DIR = ROOT / "seed"
DB_PATH = ROOT / "app.db"

# Table name -> seed CSV. Column names come from each CSV's header row.
TABLES = {"tickets": "tickets.csv", "customers": "customers.csv"}
INTEGER_COLUMNS = {"open_tickets"}


def _read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        return next(reader), list(reader)


def load_seed(db_path: Path = DB_PATH, seed_dir: Path = SEED_DIR) -> dict[str, int]:
    """Rebuild each table from its CSV in one transaction and return the row count per table."""
    data = {table: _read_csv(seed_dir / csv_name) for table, csv_name in TABLES.items()}
    counts = {}
    conn = sqlite3.connect(db_path, autocommit=False)
    try:
        for table, (columns, rows) in data.items():
            column_defs = ", ".join(f'"{c}" {"INTEGER" if c in INTEGER_COLUMNS else "TEXT"}' for c in columns)
            integer_positions = [i for i, c in enumerate(columns) if c in INTEGER_COLUMNS]
            for row in rows:
                for i in integer_positions:
                    row[i] = int(row[i])
            conn.execute(f'DROP TABLE IF EXISTS "{table}"')
            conn.execute(f'CREATE TABLE "{table}" ({column_defs})')
            conn.executemany(f'INSERT INTO "{table}" VALUES ({", ".join("?" * len(columns))})', rows)
            counts[table] = len(rows)
        conn.commit()
    finally:
        conn.close()
    return counts


if __name__ == "__main__":
    for table, count in load_seed().items():
        print(f"{table}: {count} rows")
    print(f"Loaded into {DB_PATH}")
