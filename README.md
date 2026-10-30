# wam-shadow-desk

A research loop that runs beside the market for WAM Agentics. It rebuilds the
facts in the **Pocket Pulse** brief (n8n workflow *Retail Agent V1*) from the
same public sources **without n8n**, then audits the brief: what it reproduced,
what it got wrong, what it missed. Later phases add hypotheses that must
survive falsification before Santino sees them.

Strategy and rationale: *WAM Shadow Desk — Autoresearch Strategy for Santino* (Claude doc).
Status: **Phase 0 (one codebase) and Phase 1 (ingest + parity) are built.**

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

## Layout

```
shadowdesk/
  core/          settings (.env only), HTTP with key redaction, model policy (default-deny)
  ingest/        snapshot store (L0 provenance), FMP, FRED, SEC EDGAR, RSS, reader profiles
  compute/       line-by-line ports of the n8n Code nodes (+ *_fixed versions where the node is wrong)
  parity/        offline and live checks, Shadow Brief diff report
  ledger/        SQLite evidence ledger, experiment records, bounded runner
  research/      inquiry record + verdict tiers (Phase 3 builds on this)
  reliability/   the former AutoDetections_Santino `wam/` detector, unchanged in behaviour
config/readers/  reader profiles (annie.yaml = pilot)
fixtures/run6361 reference outputs and raw inputs exported from n8n execution 6361
docs/            strategy notes and the WAM baseline review
```

## Rules

- **Code owns verifiable facts.** Models only touch jagged domains, and are measured there.
- **No secrets in the repo.** Keys live in `.env`; URLs are redacted before they are stored.
- **Not investment advice.** The ledger holds testable statements with probabilities, never buy/sell/hold.
- **Separate from Nico's research-direction-scout.** No shared code, data or memory; borrowed ideas are listed in `docs/borrowed-ideas.md`.

## Roadmap

1. ~~Consolidate~~ 2. ~~Ingest parity~~ (live run pending on Ale's machine)
3. Ledger + falsification (N1-N5, Benjamini-Hochberg, red team) 4. Echoes x Shadows + causal do()
5. Multi-model jaggedness, calibration, Santino UI. See `docs/STRATEGY.md`.
