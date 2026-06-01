"""Stage 4: persist events into SQLite with dates as first-class citizens.

Schema honours the user's two-table design:

    dates(date, event_ids, source_documents)
    events(event_id, date, event_detail, source_documents)

`dates` is intentionally redundant — it caches the per-day rollup so a
timeline query is one cheap ORDER-BY scan and never needs a GROUP BY.
The two tables are kept consistent by `EventStore.add_events`.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

from .event_extractor import Event

logger = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS dates (
    date              TEXT PRIMARY KEY,            -- ISO yyyy-mm-dd
    event_ids         TEXT NOT NULL DEFAULT '',    -- comma-separated
    source_documents  TEXT NOT NULL DEFAULT ''     -- comma-separated, deduped
);

CREATE TABLE IF NOT EXISTS events (
    event_id          TEXT PRIMARY KEY,
    date              TEXT NOT NULL,
    event_detail      TEXT NOT NULL,
    source_documents  TEXT NOT NULL,
    FOREIGN KEY (date) REFERENCES dates(date)
);

CREATE INDEX IF NOT EXISTS idx_events_date ON events(date);
"""


class EventStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Writes

    def add_events(self, events: Iterable[Event]) -> int:
        events = list(events)
        if not events:
            return 0
        with self._connect() as conn:
            for ev in events:
                self._upsert_date(conn, ev.date, ev.event_id, ev.source_document)
                conn.execute(
                    "INSERT OR REPLACE INTO events "
                    "(event_id, date, event_detail, source_documents) "
                    "VALUES (?, ?, ?, ?)",
                    (ev.event_id, ev.date, ev.event_detail, ev.source_document),
                )
        logger.info("Inserted %d events", len(events))
        return len(events)

    def _upsert_date(
        self, conn: sqlite3.Connection, date: str, event_id: str, source: str
    ) -> None:
        row = conn.execute(
            "SELECT event_ids, source_documents FROM dates WHERE date = ?",
            (date,),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO dates(date, event_ids, source_documents) VALUES(?,?,?)",
                (date, event_id, source),
            )
            return
        ids = _csv_add(row["event_ids"], event_id)
        srcs = _csv_add(row["source_documents"], source)
        conn.execute(
            "UPDATE dates SET event_ids = ?, source_documents = ? WHERE date = ?",
            (ids, srcs, date),
        )

    # ------------------------------------------------------------------
    # Reads

    def all_dates(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return list(conn.execute("SELECT * FROM dates ORDER BY date ASC"))

    def events_on(self, date: str) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return list(conn.execute(
                "SELECT * FROM events WHERE date = ? ORDER BY event_id",
                (date,),
            ))

    def get_event(self, event_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM events WHERE event_id = ?", (event_id,)
            ).fetchone()

    def iter_events_chronologically(self) -> Iterator[sqlite3.Row]:
        with self._connect() as conn:
            yield from conn.execute(
                "SELECT * FROM events ORDER BY date ASC, event_id ASC"
            )


def _csv_add(existing: str, value: str) -> str:
    items = [s for s in existing.split(",") if s] if existing else []
    if value not in items:
        items.append(value)
    return ",".join(items)
