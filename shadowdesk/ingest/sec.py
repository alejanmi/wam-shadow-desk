"""SEC EDGAR, read directly (no FMP in the middle).

EDGAR's submissions JSON already carries the 8-K item codes (e.g. "2.02" =
results of operations), so the loop does not need to download and regex the
filing document the way the n8n SEC node does. SEC requires a descriptive
User-Agent with a contact address (SEC_USER_AGENT in .env).
"""

from __future__ import annotations

from dataclasses import dataclass

from shadowdesk.ingest.snapshot import Provenance, SnapshotStore

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

ITEM_MEANING = {
    "1.01": "material agreement", "1.03": "bankruptcy", "1.05": "cybersecurity incident",
    "2.02": "quarterly or annual results", "2.05": "restructuring costs", "2.06": "impairment",
    "3.01": "delisting notice", "4.02": "restatement of past financials",
    "5.02": "executive or director change", "7.01": "Regulation FD disclosure", "8.01": "other events",
    "9.01": "exhibits",
}


@dataclass(frozen=True)
class Filing:
    symbol: str
    form: str
    filed: str
    accession: str
    items: tuple[str, ...]
    url: str
    prov: Provenance


class SECClient:
    def __init__(self, store: SnapshotStore, user_agent: str = ""):
        self.store = store
        self.headers = {"User-Agent": user_agent or "wam-shadow-desk replay", "Accept-Encoding": "identity"}

    def cik_map(self) -> tuple[dict[str, int], Provenance]:
        data, prov = self.store.get_json("sec", "company_tickers", TICKERS_URL, self.headers)
        return {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}, prov

    def submissions(self, cik: int):
        return self.store.get_json("sec", f"submissions_{cik}", SUBMISSIONS_URL.format(cik=cik), self.headers)


def filings_in_window(symbol: str, cik: int, submissions: dict, prov: Provenance,
                      start: str, end: str, forms: tuple[str, ...] = ("8-K", "10-Q", "10-K")) -> list[Filing]:
    """Recent filings for one company between start and end (inclusive, YYYY-MM-DD)."""
    recent = submissions.get("filings", {}).get("recent", {})
    out: list[Filing] = []
    for i, form in enumerate(recent.get("form", [])):
        filed = recent["filingDate"][i]
        if form not in forms or not (start <= filed <= end):
            continue
        acc = recent["accessionNumber"][i]
        items_raw = (recent.get("items") or [""] * (i + 1))[i] or ""
        items = tuple(x.strip() for x in items_raw.split(",") if x.strip())
        doc = recent.get("primaryDocument", [""] * (i + 1))[i]
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}"
        out.append(Filing(symbol, form, filed, acc, items, url, prov))
    return out
