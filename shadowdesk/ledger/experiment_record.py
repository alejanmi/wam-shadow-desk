"""Local experiment record format.

A record captures what one bounded local experiment (see `experiments.py`)
did to a candidate workflow, for a human to review later. Records are
plain JSON files written under `NewARLoopLocal/data/` and are never
uploaded or transmitted anywhere.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import time_ns
from typing import Any

STATUSES = {"passed", "failed", "timeout", "error"}


@dataclass(frozen=True)
class ExperimentRecord:
    name: str
    hypothesis: str
    changed_workflow_path: str
    status: str
    elapsed_seconds: float
    evidence: dict[str, Any] = field(default_factory=dict)
    verification: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name is required")
        if not self.hypothesis:
            raise ValueError("hypothesis is required")
        if not self.changed_workflow_path:
            raise ValueError("changed_workflow_path is required")
        if self.status not in STATUSES:
            raise ValueError(f"unknown status: {self.status!r}, expected one of {sorted(STATUSES)}")
        if self.elapsed_seconds < 0:
            raise ValueError("elapsed_seconds must not be negative")

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-")
    return slug or "experiment"


def write_record(record: ExperimentRecord, directory: Path) -> Path:
    """Write a record to its own JSON file under `directory` and return the path.

    Filenames are timestamped so repeated experiments with the same name
    never overwrite an earlier record.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{time_ns()}-{_slug(record.name)}.json"
    while path.exists():
        path = directory / f"{time_ns()}-{_slug(record.name)}.json"
    path.write_text(record.to_json(), encoding="utf-8")
    return path


def read_record(path: Path) -> ExperimentRecord:
    data = json.loads(path.read_text(encoding="utf-8"))
    return ExperimentRecord(**data)
