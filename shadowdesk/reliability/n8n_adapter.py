"""Converts a real n8n execution export into an ExecutionTrace.

Untested against a live export (this phase has no n8n API access — see
README.md) — written from n8n's documented execution-data shape:

    {
      "data": {
        "resultData": {
          "runData": {
            "<Node Name>": [ { "startTime": <ms>, "executionTime": <ms>,
                                "data": {"main": [[ {"json": {...}} ]]},
                                "error": {...}? } , ... one entry per retry ... ]
          }
        }
      }
    }

Treat this as a starting point to adjust once a real export is on hand,
not as verified-correct code. The Validator node's own output ({ok,
failures, warnings, stats, output}) is read directly rather than
re-derived, since it's the ground truth (see fixtures/README.md).
"""

from __future__ import annotations

from typing import Any

from shadowdesk.reliability.trace import ExecutionTrace, GenerationAttempt, ValidatorResult

GENERATION_NODE_CANDIDATES = ["DeepSeek", "WM_AGENT_OG"]
VALIDATOR_NODE = "Validator"


def _ms_to_iso(ms: int) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _extract_usage(node_output: dict) -> dict[str, Any]:
    for key in ("usage", "tokenUsage"):
        if key in node_output:
            return node_output[key]
    choices = node_output.get("choices")
    if choices and isinstance(choices, list):
        return node_output.get("usage", {})
    return {}


def from_n8n_export(export: dict, run_id: str, mode: str = "hybrid") -> ExecutionTrace:
    run_data = export.get("data", {}).get("resultData", {}).get("runData", {})

    gen_node = next((n for n in GENERATION_NODE_CANDIDATES if n in run_data), None)
    if gen_node is None:
        raise ValueError(f"no generation node found in export runData (looked for {GENERATION_NODE_CANDIDATES})")

    gen_runs = run_data[gen_node]
    validator_runs = run_data.get(VALIDATOR_NODE, [])

    attempts = []
    for i, run in enumerate(gen_runs):
        start_ms = run.get("startTime", 0)
        duration_ms = run.get("executionTime", 0)
        error = run.get("error", {}).get("message") if run.get("error") else None

        try:
            gen_output = run["data"]["main"][0][0]["json"]
        except (KeyError, IndexError, TypeError):
            gen_output = {}

        usage = _extract_usage(gen_output)
        output_text = str(
            gen_output.get("output")
            or (gen_output.get("choices", [{}])[0].get("message", {}).get("content") if gen_output.get("choices") else None)
            or gen_output.get("text")
            or ""
        )

        validator_result = None
        if i < len(validator_runs):
            try:
                v_json = validator_runs[i]["data"]["main"][0][0]["json"]
                validator_result = ValidatorResult(
                    ok=v_json.get("ok", False),
                    failures=v_json.get("failures", []),
                    warnings=v_json.get("warnings", []),
                    stats=v_json.get("stats", {}),
                )
            except (KeyError, IndexError, TypeError):
                pass

        attempts.append(
            GenerationAttempt(
                attempt_index=i + 1,
                model=gen_node,
                started_at=_ms_to_iso(start_ms),
                finished_at=_ms_to_iso(start_ms + duration_ms),
                prompt_tokens=usage.get("prompt_tokens") or usage.get("promptTokens"),
                completion_tokens=usage.get("completion_tokens") or usage.get("completionTokens"),
                reasoning_tokens=(usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                output_text=output_text,
                validator=validator_result,
                error=error,
            )
        )

    return ExecutionTrace(run_id=run_id, workflow_name=export.get("workflowData", {}).get("name", "Santi Miguel AI Agent (F)"), mode=mode, attempts=attempts)
