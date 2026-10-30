"""Command line.

  python -m shadowdesk replay                 # offline: rebuild run 6361 from fixtures, write the diff
  python -m shadowdesk parity --live          # re-fetch the session from FMP/FRED/SEC (needs .env keys)
  python -m shadowdesk parity                 # same comparison, from snapshots already on disk
  python -m shadowdesk verify-snapshots       # re-hash every stored response (L0)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from shadowdesk.core.config import Settings, require
from shadowdesk.core.http import fetch
from shadowdesk.ingest.fmp import FMPClient
from shadowdesk.ingest.fred import FREDClient
from shadowdesk.ingest.reader import load_reader
from shadowdesk.ingest.sec import SECClient
from shadowdesk.ingest.snapshot import SnapshotStore
from shadowdesk.ledger.store import Ledger
from shadowdesk.parity.checks import RunFixtures, live_checks, offline_checks
from shadowdesk.parity.report import write_reports


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--fixtures", default="fixtures/run6361")
    p.add_argument("--reader", default="config/readers/annie.yaml")
    p.add_argument("--out", default=None, help="report directory (default: reports/ or <data>/reports for live)")


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles (lesson from AutoDetections)
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(prog="shadowdesk")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay", help="offline parity against the run fixtures")
    _common(r)
    p = sub.add_parser("parity", help="compare a re-fetched session against the run")
    _common(p)
    p.add_argument("--session", default="2026-10-23", help="trading day the brief describes")
    p.add_argument("--live", action="store_true", help="fetch missing snapshots from the network")
    v = sub.add_parser("verify-snapshots")
    v.add_argument("--session", default="2026-10-23")
    a = ap.parse_args(argv)

    settings = Settings.from_env()
    if a.cmd == "verify-snapshots":
        bad = SnapshotStore(settings.data_dir / "snapshots", a.session).verify()
        print("all snapshots verified" if not bad else "hash mismatch:\n" + "\n".join(bad))
        return 1 if bad else 0

    fx = RunFixtures.load(a.fixtures)
    reader = load_reader(a.reader)
    run_id = fx.market["run"]["id"]
    if a.cmd == "replay":
        checks = offline_checks(fx, reader)
        name, title = f"parity-run{run_id}-offline", f"Shadow Brief diff · run {run_id} · {reader.display_name} · offline replay"
        out_dir = a.out or "reports"
    else:
        mode = "live" if a.live else "replay"
        store = SnapshotStore(settings.data_dir / "snapshots", a.session, mode=mode, fetcher=fetch if a.live else None)
        fmp = FMPClient(store, require("FMP_API_KEY") if a.live else "")
        fred = FREDClient(store, require("FRED_API_KEY") if a.live else "")
        sec = SECClient(store, require("SEC_USER_AGENT") if a.live else "")
        checks = offline_checks(fx, reader) + live_checks(fx, reader, fmp, fred, sec, a.session)
        name, title = f"parity-run{run_id}-{a.session}", f"Shadow Brief diff · run {run_id} · {reader.display_name} · session {a.session}"
        out_dir = a.out or str(settings.data_dir / "reports")

    ledger = Ledger(settings.data_dir / "ledger.db")
    ledger.add_checks(f"{run_id}:{a.cmd}", checks)
    ledger.close()
    md, js = write_reports(out_dir, name, title, checks)
    n_find = sum(c.status == "finding" for c in checks)
    n_fail = sum(c.status == "fail" for c in checks)
    n_pass = sum(c.status == "pass" for c in checks)
    print(f"{n_pass} reproduced, {n_find} findings, {n_fail} failures -> {md}")
    return 0 if n_fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
