"""Learning memory: Behavior -> Failure -> Root Cause -> Intervention -> Result.

A small SQLite store of what went wrong, what we thought caused it, what we
tried, and whether it worked — so future anomalies with the same
`behavior_signature` (see wam/trace.py) can be recognized and, ideally,
resolved with a previously-verified intervention instead of a fresh
diagnosis every time.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    run_id TEXT NOT NULL,
    behavior_signature TEXT NOT NULL,
    mode TEXT,
    signals TEXT NOT NULL,          -- JSON list of anomaly signal names
    failures TEXT NOT NULL,         -- JSON list of raw validator failure strings
    root_cause TEXT,
    intervention_type TEXT,
    intervention_description TEXT,
    verification_result TEXT,       -- JSON: {passed: bool, detail: str}
    outcome TEXT NOT NULL           -- 'success' | 'failure' | 'observed_only'
);
CREATE INDEX IF NOT EXISTS idx_behavior_signature ON records (behavior_signature);
"""


@dataclass
class MemoryRecord:
    run_id: str
    behavior_signature: str
    signals: list[str]
    failures: list[str]
    mode: str = ""
    root_cause: Optional[str] = None
    intervention_type: Optional[str] = None
    intervention_description: Optional[str] = None
    verification_result: Optional[dict] = None
    outcome: str = "observed_only"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    id: Optional[int] = None


class LearningMemory:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "LearningMemory":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def record(self, rec: MemoryRecord) -> int:
        cur = self._conn.execute(
            """INSERT INTO records
               (created_at, run_id, behavior_signature, mode, signals, failures,
                root_cause, intervention_type, intervention_description,
                verification_result, outcome)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rec.created_at,
                rec.run_id,
                rec.behavior_signature,
                rec.mode,
                json.dumps(rec.signals),
                json.dumps(rec.failures),
                rec.root_cause,
                rec.intervention_type,
                rec.intervention_description,
                json.dumps(rec.verification_result) if rec.verification_result is not None else None,
                rec.outcome,
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def _row_to_record(self, row: tuple) -> MemoryRecord:
        (
            id_, created_at, run_id, behavior_signature, mode, signals, failures,
            root_cause, intervention_type, intervention_description,
            verification_result, outcome,
        ) = row
        return MemoryRecord(
            id=id_,
            created_at=created_at,
            run_id=run_id,
            behavior_signature=behavior_signature,
            mode=mode,
            signals=json.loads(signals),
            failures=json.loads(failures),
            root_cause=root_cause,
            intervention_type=intervention_type,
            intervention_description=intervention_description,
            verification_result=json.loads(verification_result) if verification_result else None,
            outcome=outcome,
        )

    def precedents(self, behavior_signature: str, limit: int = 20) -> list[MemoryRecord]:
        """Most recent records sharing this behavior signature, newest first."""
        rows = self._conn.execute(
            """SELECT id, created_at, run_id, behavior_signature, mode, signals, failures,
                      root_cause, intervention_type, intervention_description,
                      verification_result, outcome
               FROM records WHERE behavior_signature = ?
               ORDER BY id DESC LIMIT ?""",
            (behavior_signature, limit),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def pattern_frequency(self, behavior_signature: str) -> dict[str, Any]:
        """Summary used both by detectors ('seen N times before') and by the
        diagnostic agent (which interventions have actually worked)."""
        precedents = self.precedents(behavior_signature, limit=1000)
        by_intervention: dict[str, dict[str, int]] = {}
        for p in precedents:
            key = p.intervention_type or "(no intervention recorded)"
            bucket = by_intervention.setdefault(key, {"success": 0, "failure": 0, "observed_only": 0})
            bucket[p.outcome] = bucket.get(p.outcome, 0) + 1
        return {
            "times_seen": len(precedents),
            "by_intervention": by_intervention,
        }

    def best_known_intervention(self, behavior_signature: str) -> Optional[MemoryRecord]:
        """Most recent record for this signature whose intervention was verified successful."""
        for p in self.precedents(behavior_signature, limit=1000):
            if p.outcome == "success":
                return p
        return None
