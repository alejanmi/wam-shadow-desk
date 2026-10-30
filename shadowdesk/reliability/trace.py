"""Execution trace schema for one run of the WAM brief-generation workflow.

This is deliberately narrower than a generic n8n execution export: it
captures exactly the fields the detectors need, keyed off the two nodes
that actually determine whether a brief succeeded — the generation call
(currently the "DeepSeek" HTTP node, with "WM_AGENT_OG" as an unwired
fallback path) and the "Validator" code node that checks its output.

Traces can be constructed by hand (see fixtures/), or extracted from a
real n8n execution export via `from_n8n_export` once live API access is
wired up (see wam/n8n_adapter.py).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional


@dataclass
class ValidatorResult:
    ok: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def failure_signature(self) -> str:
        """Stable key for 'is this the same failure as before'.

        Sorted so message ordering doesn't matter; counts collapsed out of
        messages that embed a number (e.g. "pb-item count = 3 (expected 5)")
        so near-duplicate failures still collapse to one signature.
        """
        import re

        normalized = sorted(re.sub(r"\d+", "N", f) for f in self.failures)
        return "|".join(normalized)


@dataclass
class GenerationAttempt:
    attempt_index: int
    model: str
    started_at: str
    finished_at: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    output_text: str = ""
    validator: Optional[ValidatorResult] = None
    error: Optional[str] = None

    @property
    def duration_seconds(self) -> float:
        from datetime import datetime

        fmt = "%Y-%m-%dT%H:%M:%S.%f" if "." in self.started_at else "%Y-%m-%dT%H:%M:%S"
        try:
            start = datetime.strptime(self.started_at.rstrip("Z"), fmt)
            end = datetime.strptime(self.finished_at.rstrip("Z"), fmt)
            return max((end - start).total_seconds(), 0.0)
        except ValueError:
            return 0.0


@dataclass
class ExecutionTrace:
    run_id: str
    workflow_name: str
    mode: str  # e.g. "advisor" | "analyst" | "hybrid" (from the Read Mode sheet)
    attempts: list[GenerationAttempt] = field(default_factory=list)
    # Upstream aggregated payload (Ticker/advisorName/newsContext/etc.) that was
    # handed to the generation call, when captured. Lets the pre-flight-style
    # checks run retrospectively even though the live workflow doesn't gate on
    # them yet. None when not captured (older/synthetic traces).
    input_payload: Optional[dict] = None

    @property
    def final_attempt(self) -> Optional[GenerationAttempt]:
        return self.attempts[-1] if self.attempts else None

    @property
    def succeeded(self) -> bool:
        a = self.final_attempt
        return bool(a and a.validator and a.validator.ok and not a.error)

    def behavior_signature(self) -> str:
        """Groups traces that represent 'the same kind of thing going wrong'.

        Combines the mode with the failure signature(s) seen across attempts,
        so e.g. "hybrid mode, truncated joke block" recurring across separate
        runs hashes to the same key for learning-memory lookups.
        """
        sigs = sorted(
            {a.validator.failure_signature() for a in self.attempts if a.validator and not a.validator.ok}
        )
        raw = self.mode + "::" + "||".join(sigs)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "ExecutionTrace":
        attempts = []
        for a in d.get("attempts", []):
            v = a.get("validator")
            attempts.append(
                GenerationAttempt(
                    attempt_index=a["attempt_index"],
                    model=a["model"],
                    started_at=a["started_at"],
                    finished_at=a["finished_at"],
                    prompt_tokens=a.get("prompt_tokens"),
                    completion_tokens=a.get("completion_tokens"),
                    reasoning_tokens=a.get("reasoning_tokens"),
                    output_text=a.get("output_text", ""),
                    validator=ValidatorResult(**v) if v else None,
                    error=a.get("error"),
                )
            )
        return ExecutionTrace(
            run_id=d["run_id"],
            workflow_name=d.get("workflow_name", "Santi Miguel AI Agent (F)"),
            mode=d.get("mode", "hybrid"),
            attempts=attempts,
            input_payload=d.get("input_payload"),
        )

    @staticmethod
    def load(path: str | Path) -> "ExecutionTrace":
        with open(path, "r", encoding="utf-8") as f:
            return ExecutionTrace.from_dict(json.load(f))

    def save(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
