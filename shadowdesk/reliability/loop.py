"""Ties the pieces together: Detect -> Diagnose -> Intervene -> Verify -> Learn
for one ExecutionTrace, against one n8n workflow JSON file.

This is the function program.md's autonomous loop calls once per trace
(fixture, or later a real captured n8n execution). It does not decide
*when* to run — that's the loop described in program.md, mirroring the
original autoresearch repo's "LOOP FOREVER" structure but over traces
instead of GPU minutes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from shadowdesk.reliability.detectors import Anomaly, detect_all
from shadowdesk.reliability.diagnostics import Diagnosis, diagnose
from shadowdesk.reliability.interventions import InterventionResult, apply_intervention
from shadowdesk.reliability.memory import LearningMemory, MemoryRecord
from shadowdesk.reliability.ollama_client import DEFAULT_MODEL
from shadowdesk.reliability.trace import ExecutionTrace
from shadowdesk.reliability.verification import VerificationResult, verify


@dataclass
class RunResult:
    trace_run_id: str
    anomalies: list[Anomaly] = field(default_factory=list)
    diagnosis: Optional[Diagnosis] = None
    intervention: Optional[InterventionResult] = None
    verification: Optional[VerificationResult] = None
    outcome: str = "observed_only"  # 'success' | 'failure' | 'observed_only'
    memory_record_id: Optional[int] = None


def run_once(
    trace: ExecutionTrace,
    workflow: dict,
    memory: LearningMemory,
    model: str = DEFAULT_MODEL,
) -> RunResult:
    anomalies = detect_all(trace, memory)
    result = RunResult(trace_run_id=trace.run_id, anomalies=anomalies)

    if not anomalies:
        return result

    diagnosis = diagnose(trace, anomalies, memory, model=model)
    result.diagnosis = diagnosis

    outcome = "observed_only"
    intervention: Optional[InterventionResult] = None
    verification: Optional[VerificationResult] = None

    if diagnosis.is_problem and diagnosis.intervention_type != "flag_for_human_review":
        intervention = apply_intervention(workflow, diagnosis)
        result.intervention = intervention
        if intervention.applied:
            verification = verify(trace, diagnosis.intervention_type, diagnosis.intervention_params, model=model)
            result.verification = verification
            if verification.passed is True:
                outcome = "success"
            elif verification.passed is False:
                outcome = "failure"
            else:
                outcome = "observed_only"  # unverifiable offline; not a claimed success

    result.outcome = outcome
    behavior_sig = trace.behavior_signature()
    failures = sorted(
        {f for a in trace.attempts if a.validator for f in a.validator.failures}
    )
    record = MemoryRecord(
        run_id=trace.run_id,
        behavior_signature=behavior_sig,
        signals=[a.signal for a in anomalies],
        failures=failures,
        mode=trace.mode,
        root_cause=diagnosis.why if diagnosis.error is None else None,
        intervention_type=diagnosis.intervention_type,
        intervention_description=diagnosis.intervention_description,
        verification_result={"passed": verification.passed, "detail": verification.detail} if verification else None,
        outcome=outcome,
    )
    result.memory_record_id = memory.record(record)
    return result


def load_workflow(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_workflow(workflow: dict, path: str | Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(workflow, f, indent=2, ensure_ascii=False)
