"""Financial Modeling Prep client: the same /stable endpoints the n8n workflow calls.

Every call goes through the SnapshotStore, so in replay mode no key is needed
and in live mode every response is hashed and kept.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlencode

from shadowdesk.ingest.snapshot import Provenance, SnapshotStore

BASE = "https://financialmodelingprep.com/stable"


def fmp_symbol(t: str) -> str:
    """Same normalization as the workflow: BRK/B and BRK.B -> BRK-B."""
    return str(t or "").upper().strip().replace("/", "-").replace(".", "-")


class FMPClient:
    def __init__(self, store: SnapshotStore, api_key: str = ""):
        self.store = store
        self.api_key = api_key

    def _get(self, endpoint: str, key: str, **params: Any) -> tuple[Any, Provenance]:
        q = {k: v for k, v in params.items() if v is not None}
        q["apikey"] = self.api_key or "REPLAY"
        url = f"{BASE}/{endpoint}?{urlencode(q, quote_via=quote)}"
        return self.store.get_json("fmp", key, url)

    # prices
    def quote(self, symbol: str):
        return self._get("quote", f"quote_{fmp_symbol(symbol)}", symbol=fmp_symbol(symbol))

    def batch_quote(self, symbols: list[str]):
        syms = ",".join(fmp_symbol(s) for s in symbols)
        return self._get("batch-quote", f"batch-quote_{syms}", symbols=syms)

    def historical_eod(self, symbol: str, frm: str, to: str | None = None):
        return self._get("historical-price-eod/full", f"eod_{fmp_symbol(symbol)}_{frm}_{to or ''}",
                         symbol=fmp_symbol(symbol), **{"from": frm, "to": to})

    def rsi(self, symbol: str, period: int = 14):
        return self._get("technical-indicators/rsi", f"rsi{period}_{fmp_symbol(symbol)}",
                         symbol=fmp_symbol(symbol), periodLength=period, timeframe="1day")

    # companies
    def profile(self, symbol: str):
        return self._get("profile", f"profile_{fmp_symbol(symbol)}", symbol=fmp_symbol(symbol))

    def grades(self, symbol: str):
        return self._get("grades", f"grades_{fmp_symbol(symbol)}", symbol=fmp_symbol(symbol))

    # calendars
    def earnings_calendar(self, frm: str, to: str):
        return self._get("earnings-calendar", f"earnings_{frm}_{to}", **{"from": frm, "to": to})

    def economic_calendar(self, frm: str, to: str):
        return self._get("economic-calendar", f"economic_{frm}_{to}", **{"from": frm, "to": to})

    # disclosures
    def senate_latest(self, page: int = 0, limit: int = 100):
        return self._get("senate-latest", f"senate_p{page}", page=page, limit=limit)

    def house_latest(self, page: int = 0, limit: int = 100):
        return self._get("house-latest", f"house_p{page}", page=page, limit=limit)

    def insider_latest(self, page: int = 0, limit: int = 100):
        return self._get("insider-trading/latest", f"insider_p{page}", page=page, limit=limit)
