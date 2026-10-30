"""Reader profile: what one reader holds, watches, follows and worries about."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-/]{0,6}$")

# Tickers people commonly type that are not the listed symbol.
KNOWN_ALIASES = {"CITI": "C", "GOOGLE": "GOOGL", "FACEBOOK": "META", "BRK.B": "BRK-B"}


@dataclass
class Sensitivity:
    scenario: str
    concern: int | None


@dataclass
class ReaderProfile:
    reader: str
    display_name: str
    holdings: list[str]
    watchlist: list[str]
    topics: list[str] = field(default_factory=list)
    people: list[dict] = field(default_factory=list)
    sensitivities: list[Sensitivity] = field(default_factory=list)
    product: str = "Pocket Pulse"

    @property
    def all_tickers(self) -> list[str]:
        seen, out = set(), []
        for t in self.holdings + self.watchlist:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out

    def ticker_issues(self) -> list[str]:
        """Tickers that will fail lookups, with the likely intended symbol."""
        issues = []
        for t in self.all_tickers:
            if not TICKER_RE.match(t):
                issues.append(f"{t}: not a valid ticker format")
            elif t in KNOWN_ALIASES:
                issues.append(f"{t}: not a listed symbol; did you mean {KNOWN_ALIASES[t]}?")
        return issues

    def top_sensitivities(self, min_concern: int = 7) -> list[Sensitivity]:
        return sorted((s for s in self.sensitivities if (s.concern or 0) >= min_concern),
                      key=lambda s: -(s.concern or 0))


def load_reader(path: str | Path) -> ReaderProfile:
    d = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    up = lambda xs: [str(x).upper().strip() for x in (xs or []) if str(x).strip()]
    return ReaderProfile(
        reader=d["reader"],
        display_name=d.get("display_name", d["reader"]),
        holdings=up(d.get("holdings")),
        watchlist=up(d.get("watchlist")),
        topics=list(d.get("topics") or []),
        people=list(d.get("people") or []),
        sensitivities=[Sensitivity(s["scenario"], s.get("concern")) for s in d.get("sensitivities") or []],
        product=d.get("product", "Pocket Pulse"),
    )
