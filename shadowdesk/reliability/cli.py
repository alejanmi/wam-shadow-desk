"""Command-line entrypoint for one loop pass: run every trace in a directory
through Detect -> Diagnose -> Intervene -> Verify -> Learn against one
workflow file, printing a summary and updating the learning memory.

    uv run python -m shadowdesk.reliability.cli fixtures/

program.md's LOOP FOREVER drives this per-trace, deciding what to do with
a "success" outcome (write the patched workflow, commit) the same way the
original autoresearch program.md decided what to do with an improved
val_bpb — this file only runs one pass and reports what happened.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from shadowdesk.reliability.loop import RunResult, load_workflow, run_once, save_workflow
from shadowdesk.reliability.memory import LearningMemory
from shadowdesk.reliability.trace import ExecutionTrace


def _print_result(result: RunResult) -> None:
    print(f"\n=== {result.trace_run_id} ===")
    if not result.anomalies:
        print("  no anomalies detected")
        return
    for a in result.anomalies:
        print(f"  [{a.severity:8s}] {a.signal}: {a.summary}")
    d = result.diagnosis
    if d:
        print(f"  diagnosis: {d.what_happened}")
        print(f"    why: {d.why}")
        if d.error:
            print(f"    (diagnostic agent error: {d.error})")
        print(f"    -> intervention: {d.intervention_type} {d.intervention_params}")
    if result.intervention:
        status = "applied" if result.intervention.applied else "not applied"
        print(f"  intervention {status}: {result.intervention.description}")
    if result.verification:
        print(f"  verification: passed={result.verification.passed} — {result.verification.detail}")
    print(f"  outcome: {result.outcome}")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", type=Path, help="a trace JSON file, or a directory of them")
    parser.add_argument("--workflow", type=Path, default=Path("shadowdesk/reliability/assets/advisor_workflow_redacted.json"))
    parser.add_argument("--memory", type=Path, default=Path("data/wam_memory.db"))
    parser.add_argument("--apply-verified", action="store_true", help="write the patched workflow to --out when verification passes")
    parser.add_argument("--out", type=Path, default=Path("data/advisor_workflow.patched.json"))
    args = parser.parse_args(argv)

    trace_paths = sorted(args.traces.glob("*.json")) if args.traces.is_dir() else [args.traces]
    if not trace_paths:
        print(f"no trace files found at {args.traces}", file=sys.stderr)
        return 1

    workflow = load_workflow(args.workflow)
    memory = LearningMemory(args.memory)
    successes = 0
    try:
        for path in trace_paths:
            trace = ExecutionTrace.load(path)
            result = run_once(trace, workflow, memory)
            _print_result(result)
            if result.outcome == "success" and result.intervention and result.intervention.workflow:
                successes += 1
                if args.apply_verified:
                    save_workflow(result.intervention.workflow, args.out)
                    print(f"  wrote verified patch to {args.out}")
    finally:
        memory.close()

    print(f"\n{len(trace_paths)} trace(s) processed, {successes} verified intervention(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
