"""The diagnostic sub-agent.

Per the WAM doc, its job on an anomaly is not "was the output correct?" but:
What happened? Why? Is it actually a problem? What caused it? What
intervention should occur? It answers by calling a local Ollama model with
the anomaly evidence plus any learning-memory precedents for the same
behavior signature, and returns a structured Diagnosis that the
intervention registry (wam/interventions.py) knows how to act on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from shadowdesk.reliability.detectors import Anomaly
from shadowdesk.reliability.memory import LearningMemory
from shadowdesk.reliability.ollama_client import DEFAULT_MODEL, OllamaError, chat_json
from shadowdesk.reliability.trace import ExecutionTrace

# Keep this in sync with wam/interventions.py's INTERVENTIONS registry keys.
KNOWN_INTERVENTION_TYPES = [
    "add_system_prompt_directive",
    "enable_preflight_check",
    "enable_validator_gate",
    "adjust_generation_params",
    "tighten_validator_threshold",
    "loosen_validator_threshold",
    "flag_for_human_review",
]

SYSTEM_PROMPT = f"""You are the diagnostic sub-agent in a financial-agent reliability system.
A detector has flagged anomalous behavior in one execution of a daily financial-brief
generation workflow. You do NOT evaluate whether the brief's writing is good. Your job is
root-cause analysis of the *behavior*: what happened, why, whether it is actually a problem
worth acting on (vs. noise), what caused it, and what single intervention should be tried.

You must choose intervention_type from exactly this list: {KNOWN_INTERVENTION_TYPES}.

- add_system_prompt_directive: append a short, imperative corrective instruction to the
  brief-writing model's system prompt. Use when the model itself is making a mistake it
  could avoid if told explicitly (e.g. truncating, misordering sections, inventing content).
  params: {{"directive": "<one or two imperative sentences>"}}
- enable_preflight_check: turn on the (currently disabled) payload pre-flight validator that
  runs before generation starts. Use when failures point at bad/incomplete upstream data
  reaching the model, i.e. the model is being set up to fail before it even starts.
  params: {{}}
- enable_validator_gate: insert a decision gate right after the Validator node so a
  structurally broken brief (validator ok=false) stops instead of shipping through
  formatting/podcast/email. Use when the failure already reached the Validator (i.e.
  pre-flight wouldn't have helped) and nothing currently prevents a broken brief from
  being sent out. This does not fix the underlying cause — pair it with the anomaly's
  own diagnosis, or use it alone when you're not confident enough to change generation
  itself yet and stopping bad output from shipping is the priority.
  params: {{}}
- adjust_generation_params: change one generation parameter (temperature, max_tokens, etc.)
  on the generation call. Use when evidence points at a sampling/length issue, not content.
  params: {{"field": "<param name>", "value": <new value>, "reason": "<why>"}}
- tighten_validator_threshold / loosen_validator_threshold: change one of the Validator's
  numeric/structural thresholds. Only use if the CURRENT THRESHOLD is itself the problem
  (e.g. a legitimate output shape is being rejected, or an actually-broken shape is passing).
  params: {{"check": "<name from validator stats, e.g. 'pbItems' or 'chars'>", "value": <new threshold>}}
- flag_for_human_review: use when you are not confident, when the same intervention has
  already failed before for this behavior signature (see precedents), or when the root
  cause is outside this system's control (e.g. an upstream data source is down).
  params: {{"reason": "<why a human should look>"}}

IMPORTANT: a truncation failure together with a high completion_tokens count means the
model RAN OUT OF ROOM, not that it was told to write too much. If you see a
"hit_generation_ceiling" or truncation-related anomaly, the fix is almost always to
RAISE max_tokens (or shorten the required output), never to lower it — lowering it makes
truncation worse. Do not let a separate "excessive_tokens" anomaly on the same attempt
talk you into reducing max_tokens when truncation is also present; check which anomaly
actually explains the observed failure before choosing a direction.

Respond with ONLY a JSON object with exactly these keys:
{{
  "what_happened": "<factual, one or two sentences>",
  "why": "<your best root-cause hypothesis>",
  "is_problem": <true|false>,
  "confidence": <0.0-1.0>,
  "intervention_type": "<one of the list above>",
  "intervention_params": {{...as specified above for the chosen type...}},
  "intervention_description": "<one sentence a human would read in a changelog>"
}}"""


@dataclass
class Diagnosis:
    what_happened: str
    why: str
    is_problem: bool
    confidence: float
    intervention_type: str
    intervention_params: dict[str, Any] = field(default_factory=dict)
    intervention_description: str = ""
    error: Optional[str] = None

    @staticmethod
    def failed(reason: str) -> "Diagnosis":
        return Diagnosis(
            what_happened="diagnosis unavailable",
            why=reason,
            is_problem=True,
            confidence=0.0,
            intervention_type="flag_for_human_review",
            intervention_params={"reason": reason},
            intervention_description="Diagnostic agent could not run; flagged for human review.",
            error=reason,
        )


def _build_user_prompt(trace: ExecutionTrace, anomalies: list[Anomaly], memory: Optional[LearningMemory]) -> str:
    payload: dict[str, Any] = {
        "run_id": trace.run_id,
        "mode": trace.mode,
        "num_attempts": len(trace.attempts),
        "final_succeeded": trace.succeeded,
        "anomalies": [
            {"signal": a.signal, "severity": a.severity, "summary": a.summary, "evidence": a.evidence}
            for a in anomalies
        ],
        "attempts": [
            {
                "attempt_index": a.attempt_index,
                "model": a.model,
                "duration_seconds": round(a.duration_seconds, 1),
                "completion_tokens": a.completion_tokens,
                "reasoning_tokens": a.reasoning_tokens,
                "validator_ok": a.validator.ok if a.validator else None,
                "validator_failures": a.validator.failures if a.validator else None,
                "validator_warnings": a.validator.warnings if a.validator else None,
                "validator_stats": a.validator.stats if a.validator else None,
                "error": a.error,
                # Output text is 40k-140k chars in production; only the edges matter for
                # diagnosing truncation/preamble/section-order issues, so excerpt it.
                "output_head": a.output_text[:800],
                "output_tail": a.output_text[-800:],
            }
            for a in trace.attempts
        ],
    }
    if trace.input_payload is not None:
        payload["input_payload"] = trace.input_payload
    if memory is not None:
        sig = trace.behavior_signature()
        payload["behavior_signature"] = sig
        payload["precedents"] = memory.pattern_frequency(sig)
        best = memory.best_known_intervention(sig)
        if best:
            payload["previously_verified_fix"] = {
                "intervention_type": best.intervention_type,
                "intervention_description": best.intervention_description,
            }
    return json.dumps(payload, indent=2)


def diagnose(
    trace: ExecutionTrace,
    anomalies: list[Anomaly],
    memory: Optional[LearningMemory] = None,
    model: str = DEFAULT_MODEL,
) -> Diagnosis:
    if not anomalies:
        return Diagnosis(
            what_happened="no anomalies detected",
            why="n/a",
            is_problem=False,
            confidence=1.0,
            intervention_type="flag_for_human_review",
            intervention_params={},
            intervention_description="",
        )
    user_prompt = _build_user_prompt(trace, anomalies, memory)
    try:
        result = chat_json(SYSTEM_PROMPT, user_prompt, model=model)
    except OllamaError as e:
        return Diagnosis.failed(str(e))

    try:
        intervention_type = result["intervention_type"]
        if intervention_type not in KNOWN_INTERVENTION_TYPES:
            return Diagnosis.failed(f"model chose unknown intervention_type: {intervention_type!r}")
        return Diagnosis(
            what_happened=result["what_happened"],
            why=result["why"],
            is_problem=bool(result["is_problem"]),
            confidence=float(result.get("confidence", 0.5)),
            intervention_type=intervention_type,
            intervention_params=result.get("intervention_params", {}) or {},
            intervention_description=result.get("intervention_description", ""),
        )
    except (KeyError, TypeError, ValueError) as e:
        return Diagnosis.failed(f"malformed diagnosis response: {e}")
