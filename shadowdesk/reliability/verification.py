"""Verify an intervention against the trace/fixture that motivated it, before
it's trusted (per the WAM doc: "the proposed intervention would then ideally
be verified, rather than blindly accepted").

Honesty note: we have no live n8n or model-API access in this phase, so a
brief can't actually be regenerated end-to-end to prove a fix works. Where
that would be required (system-prompt directives, sampling params) this
module says so explicitly via `passed=None` rather than faking a result.
Where the check IS fully offline-provable (validator threshold edits,
whether pre-flight would have caught the failure), it gives a real
True/False. `passed=None` is a TODO marker for live verification, not a
success.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from shadowdesk.reliability.interventions import InterventionResult
from shadowdesk.reliability.ollama_client import DEFAULT_MODEL, OllamaError, chat_json
from shadowdesk.reliability.preflight_port import run_preflight
from shadowdesk.reliability.trace import ExecutionTrace
from shadowdesk.reliability.validator_port import run_validator


@dataclass
class VerificationResult:
    passed: Optional[bool]  # None = cannot verify offline yet
    detail: str


def _verify_validator_threshold(trace: ExecutionTrace, params: dict) -> VerificationResult:
    check = params.get("check")
    value = params.get("value")
    failing = [a for a in trace.attempts if a.validator and not a.validator.ok]
    if not failing:
        return VerificationResult(None, "no failing attempt in this trace to verify the threshold change against")
    target = failing[-1]

    threshold_key = {"chars_min": "chars_min", "chars_max": "chars_max"}.get(check, check)
    new_result = run_validator(target.output_text, thresholds={threshold_key: value})
    cleared = new_result.ok or len(new_result.failures) < len(target.validator.failures)
    detail = (
        f"re-ran the validator on attempt {target.attempt_index}'s output with {check}={value}: "
        f"failures went from {len(target.validator.failures)} to {len(new_result.failures)}"
    )
    return VerificationResult(cleared, detail)


def _verify_preflight(trace: ExecutionTrace, params: dict) -> VerificationResult:
    if not trace.input_payload:
        return VerificationResult(None, "trace has no captured input_payload; cannot verify pre-flight offline")
    result = run_preflight(trace.input_payload)
    if result.ok:
        return VerificationResult(
            False,
            "pre-flight would NOT have caught this — the payload passes pre-flight, so the failure "
            "originates elsewhere (model behavior, not input quality); enable_preflight_check was likely the wrong intervention",
        )
    return VerificationResult(
        True,
        f"pre-flight would have failed fast on this payload before generation: {result.failures}",
    )


def _verify_validator_gate(trace: ExecutionTrace, params: dict) -> VerificationResult:
    final = trace.final_attempt
    if not final or not final.validator:
        return VerificationResult(None, "no validator result on the final attempt to check the gate against")
    if final.validator.ok:
        return VerificationResult(
            False,
            "the final attempt already passed validation — the gate would not have changed this run's outcome "
            "(it only guards against ok=false slipping through)",
        )
    return VerificationResult(
        True,
        f"the final attempt failed validation ({final.validator.failures}) — the gate would have stopped it "
        "from reaching formatting/podcast/email instead of shipping",
    )


def _verify_generation_param(trace: ExecutionTrace, params: dict) -> VerificationResult:
    field_name = params.get("field")
    value = params.get("value")
    failing = [a for a in trace.attempts if a.validator and not a.validator.ok]
    if field_name == "max_tokens" and failing:
        target = failing[-1]
        truncated = any("truncat" in f for f in target.validator.failures)
        if not truncated:
            return VerificationResult(None, "no truncation failure on record; max_tokens increase is unrelated to the observed failure")
        prior_completion = target.completion_tokens or 0
        try:
            new_value = float(value)
        except (TypeError, ValueError):
            return VerificationResult(False, f"new max_tokens value {value!r} is not numeric")
        if new_value > prior_completion * 1.2:
            return VerificationResult(
                True,
                f"new max_tokens={new_value} gives {new_value / max(prior_completion, 1):.1f}x headroom over the "
                f"{prior_completion} completion tokens used in the truncated attempt",
            )
        return VerificationResult(False, f"new max_tokens={new_value} is not meaningfully larger than the {prior_completion} tokens already used")
    return VerificationResult(None, f"no deterministic offline check for generation param {field_name!r}; needs a live regeneration")


_JUDGE_SYSTEM = """You are sanity-checking a proposed fix, not writing anything. Given a
description of a workflow failure and a corrective directive that was added to the
generation model's system prompt, answer whether the directive plausibly addresses the
stated failure. This is a coarse pre-check, not proof — a real check requires re-running
the workflow. Respond with ONLY JSON: {"plausible": <true|false>, "reason": "<one sentence>"}"""


def _verify_system_prompt_directive(trace: ExecutionTrace, params: dict, model: str) -> VerificationResult:
    failing = [a for a in trace.attempts if a.validator and not a.validator.ok]
    directive = params.get("directive", "")
    failure_desc = failing[-1].validator.failures if failing else ["(no recorded failure)"]
    user = f"Failure(s): {failure_desc}\nDirective added: {directive!r}"
    try:
        result = chat_json(_JUDGE_SYSTEM, user, model=model)
        plausible = bool(result.get("plausible"))
        reason = result.get("reason", "")
    except OllamaError as e:
        return VerificationResult(None, f"local judge unavailable ({e}); directive not yet verified against a real regeneration")
    return VerificationResult(
        None if plausible else False,
        f"[weak, non-empirical check] local-model plausibility judgment: {reason} "
        "-- TODO: replace with a real regeneration once live n8n/model API access exists",
    )


def verify(trace: ExecutionTrace, diagnosis_intervention_type: str, params: dict, model: str = DEFAULT_MODEL) -> VerificationResult:
    if diagnosis_intervention_type in ("tighten_validator_threshold", "loosen_validator_threshold"):
        return _verify_validator_threshold(trace, params)
    if diagnosis_intervention_type == "enable_preflight_check":
        return _verify_preflight(trace, params)
    if diagnosis_intervention_type == "enable_validator_gate":
        return _verify_validator_gate(trace, params)
    if diagnosis_intervention_type == "adjust_generation_params":
        return _verify_generation_param(trace, params)
    if diagnosis_intervention_type == "add_system_prompt_directive":
        return _verify_system_prompt_directive(trace, params, model)
    return VerificationResult(None, f"no verifier for intervention type {diagnosis_intervention_type!r}")
