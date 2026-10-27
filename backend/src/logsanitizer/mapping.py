"""Persistent, project-wide mapping from original values to placeholders.

CONFIDENTIAL: the mapping database reveals every original value. It must stay on
the local system and is never part of rule exports, reports or run outputs.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

PLACEHOLDER_TEMPLATE = "[{category}_{number}]"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mapping (
    category TEXT NOT NULL,
    original TEXT NOT NULL,
    number INTEGER NOT NULL,
    run_id TEXT NOT NULL,
    created TEXT NOT NULL,
    PRIMARY KEY (category, original),
    UNIQUE (category, number)
);
"""


def placeholder(category: str, number: int) -> str:
    return PLACEHOLDER_TEMPLATE.format(category=category, number=number)


class MappingStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # Always close: open handles keep the file locked on Windows.
        conn = sqlite3.connect(self.path)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def load(self) -> dict[tuple[str, str], str]:
        """Return {(category, original): placeholder} for all known values."""
        with self._connect() as conn:
            rows = conn.execute("SELECT category, original, number FROM mapping").fetchall()
        return {(c, o): placeholder(c, n) for c, o, n in rows}

    def assign(self, values: Iterable[tuple[str, str]], run_id: str) -> int:
        """Assign numbers to values not yet mapped; returns how many were added.

        New values are sorted before numbering, so the result depends only on the
        set of values, not on the order in which files were read.
        """
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as conn:
            known = set(conn.execute("SELECT category, original FROM mapping").fetchall())
            new = sorted(set(values) - known)
            next_number = dict(conn.execute(
                "SELECT category, MAX(number) FROM mapping GROUP BY category").fetchall())
            for category, original in new:
                number = next_number.get(category, 0) + 1
                next_number[category] = number
                conn.execute("INSERT INTO mapping VALUES (?, ?, ?, ?, ?)",
                             (category, original, number, run_id, now))
        return len(new)

    def counts(self) -> dict[str, int]:
        with self._connect() as conn:
            return dict(conn.execute(
                "SELECT category, COUNT(*) FROM mapping GROUP BY category ORDER BY category"))

    def rows(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT category, number, original, run_id, created FROM mapping "
                "ORDER BY category, number").fetchall()
        return [{"placeholder": placeholder(c, n), "category": c, "original": o,
                 "run_id": r, "created": t} for c, n, o, r, t in rows]

    def originals(self) -> list[tuple[str, str]]:
        with self._connect() as conn:
            return conn.execute("SELECT category, original FROM mapping").fetchall()
