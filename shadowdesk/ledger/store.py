"""The evidence ledger (SQLite).

Two tables: `checks` (parity and data-quality checks, one row per check per
run) and `inquiries` (hypothesis records, Phase 3 onward). Every row keeps the
query that produced it, so any line in a report can be re-run.
The old AutoDetections learning memory lives on in shadowdesk.reliability.memory.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from shadowdesk.research.inquiry import InquiryRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    run_id TEXT NOT NULL,
    check_id TEXT NOT NULL,
    layer TEXT NOT NULL,
    status TEXT NOT NULL,          -- pass | finding | fail | skipped
    severity TEXT NOT NULL,        -- info | low | medium | high
    title TEXT NOT NULL,
    expected TEXT,
    actual TEXT,
    query TEXT NOT NULL,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_checks_run ON checks (run_id);
CREATE TABLE IF NOT EXISTS inquiries (
    claim_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    verdict TEXT NOT NULL,
    record TEXT NOT NULL
);
"""


class Ledger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.executescript(SCHEMA)

    def add_checks(self, run_id: str, checks) -> int:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows = [(now, run_id, c.check_id, c.layer, c.status, c.severity, c.title,
                 json.dumps(c.expected, default=str), json.dumps(c.actual, default=str), c.query, c.detail)
                for c in checks]
        self.conn.executemany(
            "INSERT INTO checks (created_at, run_id, check_id, layer, status, severity, title, expected, actual, query, detail)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
        self.conn.commit()
        return len(rows)

    def add_inquiry(self, rec: InquiryRecord) -> None:
        self.conn.execute("INSERT OR REPLACE INTO inquiries VALUES (?,?,?,?)",
                          (rec.claim_id, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           rec.verdict.value, rec.to_json()))
        self.conn.commit()

    def checks_for(self, run_id: str) -> list[dict]:
        cur = self.conn.execute("SELECT check_id, layer, status, severity, title, query FROM checks WHERE run_id=? ORDER BY id", (run_id,))
        return [dict(zip(("check_id", "layer", "status", "severity", "title", "query"), r)) for r in cur]

    def close(self):
        self.conn.close()
