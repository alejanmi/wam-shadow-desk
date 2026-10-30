"""Bounded, deterministic experiment control.

The controller does not decide what a workflow change means. An experiment
adapter supplies the actual work and returns evidence. The controller only
limits duration and records an explicit outcome.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ExperimentResult(Generic[T]):
    name: str
    status: str
    elapsed_seconds: float
    evidence: T | None = None
    error: str | None = None


def run_bounded(
    name: str,
    work: Callable[[], T],
    budget_seconds: float = 300.0,
) -> ExperimentResult[T]:
    """Run one local experiment and mark over-budget work as failed.

    Python cannot safely interrupt arbitrary model inference in the same
    thread, so callers should also configure timeouts in their model/client
    adapters. This wall-clock check prevents an over-budget result from being
    reported as successful.
    """
    if budget_seconds <= 0:
        raise ValueError("budget_seconds must be positive")
    started = monotonic()
    try:
        evidence = work()
    except Exception as exc:  # adapters are untrusted experiment boundaries
        return ExperimentResult(name, "error", monotonic() - started, error=str(exc))
    elapsed = monotonic() - started
    if elapsed > budget_seconds:
        return ExperimentResult(
            name,
            "timeout",
            elapsed,
            evidence=evidence,
            error=f"experiment exceeded {budget_seconds:.1f}s budget",
        )
    return ExperimentResult(name, "passed", elapsed, evidence=evidence)
