# wam-shadow-desk

A research loop that runs beside the market for WAM Agentics. It rebuilds the
facts in the **Pocket Pulse** brief (n8n workflow *Retail Agent V1*) from the
same public sources **without n8n**, then audits the brief: what it reproduced,
what it got wrong, what it missed. Later phases add hypotheses that must
survive falsification before Santino sees them.

Strategy and rationale: *WAM Shadow Desk — Autoresearch Strategy for Santino* (Claude doc).
Status: **Phases 0-1 built (one codebase, ingest + parity). Phase 3 started: first falsification run (research run 001).**

## Quick start (Windows PowerShell)

```powershell
cd C:\Users\aleja\source\repos\wam-shadow-desk
py -3.12 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m pytest -q -m "not slow"     # ~1 s; drop the filter to include the 2-min reliability suite
python -m shadowdesk replay            # offline: rebuild run 6361, write reports\parity-run6361-offline.md
```

Live re-fetch of the Oct 23 session (needs **newly rotated** keys in `.env`; copy `.env.example`):

```powershell
python -m shadowdesk parity --live --session 2026-10-23
python -m shadowdesk verify-snapshots --session 2026-10-23
```

Every response is stored once under `data\snapshots\<session>\` with its SHA-256,
so the second run of `parity` (without `--live`) needs no network and no keys.

## What the offline replay of run 6361 shows

6 brief facts reproduced exactly from ported logic (breadth, top movers, sector
extremes, S&P regime signal, average RSI, the 6 rating actions) and 11 findings, including:

| Severity | Finding |
| --- | --- |
| high | Week Ahead lists only AMZN; the brief's own text says MSFT and GOOG report Oct 28 |
| high | Loop Capital's AAPL downgrade (Oct 20) was cut in favour of six routine reiterations |
| medium | Annie's top-rated risk (Hormuz oil shock, 8/10) moved: crude +3.8%, Energy best sector; never linked |
| medium | Two VIX values on one page (19.45 tile, 19.03 text); "today" tiles show Oct 22 rates |
| medium | Google News feed never reached the aggregator; `CITI` is not a ticker (Citigroup is `C`) |

Each finding in the report carries the exact query that reproduces it.

## Research run 001: do WAM's conclusions hold up?

`python -m shadowdesk research` turns the brief's conclusions into falsifiable
statements and tests them against 5 years of weekly prices (hash-verified
fixture, estimation ends at the session the brief describes; no lookahead).
Full write-up: `reports/research-run-001.md`.

- **0 of 7** testable conclusions in the Oct 24 brief are corroborated; 1 is untestable as written.
  Example: "AT&T and J&J use fuel, MSFT and ORCL less exposed": AT&T's market-adjusted oil
  elasticity is actually positive (+0.07); "rates reach AT&T most directly": JNJ is more rate-sensitive.
- **AT&T's -11.3% week was 102% company-specific** (factors explain +0.3%), while the brief framed AT&T through rates.
- **Annie's Hormuz scenario as do(WTI +10%)**: no measurable basket loss on 2021-26 data (+0.13%, placebo passes);
  a supply-shock instrument is the next experiment.
- **The falsifier is checked first**: 1,000 synthetic nulls give a 5.8% false-positive rate at α = 5%;
  power 72% on a planted effect the size of one standard error.

## Layout

```
shadowdesk/
  core/          settings (.env only), HTTP with key redaction, model policy (default-deny)
  ingest/        snapshot store (L0 provenance), FMP, FRED, SEC EDGAR, RSS, reader profiles
  compute/       line-by-line ports of the n8n Code nodes (+ *_fixed versions where the node is wrong)
  parity/        offline and live checks, Shadow Brief diff report
  ledger/        SQLite evidence ledger, experiment records, bounded runner
  research/      inquiry record + verdict tiers; factor tests, bootstrap/window/walk-forward nulls,
                 Benjamini-Hochberg, do() with placebo, falsifier self-test, run report
  reliability/   the former AutoDetections_Santino `wam/` detector, unchanged in behaviour
config/readers/  reader profiles (annie.yaml = pilot)
fixtures/run6361 reference outputs and raw inputs exported from n8n execution 6361
fixtures/market_weekly  5y weekly prices (14 series), SHA-256 verified on every load
docs/            strategy notes and the WAM baseline review
```

## Rules

- **Code owns verifiable facts.** Models only touch jagged domains, and are measured there.
- **No secrets in the repo.** Keys live in `.env`; URLs are redacted before they are stored.
- **Not investment advice.** The ledger holds testable statements with probabilities, never buy/sell/hold.
- **Separate from Nico's research-direction-scout.** No shared code, data or memory; borrowed ideas are listed in `docs/borrowed-ideas.md`.

## Roadmap

1. ~~Consolidate~~ 2. ~~Ingest parity~~ (live run pending on Ale's machine)
3. Ledger + falsification: **started** (N1, N2, N4, BH, do() + placebo, self-test). Next: N3, N5, event-day
   instrument for supply shocks, margin data for W2-type claims, model red team (L6) once a model endpoint is configured
4. Echoes x Shadows + causal do()
5. Multi-model jaggedness, calibration, Santino UI. See `docs/STRATEGY.md`.
