"""Applies a Diagnosis to a copy of the n8n workflow JSON.

Deliberately NOT freeform LLM-authored patching: the diagnostic agent picks
from a small, fixed vocabulary of intervention types (see
wam/diagnostics.py:KNOWN_INTERVENTION_TYPES) and supplies parameters; this
module is what actually knows how to turn each one into a concrete,
reviewable edit of the real workflow nodes:

- "Edit Fields" (n8n-nodes-base.set)  -> assembles systemPrompt/userMessage
- "DeepSeek" (httpRequest)            -> the live generation call + its params
- "Validator" (code)                  -> the structural checks and their thresholds
- "Analyst desk rollup" -> "Edit Fields" -> where a pre-flight gate gets inserted

Every patch is idempotent (re-applying the same directive twice is a no-op)
and every function returns a fresh workflow dict — callers own committing
the result to disk/git.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from shadowdesk.reliability.diagnostics import Diagnosis

DIRECTIVE_MARKER = "WAM-INTERVENTION"


@dataclass
class InterventionResult:
    applied: bool
    description: str
    notes: list[str] = field(default_factory=list)
    workflow: Optional[dict] = None


def _find_node(workflow: dict, name: str) -> dict:
    for n in workflow["nodes"]:
        if n["name"] == name:
            return n
    raise KeyError(f"node not found in workflow: {name!r}")


def _find_assignment(node: dict, field_name: str) -> dict:
    for a in node["parameters"]["assignments"]["assignments"]:
        if a["name"].lstrip("=") == field_name:
            return a
    raise KeyError(f"assignment not found: {field_name!r} on node {node['name']!r}")


def _apply_add_system_prompt_directive(workflow: dict, params: dict[str, Any]) -> InterventionResult:
    directive = (params.get("directive") or "").strip()
    if not directive:
        return InterventionResult(False, "no directive text supplied")

    node = _find_node(workflow, "Edit Fields")
    assignment = _find_assignment(node, "systemPrompt")
    digest = hashlib.sha256(directive.encode("utf-8")).hexdigest()[:12]
    open_marker = f"<!-- {DIRECTIVE_MARKER}:{digest} -->"
    if open_marker in assignment["value"]:
        return InterventionResult(False, "directive already present (idempotent no-op)", [f"digest {digest} already applied"])

    close_marker = f"<!-- /{DIRECTIVE_MARKER}:{digest} -->"
    block = f"\n\n{open_marker}\n{directive}\n{close_marker}\n"
    assignment["value"] = assignment["value"] + block
    return InterventionResult(
        True,
        f"appended corrective directive to Edit Fields.systemPrompt: {directive!r}",
        [f"marker {digest}"],
        workflow,
    )


_GEN_PARAM_FIELDS = {"max_tokens", "temperature", "top_p"}


def _apply_adjust_generation_params(workflow: dict, params: dict[str, Any]) -> InterventionResult:
    gen_field = params.get("field")
    value = params.get("value")
    if gen_field not in _GEN_PARAM_FIELDS:
        return InterventionResult(False, f"unsupported generation param: {gen_field!r} (allowed: {_GEN_PARAM_FIELDS})")
    node = _find_node(workflow, "DeepSeek")
    body = node["parameters"]["jsonBody"]
    pattern = re.compile(rf"({re.escape(gen_field)}\s*:\s*)[0-9.]+")
    if not pattern.search(body):
        return InterventionResult(False, f"could not find {gen_field!r} literal in DeepSeek jsonBody")
    new_body = pattern.sub(lambda m: f"{m.group(1)}{value}", body, count=1)
    if new_body == body:
        return InterventionResult(False, "no change (value already set)")
    node["parameters"]["jsonBody"] = new_body
    return InterventionResult(True, f"set DeepSeek generation param {gen_field}={value}", [], workflow)


# Maps a validator "check name" (as used in Validator.stats / detector evidence)
# to the numeric literal in its jsCode that enforces the threshold.
_VALIDATOR_THRESHOLDS = {
    "chars_min": r"(chars\s*<\s*)(\d+)",
    "chars_max": r"(chars\s*>\s*)(\d+)",
    "pbItems": r"(pbItems\s*!==\s*)(\d+)",
    "mv": r"(mv\s*!==\s*)(\d+)",
    "blind": r"(blind\s*!==\s*)(\d+)",
    "ap": r"(ap\s*!==\s*)(\d+)",
    "secNews": r"(secNews\s*!==\s*)(\d+)",
}


def _apply_validator_threshold(workflow: dict, params: dict[str, Any]) -> InterventionResult:
    check = params.get("check")
    value = params.get("value")
    pattern_src = _VALIDATOR_THRESHOLDS.get(check)
    if pattern_src is None:
        return InterventionResult(False, f"unsupported validator check: {check!r} (allowed: {list(_VALIDATOR_THRESHOLDS)})")
    node = _find_node(workflow, "Validator")
    code = node["parameters"]["jsCode"]
    pattern = re.compile(pattern_src)
    if not pattern.search(code):
        return InterventionResult(False, f"could not find threshold literal for {check!r} in Validator jsCode")
    new_code = pattern.sub(lambda m: f"{m.group(1)}{value}", code, count=1)
    if new_code == code:
        return InterventionResult(False, "no change (value already set)")
    node["parameters"]["jsCode"] = new_code
    return InterventionResult(True, f"changed Validator threshold {check} -> {value}", [], workflow)


_PREFLIGHT_CODE = """\
// Auto-inserted by the WAM self-improvement loop (enable_preflight_check).
// Ported from the commented-out "NODE B" reference in the Validator node:
// checks the aggregated payload BEFORE the ~15-minute generation call, so a
// broken/incomplete payload fails fast instead of wasting a full attempt.
const p = $input.first().json;
const failures = [];
const warnings = [];
const len = (v) => Array.isArray(v) ? v.length : (v && typeof v === 'object' ? Object.keys(v).length : (v ? String(v).length : 0));

if (!p.Ticker || String(p.Ticker).trim().length < 2) failures.push('no holdings (Ticker empty)');
if (!p.advisorName) failures.push('no advisorName');
if (!p.Mode) warnings.push('no Mode (hybrid assumed by prompt)');
if (!p.bookMove && !p.BookMove) failures.push('no BOOK MOVE block');
if (len(p.newsContext) < 20) failures.push('newsContext has ' + len(p.newsContext) + ' items (expected 60 to 100)');
if (len(p.macroContext) < 10) failures.push('macroContext has ' + len(p.macroContext) + ' series');
if (len(p.holdingsPerf) < 3) failures.push('holdingsPerf has ' + len(p.holdingsPerf) + ' rows');
if (!p.sectorExposure) failures.push('no sectorExposure');
if (!p.fixedIncome && !p.fi) warnings.push('no fixed income block');
if (!p.earningsThisWeek) warnings.push('no earningsThisWeek');
if (!p.economicCalendar) warnings.push('no economicCalendar');
if (p.quoteFailures && len(p.quoteFailures) > 3) warnings.push('quote failures: ' + len(p.quoteFailures));
if (!p.smartMoney || p.smartMoney.hasData === false) warnings.push('smartMoney empty (Hedge Fund Flow will be omitted)');

const payloadChars = JSON.stringify(p).length;
if (payloadChars < 150000) failures.push('payload only ' + payloadChars + ' chars (expected ~400k)');

return [{ json: Object.assign({}, p, { preflight: { ok: failures.length === 0, failures, warnings, payloadChars, checkedAt: new Date().toISOString() } }) }];
"""


def _rewire(workflow: dict, source: str, old_target: str, new_target: str) -> None:
    for branch in workflow["connections"][source]["main"]:
        for c in branch:
            if c["node"] == old_target:
                c["node"] = new_target


def _apply_enable_preflight_check(workflow: dict, params: dict[str, Any]) -> InterventionResult:
    for n in workflow["nodes"]:
        if n["name"] == "Pre-Flight Check":
            return InterventionResult(False, "pre-flight check already inserted (idempotent no-op)")

    upstream = _find_node(workflow, "Analyst desk rollup")
    downstream_name = "Edit Fields"
    _find_node(workflow, downstream_name)  # raises if missing

    max_id = max((n.get("id", "") for n in workflow["nodes"]), key=len, default="")
    preflight_node = {
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [upstream["position"][0] + 120, upstream["position"][1] + 200],
        "id": "wam-preflight-" + hashlib.sha256(json.dumps(workflow.get("id", "")).encode()).hexdigest()[:8],
        "name": "Pre-Flight Check",
        "parameters": {"jsCode": _PREFLIGHT_CODE},
    }
    gate_node = {
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": [preflight_node["position"][0] + 200, preflight_node["position"][1]],
        "id": "wam-preflight-gate-" + preflight_node["id"][-8:],
        "name": "Preflight Gate",
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                "conditions": [
                    {
                        "leftValue": "={{ $json.preflight.ok }}",
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                    }
                ],
                "combinator": "and",
            },
        },
    }
    alert_node = {
        "type": "n8n-nodes-base.noOp",
        "typeVersion": 1,
        "position": [gate_node["position"][0] + 200, gate_node["position"][1] + 150],
        "id": "wam-preflight-alert-" + preflight_node["id"][-8:],
        "name": "Preflight Failed (needs alert wiring)",
    }

    workflow["nodes"] += [preflight_node, gate_node, alert_node]

    # Analyst desk rollup -> Pre-Flight Check -> Preflight Gate -> [true] Edit Fields, [false] alert stub
    _rewire(workflow, "Analyst desk rollup", downstream_name, "Pre-Flight Check")
    workflow["connections"]["Pre-Flight Check"] = {"main": [[{"node": "Preflight Gate", "type": "main", "index": 0}]]}
    workflow["connections"]["Preflight Gate"] = {
        "main": [
            [{"node": downstream_name, "type": "main", "index": 0}],
            [{"node": "Preflight Failed (needs alert wiring)", "type": "main", "index": 0}],
        ]
    }
    return InterventionResult(
        True,
        "inserted Pre-Flight Check + Preflight Gate between Analyst desk rollup and Edit Fields",
        ["failing branch currently routes to a NoOp stub — wire real alerting before relying on this in production"],
        workflow,
    )


def _apply_enable_validator_gate(workflow: dict, params: dict[str, Any]) -> InterventionResult:
    """The Validator node already computes {ok, failures, warnings} but nothing
    in the live graph acts on it — a structurally broken brief flows straight
    through to formatting/podcast/email exactly like a good one. This inserts
    an IF node right after Validator: ok=true keeps the existing fan-out
    (today, "strip text1" and "Formatting2"), ok=false routes to a stop node
    instead of shipping. Mirrors enable_preflight_check's shape/idempotency."""
    for n in workflow["nodes"]:
        if n["name"] == "Validator Gate":
            return InterventionResult(False, "validator gate already inserted (idempotent no-op)")

    validator = _find_node(workflow, "Validator")
    validator_conns = workflow["connections"].get("Validator", {}).get("main", [])
    old_targets = [c["node"] for branch in validator_conns for c in branch]
    if not old_targets:
        return InterventionResult(False, "Validator has no outgoing connections to gate")

    gate_id = "wam-validator-gate-" + hashlib.sha256(json.dumps(workflow.get("id", "")).encode()).hexdigest()[:8]
    gate_node = {
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": [validator["position"][0] + 200, validator["position"][1]],
        "id": gate_id,
        "name": "Validator Gate",
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                "conditions": [
                    {
                        "leftValue": "={{ $json.ok }}",
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                    }
                ],
                "combinator": "and",
            },
        },
    }
    stop_node = {
        "type": "n8n-nodes-base.noOp",
        "typeVersion": 1,
        "position": [gate_node["position"][0] + 200, gate_node["position"][1] + 150],
        "id": "wam-validator-stop-" + gate_id[-8:],
        "name": "Validator Failed (needs alert wiring)",
    }

    workflow["nodes"] += [gate_node, stop_node]
    workflow["connections"]["Validator"] = {"main": [[{"node": "Validator Gate", "type": "main", "index": 0}]]}
    workflow["connections"]["Validator Gate"] = {
        "main": [
            [{"node": t, "type": "main", "index": 0} for t in old_targets],
            [{"node": "Validator Failed (needs alert wiring)", "type": "main", "index": 0}],
        ]
    }
    return InterventionResult(
        True,
        f"inserted Validator Gate after Validator: ok=true -> {old_targets}, ok=false -> stop node",
        ["failing branch currently routes to a NoOp stub — wire real alerting before relying on this for unattended runs"],
        workflow,
    )


def _apply_flag_for_human_review(workflow: dict, params: dict[str, Any]) -> InterventionResult:
    return InterventionResult(False, f"flagged for human review: {params.get('reason', '(no reason given)')}")


_HANDLERS = {
    "add_system_prompt_directive": _apply_add_system_prompt_directive,
    "enable_preflight_check": _apply_enable_preflight_check,
    "enable_validator_gate": _apply_enable_validator_gate,
    "adjust_generation_params": _apply_adjust_generation_params,
    "tighten_validator_threshold": _apply_validator_threshold,
    "loosen_validator_threshold": _apply_validator_threshold,
    "flag_for_human_review": _apply_flag_for_human_review,
}


def apply_intervention(workflow: dict, diagnosis: Diagnosis) -> InterventionResult:
    """Applies diagnosis.intervention_type to a deep copy of `workflow`.

    Never mutates the input. `flag_for_human_review` and any handler that
    declines to act return applied=False with workflow=None.
    """
    handler = _HANDLERS.get(diagnosis.intervention_type)
    if handler is None:
        return InterventionResult(False, f"no handler registered for intervention type {diagnosis.intervention_type!r}")
    wf_copy = copy.deepcopy(workflow)
    return handler(wf_copy, diagnosis.intervention_params)
