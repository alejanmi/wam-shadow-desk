"""FRED client plus the series the brief's macro tiles and text rely on.

`latest_with_change` returns the last valid observation, the change versus the
previous valid one, and the observation date, which is what the n8n FRED node
reports (e.g. 10Y 4.96, chg -0.17, as of 2026-10-22).
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

from shadowdesk.ingest.snapshot import Provenance, SnapshotStore

BASE = "https://api.stlouisfed.org/fred/series/observations"

# reference field (as named in the n8n FRED node output) -> FRED series id
SERIES: dict[str, str] = {
    "yield2Y": "DGS2",
    "yield10Y": "DGS10",
    "yield30Y": "DGS30",
    "spread2s10s": "T10Y2Y",
    "spread10y3m": "T10Y3M",
    "vix": "VIXCLS",
    "realYield10": "DFII10",
    "breakeven10": "T10YIE",
    "fwd5y5y": "T5YIFR",
    "hySpread": "BAMLH0A0HYM2",
    "igSpread": "BAMLC0A0CM",
    "cccSpread": "BAMLH0A3HYC",
    "bbSpread": "BAMLH0A1HYBB",
    "fedUpper": "DFEDTARU",
    "fedLower": "DFEDTARL",
    "mortgage30": "MORTGAGE30US",
    "dollarIndex": "DTWEXBGS",
    "nfci": "NFCI",
    "claimsK": "ICSA",
    "unemployment": "UNRATE",
    "brent": "DCOILBRENTEU",
    "wtiFred": "DCOILWTICO",
    "termPremium": "THREEFYTP10",
    "gdpNow": "GDPNOW",
}

# how many days old a reading may be before it must not be presented as current
MAX_AGE_DAYS: dict[str, int] = {
    "daily": 5, "weekly": 12, "monthly": 45, "quarterly": 100,
}
SERIES_FREQ: dict[str, str] = {
    "MORTGAGE30US": "weekly", "NFCI": "weekly", "ICSA": "weekly", "DTWEXBGS": "weekly",
    "UNRATE": "monthly", "GDPNOW": "quarterly", "THREEFYTP10": "weekly",
}


@dataclass(frozen=True)
class Reading:
    series_id: str
    value: float
    change: float | None
    date: str
    prov: Provenance


def parse_observations(payload: dict) -> list[tuple[str, float]]:
    out = []
    for o in payload.get("observations", []):
        v = o.get("value")
        if v in (None, "", "."):
            continue
        try:
            out.append((o["date"], float(v)))
        except (TypeError, ValueError, KeyError):
            continue
    return out


class FREDClient:
    def __init__(self, store: SnapshotStore, api_key: str = ""):
        self.store = store
        self.api_key = api_key

    def observations(self, series_id: str, start: str, end: str | None = None):
        q = {"series_id": series_id, "observation_start": start, "file_type": "json",
             "api_key": self.api_key or "REPLAY"}
        if end:
            q["observation_end"] = end
        return self.store.get_json("fred", f"{series_id}_{start}_{end or ''}", f"{BASE}?{urlencode(q)}")

    def latest_with_change(self, series_id: str, start: str, end: str | None = None) -> Reading | None:
        payload, prov = self.observations(series_id, start, end)
        obs = parse_observations(payload)
        if not obs:
            return None
        date, value = obs[-1]
        change = round(value - obs[-2][1], 6) if len(obs) > 1 else None
        return Reading(series_id, value, change, date, prov)
