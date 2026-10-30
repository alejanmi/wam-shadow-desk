# Fixtures

Synthetic `ExecutionTrace` JSON files (see `wam/trace.py`) standing in for
real n8n execution exports, until live n8n API access is wired up. Each one
is grounded in an actual failure mode the workflow's own `Validator` node
checks for (see `wam/validator_port.py`, a manual port of the Validator
node's real jsCode) — brief text was generated and passed through that
same validator so the `validator` block in each fixture is a real,
verified result, not hand-typed.

| File | Scenario |
|---|---|
| `execution_ok.json` | Clean pass, one attempt. |
| `execution_truncated_joke_block.json` | Generation hit `max_tokens` and stopped right before the closing joke block — output looks complete-ish but fails the truncation tripwire. |
| `execution_retry_storm.json` | The same truncation failure, 3 attempts in a row, each ~28 minutes — the workflow's blind `retryOnFail` re-running the identical failing call rather than diagnosing it. |
| `execution_missing_section_and_placeholder.json` | Model dropped the `situations` section entirely and left a `[TICKER]` placeholder and an em dash in the output. |
| `execution_preflight_catchable.json` | Upstream payload was thin (5 news items, no `sectorExposure`) but generation ran anyway for ~13 minutes before failing structurally — the disabled Pre-Flight check (see `wam/preflight_port.py`) would have caught this before spending the attempt. Includes `input_payload`. |

## Adding a real one

Once n8n execution export access exists, a real trace should be converted
into this same shape: one `GenerationAttempt` per retry/fallback attempt,
each carrying the model, timestamps, token usage, and the Validator node's
own `{ok, failures, warnings, stats}` output verbatim (no need to re-derive
it — the real Validator node's output *is* ground truth; `validator_port.py`
exists only for offline replay/verification, not to second-guess it).
