# Strategy notes (code-side summary)

The full strategy lives in the Claude doc *WAM Shadow Desk — Autoresearch Strategy for Santino*.
This file keeps the definitions the code depends on.

## Evaluation layers

| Layer | Question | Owner |
| --- | --- | --- |
| L0 Provenance | Does every number trace to a stored, hashed response? | `ingest/snapshot.py` |
| L1 Freshness and consistency | Inside its age limit; one value per series per page? | `parity/checks.py`, `ingest/fred.py:MAX_AGE_DAYS` |
| L2 Arithmetic | Do derived numbers recompute exactly? | `compute/brief_facts.py` |
| L3 Grounding | Is each sentence backed by a retrieved document? | Phase 3 |
| L4 Statistical | Survived nulls N1-N5 after Benjamini-Hochberg? | Phase 3 |
| L5 Causal | do() effect identified, adjustment set stated, placebo passes? | Phase 4 |
| L6 Interpretive | Narrative sound; red team (different model) loses? | Phase 5 |
| L7 Outcome | Forecast right at its resolution date, and how early? | Phase 3 onward |

## Null levels (adapted from Echoes & Shadows)

- **N1 Echo null** - deviation indistinguishable from the series' own noise (block bootstrap).
- **N2 Shadow null** - path-coefficient change within normal rolling variance (permutation).
- **N3 Coincidence null** - Echo and Shadow co-occur by chance (shuffled time).
- **N4 Lead-time null** - pattern did not precede moves more than chance (walk-forward, no lookahead).
- **N5 Already-priced null** - effect already in prices when the claim was made (event study).

## Verdict tiers

Computed in `research/inquiry.py` from layers passed, never set by hand:
Fact, Verified, Supported, Contested, Jagged, Refuted, Untestable.

## Phase exit tests

| Phase | Exit |
| --- | --- |
| 0 Consolidate | Former AutoDetections tests pass in the new layout; no secret in repo or history. **Done.** |
| 1 Ingest parity | Replaying Oct 24 reproduces run 6361's numbers; every difference explained. **Offline done; live pending.** |
| 2-3 Ledger + falsification | On 60 replayed days, survival rate stable and < ~15%; planted fake signals caught. **Run 001: 1 day, 11 tests, survival 0/11; self-test FPR 5.8% ± 0.7% at α=5%, power 72%.** |
| 4 Echoes, Shadows, causal | >= 1 dual-plane pattern passes N4 over >= 12 months, lead time reported. |
| 5 Models + UI | 30 daily Shadow Briefs; 50+ resolved forecasts on a reliability diagram; first proposal to WAM. |
