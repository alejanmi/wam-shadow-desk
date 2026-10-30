"""Weekly market panel for the research loop, with an integrity check (L0)."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

FACTORS = {"mkt": "VOO", "oil": "CL=F", "rate": "^TNX", "usd": "DX-Y.NYB"}


@dataclass
class Panel:
    dates: list[str]                 # Monday labels of each weekly bar (return rows start at dates[1])
    prices: dict[str, np.ndarray]
    sha256: str
    as_of: str                       # last bar used for estimation

    def returns(self, symbol: str) -> np.ndarray:
        """Weekly log return; for the 10Y yield, the change in percentage points."""
        p = self.prices[symbol]
        return np.diff(p) if symbol == FACTORS["rate"] else np.diff(np.log(p))

    @property
    def return_dates(self) -> list[str]:
        return self.dates[1:]

    def est_slice(self) -> slice:
        """Rows used for estimation: every return up to and including the as_of bar."""
        return slice(0, self.return_dates.index(self.as_of) + 1)

    def outcome_index(self) -> int | None:
        i = self.return_dates.index(self.as_of) + 1
        return i if i < len(self.return_dates) else None


def load_panel(folder: str | Path, as_of: str = "2026-10-19", n_weeks: int = 262,
               first_monday: str = "2021-10-25", expected_sha: str | None = None) -> Panel:
    folder = Path(folder)
    series_text = (folder / "series.json").read_text(encoding="utf-8").strip()
    d0 = dt.date.fromisoformat(first_monday)
    dates = [(d0 + dt.timedelta(weeks=i)).isoformat() for i in range(n_weeks)]
    payload = '{"dates":' + json.dumps(dates, separators=(",", ":")) + ',"series":' + series_text + "}"
    sha = hashlib.sha256(payload.encode()).hexdigest()
    if expected_sha is None:
        meta = folder / "meta.json"
        expected_sha = json.loads(meta.read_text(encoding="utf-8"))["payload_sha256"] if meta.exists() else sha
    if sha != expected_sha:
        raise ValueError(f"market data does not match its recorded hash ({sha[:12]} != {expected_sha[:12]})")
    series = json.loads(series_text)
    prices = {k: np.array(v, dtype=float) for k, v in series.items()}
    if any(len(v) != n_weeks for v in prices.values()):
        raise ValueError("series length does not match the date axis")
    return Panel(dates, prices, sha, as_of)
