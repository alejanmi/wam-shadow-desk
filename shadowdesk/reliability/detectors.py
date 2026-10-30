"""Detection engine: behavioral signals over an ExecutionTrace.

Maps directly onto the signal list in "WAM Detection and Self-Improvement
System.txt" but grounded in what this specific workflow actually exposes:
the Validator node's ok/failures/warnings/stats, retry attempts (from
WM_AGENT_OG's retryOnFail/waitBetweenTries and the DeepSeek/Anthropic
fallback), and token usage.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from dataclasses import dataclass, field
from typing import Any, Optional

from shadowdesk.reliability.memory import LearningMemory
from shadowdesk.reliability.preflight_port import run_preflight
from shadowdesk.reliability.trace import ExecutionTrace, GenerationAttempt

# 15 minutes: the Pre-flight comment in the Validator node calls this out
# explicitly as the cost of generating against a broken payload.
DEFAULT_TIME_BUDGET_SECONDS = 15 * 60
# The DeepSeek node's own max_tokens is 32768 (see wam/interventions.py's
# _GEN_PARAM_FIELDS patch target) and briefs legitimately run 40k-140k chars
# (roughly 10k-35k tokens) — so this budget is deliberately close to that
# ceiling. It means "getting close to running out of room", not "used a lot
# of tokens"; keep it near the real cap so it doesn't fire on ordinary runs
# and get read as a *separate* problem from truncation (see
# detect_hit_generation_ceiling below for why conflating the two is wrong).
DEFAULT_COMPLETION_TOKEN_BUDGET = 30_000
DEFAULT_REASONING_TOKEN_RATIO_BUDGET = 1.5  # reasoning_tokens / completion_tokens
RESEMBLANCE_THRESHOLD = 2  # "seen before" kicks in on the 3rd occurrence

# Common max_tokens ceilings. completion_tokens landing on one of these
# alongside a truncation failure is the signature of "ran out of room", not
# "was told to write too much" — the two look similar (both are "high token
# counts") but call for opposite fixes.
_COMMON_TOKEN_CEILINGS = {2048, 4096, 8192, 16384, 32768, 65536, 128000}


@dataclass
class Anomaly:
    signal: str
    severity: str  # "warning" | "failure" | "critical"
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)
    attempt_index: Optional[int] = None


def detect_structural_issues(trace: ExecutionTrace) -> list[Anomaly]:
    anomalies = []
    for a in trace.attempts:
        if a.error:
            anomalies.append(
                Anomaly("execution_error", "critical", f"attempt {a.attempt_index} errored: {a.error}",
                        {"error": a.error}, a.attempt_index)
            )
            continue
        if not a.validator:
            continue
        for f in a.validator.failures:
            anomalies.append(
                Anomaly("structural_failure", "failure", f, {"raw": f}, a.attempt_index)
            )
        for w in a.validator.warnings:
            anomalies.append(
                Anomaly("structural_warning", "warning", w, {"raw": w}, a.attempt_index)
            )
    return anomalies


def detect_retry_storm(trace: ExecutionTrace) -> list[Anomaly]:
    """Same failure signature recurring across attempts = blind retry, not
    diagnosis. This is the 'circular feedback loop' / 'repeats work' failure
    mode called out in the WAM doc, expressed at the level this workflow
    actually operates at (whole-brief regeneration attempts, not tool calls)."""
    failing = [a for a in trace.attempts if a.validator and not a.validator.ok]
    if len(failing) < 2:
        return []
    sigs = [a.validator.failure_signature() for a in failing]
    if len(set(sigs)) == 1:
        return [
            Anomaly(
                "retry_storm",
                "critical" if len(failing) >= 3 else "failure",
                f"{len(failing)} consecutive attempts failed with the identical failure signature "
                f"({sigs[0][:120]}) — retries are not diagnosing anything, just repeating the same call.",
                {"attempt_indices": [a.attempt_index for a in failing], "signature": sigs[0]},
            )
        ]
    return []


def detect_excessive_time(trace: ExecutionTrace, budget_seconds: float = DEFAULT_TIME_BUDGET_SECONDS) -> list[Anomaly]:
    anomalies = []
    for a in trace.attempts:
        dur = a.duration_seconds
        if dur > budget_seconds:
            anomalies.append(
                Anomaly(
                    "excessive_time",
                    "warning" if dur < budget_seconds * 1.5 else "failure",
                    f"attempt {a.attempt_index} took {dur:.0f}s (budget {budget_seconds:.0f}s)",
                    {"duration_seconds": dur, "budget_seconds": budget_seconds},
                    a.attempt_index,
                )
            )
    return anomalies


def detect_excessive_tokens(
    trace: ExecutionTrace,
    completion_budget: int = DEFAULT_COMPLETION_TOKEN_BUDGET,
    reasoning_ratio_budget: float = DEFAULT_REASONING_TOKEN_RATIO_BUDGET,
) -> list[Anomaly]:
    anomalies = []
    for a in trace.attempts:
        if a.completion_tokens and a.completion_tokens > completion_budget:
            anomalies.append(
                Anomaly(
                    "excessive_tokens",
                    "warning",
                    f"attempt {a.attempt_index} used {a.completion_tokens} completion tokens (budget {completion_budget})",
                    {"completion_tokens": a.completion_tokens, "budget": completion_budget},
                    a.attempt_index,
                )
            )
        if a.reasoning_tokens and a.completion_tokens:
            ratio = a.reasoning_tokens / max(a.completion_tokens, 1)
            if ratio > reasoning_ratio_budget:
                anomalies.append(
                    Anomaly(
                        "reasoning_token_blowup",
                        "warning",
                        f"attempt {a.attempt_index} spent {ratio:.1f}x more tokens reasoning than writing "
                        f"({a.reasoning_tokens} reasoning vs {a.completion_tokens} completion)",
                        {"reasoning_tokens": a.reasoning_tokens, "completion_tokens": a.completion_tokens, "ratio": ratio},
                        a.attempt_index,
                    )
                )
    return anomalies


def detect_hit_generation_ceiling(trace: ExecutionTrace) -> list[Anomaly]:
    """Truncation failure + completion_tokens sitting on a round ceiling means
    the model ran out of room, not that it rambled. This is the opposite
    problem from 'excessive_tokens' and calls for the opposite fix (raise
    max_tokens / shorten required content), so it's surfaced as its own,
    unambiguous, higher-severity signal rather than left for a diagnosis
    step to disentangle from a same-run excessive_tokens anomaly."""
    anomalies = []
    for a in trace.attempts:
        if not a.validator or a.validator.ok:
            continue
        truncated = any("truncat" in f for f in a.validator.failures)
        if truncated and a.completion_tokens in _COMMON_TOKEN_CEILINGS:
            anomalies.append(
                Anomaly(
                    "hit_generation_ceiling",
                    "critical",
                    f"attempt {a.attempt_index} was truncated AND used exactly {a.completion_tokens} completion "
                    "tokens, a round max_tokens value — this is the model running out of room, not overusing "
                    "tokens. The fix is almost always to RAISE max_tokens (or shorten required output), never lower it.",
                    {"completion_tokens": a.completion_tokens},
                    a.attempt_index,
                )
            )
    return anomalies


def detect_declining_information_gain(trace: ExecutionTrace) -> list[Anomaly]:
    """If a later, more expensive attempt didn't produce materially new
    content, the retries aren't converging on anything — the model is spinning.

    Structure and length catch coarse repetition cheaply; content similarity
    catches retries that only change markup or a small amount of boilerplate.
    """
    scored = [
        a for a in trace.attempts
        if a.validator and a.validator.stats.get("chars") is not None
    ]
    if len(scored) < 2:
        return []
    anomalies = []
    for prev, cur in zip(scored, scored[1:]):
        prev_sections = prev.validator.stats.get("sections", 0)
        cur_sections = cur.validator.stats.get("sections", 0)
        prev_chars = prev.validator.stats.get("chars", 0)
        cur_chars = cur.validator.stats.get("chars", 0)
        cost_increased = (cur.completion_tokens or 0) >= (prev.completion_tokens or 0)
        no_progress = cur_sections <= prev_sections and abs(cur_chars - prev_chars) < 0.02 * max(prev_chars, 1)
        content_similarity = None
        if prev.output_text and cur.output_text:
            content_similarity = SequenceMatcher(
                None, prev.output_text, cur.output_text, autojunk=False
            ).ratio()
        repeated_content = content_similarity is not None and content_similarity >= 0.98
        if cost_increased and no_progress and repeated_content and not cur.validator.ok:
            anomalies.append(
                Anomaly(
                    "declining_information_gain",
                    "failure",
                    f"attempt {cur.attempt_index} cost at least as much as attempt {prev.attempt_index} "
                    f"but repeated nearly all of its content ({content_similarity:.1%} similarity) "
                    "without improving the structural result",
                    {
                        "prev_attempt": prev.attempt_index, "cur_attempt": cur.attempt_index,
                        "prev_sections": prev_sections, "cur_sections": cur_sections,
                        "prev_chars": prev_chars, "cur_chars": cur_chars,
                        "content_similarity": content_similarity,
                    },
                    cur.attempt_index,
                )
            )
    return anomalies


def detect_preflight_would_have_caught(trace: ExecutionTrace) -> list[Anomaly]:
    """The Pre-Flight payload check exists in the workflow's source (as a
    comment) but was never wired in. When we have the input payload and the
    run failed, check retroactively whether pre-flight would have caught it
    — if so, the model was set up to fail before it started, which is a
    materially different (and more actionable) root cause than a model or
    prompt problem. Surfaced explicitly so the diagnostic agent doesn't have
    to infer 'upstream data was thin' purely from validator symptoms."""
    if not trace.input_payload or trace.succeeded:
        return []
    result = run_preflight(trace.input_payload)
    if result.ok:
        return []
    return [
        Anomaly(
            "preflight_would_have_caught",
            "critical",
            "the upstream payload fails the (unwired) pre-flight check: " + "; ".join(result.failures)
            + " — generation ran anyway and failed structurally, wasting the full attempt on data "
            "that was never going to produce a valid brief.",
            {"preflight_failures": result.failures, "payload_chars": result.payload_chars},
        )
    ]


def detect_resembles_past_failure(trace: ExecutionTrace, memory: LearningMemory) -> list[Anomaly]:
    if trace.succeeded:
        return []
    sig = trace.behavior_signature()
    freq = memory.pattern_frequency(sig)
    times_seen = freq["times_seen"]
    if times_seen < RESEMBLANCE_THRESHOLD:
        return []
    best = memory.best_known_intervention(sig)
    summary = f"this behavior signature has appeared {times_seen} time(s) before"
    if best:
        summary += f"; a previously-verified fix exists: {best.intervention_type} ({best.intervention_description})"
    else:
        summary += "; no previously-verified fix on record"
    return [
        Anomaly(
            "resembles_past_failure",
            "warning",
            summary,
            {"behavior_signature": sig, "pattern_frequency": freq, "known_fix": best.intervention_type if best else None},
        )
    ]


def detect_all(trace: ExecutionTrace, memory: Optional[LearningMemory] = None) -> list[Anomaly]:
    anomalies: list[Anomaly] = []
    anomalies += detect_structural_issues(trace)
    anomalies += detect_retry_storm(trace)
    anomalies += detect_excessive_time(trace)
    anomalies += detect_excessive_tokens(trace)
    anomalies += detect_hit_generation_ceiling(trace)
    anomalies += detect_declining_information_gain(trace)
    anomalies += detect_preflight_would_have_caught(trace)
    if memory is not None:
        anomalies += detect_resembles_past_failure(trace, memory)
    return anomalies
