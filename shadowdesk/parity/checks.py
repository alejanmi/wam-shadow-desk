"""Parity: can the loop rebuild the brief's facts without n8n, and where does the brief go wrong?

`offline_checks` works from the run fixtures alone (no network, no keys):
  * L2 recomputation checks - ported node logic must reproduce the run's outputs exactly;
  * L1/L3 findings - inconsistencies between the data, the reader profile and the printed page.

`live_checks` re-fetches the same session from FMP, FRED and SEC EDGAR through
the snapshot store and compares against the run's reference values.

Every Check carries `query`: the exact call (or data path) that reproduces it.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from shadowdesk.compute import brief_facts as bf
from shadowdesk.ingest.fred import MAX_AGE_DAYS, SERIES, SERIES_FREQ
from shadowdesk.ingest.reader import ReaderProfile

FUNDS = {"VOO", "VXF", "SPYM", "SCHD", "QQQ", "SPY", "IVV", "VTI"}


@dataclass
class Check:
    check_id: str
    layer: str          # L0..L3
    title: str
    status: str         # pass | finding | fail | skipped
    severity: str       # info | low | medium | high
    query: str
    expected: Any = None
    actual: Any = None
    detail: str = ""


@dataclass
class RunFixtures:
    market: dict
    disclosures: dict
    raw: dict
    brief: dict
    root: Path

    @classmethod
    def load(cls, root: str | Path) -> "RunFixtures":
        r = Path(root)
        j = lambda n: json.loads((r / n).read_text(encoding="utf-8"))
        return cls(j("reference_market.json"), j("reference_disclosures.json"), j("raw_inputs.json"),
                   j("brief_claims.json"), r)

    @property
    def run_time(self) -> datetime:
        return datetime.fromtimestamp(self.raw["processing_node_started_ms"] / 1000, timezone.utc)

    def grade_rows(self) -> list[dict]:
        cols = ["symbol", "date", "gradingCompany", "previousGrade", "newGrade", "action"]
        return [dict(zip(cols, r)) for r in self.raw["grades_since_2026_10_10"]]


def _eq(check_id, title, expected, actual, query, layer="L2") -> Check:
    ok = expected == actual
    return Check(check_id, layer, title, "pass" if ok else "fail", "info" if ok else "high", query, expected, actual,
                 "" if ok else "ported logic does not reproduce the n8n output")


# --------------------------------------------------------------------------- offline

def offline_checks(fx: RunFixtures, reader: ReaderProfile) -> list[Check]:
    m, d, b = fx.market, fx.disclosures, fx.brief
    out: list[Check] = []
    F = f"fixtures/{fx.root.name}"

    # ---- L2: ported logic reproduces the run --------------------------------
    br = bf.breadth(m["price"]["quotes"])
    out.append(_eq("P-BREADTH", "Breadth of the reader's companies",
                   {k: m["price"]["breadth"][k] for k in ("up", "down", "flat", "counted")},
                   {k: br[k] for k in ("up", "down", "flat", "counted")},
                   f"brief_facts.breadth({F}/reference_market.json:price.quotes)"))
    g, l = bf.top_movers(m["price"]["quotes"])
    out.append(_eq("P-MOVERS", "Biggest riser and faller",
                   [m["price"]["topGainer"]["symbol"], m["price"]["topLoser"]["symbol"]], [g["symbol"], l["symbol"]],
                   f"brief_facts.top_movers({F}/reference_market.json:price.quotes)"))
    ss = bf.sector_summary(m["sectors"])
    out.append(_eq("P-SECTORS", "Best and worst SPDR sector of the session",
                   m["sectorSummary"], {k: ss[k] for k in ("best", "worst", "up", "down")},
                   f"brief_facts.sector_summary({F}/reference_market.json:sectors)"))
    closes = [c for _, c in fx.raw["gspc_newest_first"]][::-1]
    s = bf.sro(closes)
    out.append(_eq("P-SRO", "S&P 500 regime signal (EMA10 vs EMA35)", d["sro"], {"sro": s["sro"], "sroRegime": s["sroRegime"]},
                   f"brief_facts.sro({F}/raw_inputs.json:gspc_newest_first reversed)"))
    rsi = bf.rsi_summary(d["rsi"])
    out.append(_eq("P-RSI", "Average RSI-14 across holdings", d["rsiAvg"], rsi["avg"],
                   f"brief_facts.rsi_summary({F}/reference_disclosures.json:rsi)"))
    faithful = bf.rating_changes(fx.grade_rows(), fx.run_time)
    key = lambda rs: [(r["symbol"], r["date"], r["firm"], r["action"]) for r in rs]
    out.append(_eq("P-RATINGS", "Analyst rating actions shown (port of the Processing node)",
                   key(d["ratings"]), key(faithful),
                   f"brief_facts.rating_changes({F}/raw_inputs.json:grades_since_2026_10_10, now={fx.run_time.isoformat()})"))

    # ---- Findings -------------------------------------------------------------
    fixed = bf.rating_changes_fixed(fx.grade_rows(), fx.run_time)
    dropped = [r for r in fixed if r["action"] != "reiterated" and key([r])[0] not in key(faithful)]
    out.append(Check(
        "F-RATINGS-NEWS-DROPPED", "L3", "Rating upgrades/downgrades cut in favour of reiterations",
        "finding" if dropped else "pass", "high" if dropped else "info",
        f"brief_facts.rating_changes_fixed({F}/raw_inputs.json:grades_since_2026_10_10, now={fx.run_time.isoformat()})",
        expected="every upgrade/downgrade in the 7-day window is shown", actual=[r["fact"] for r in dropped],
        detail=("The Processing node ranks news above reiterations only within one company, then sorts all "
                "companies by date and keeps 6, so an older downgrade loses to newer routine reiterations.")))

    issues = reader.ticker_issues()
    failed = m["price"].get("quotesFailed", [])
    out.append(Check(
        "F-TICKER", "L1", "Reader tickers that no data source recognises",
        "finding" if (issues or failed) else "pass", "medium" if (issues or failed) else "info",
        f"ReaderProfile.ticker_issues(config/readers/{reader.reader}.yaml) + {F}/reference_market.json:price.quotesFailed",
        expected=[], actual={"profile": issues, "quote_failures": failed},
        detail="The name is silently missing from every section of the brief (quotes, news, ratings, 13F)."))

    tile_vix, text_vix = b["tiles"]["vix"]["value"], next(t["value"] for t in b["text_numbers"] if t["series"] == "vix")
    out.append(Check(
        "F-VIX-TWO-VALUES", "L1", "Two different VIX values on one page",
        "finding" if abs(tile_vix - text_vix) > 0.01 else "pass", "medium",
        f"{F}/brief_claims.json:tiles.vix vs text_numbers[vix]  (tile=FMP ^VIX quote, text=FRED VIXCLS {m['fred']['rateDate']})",
        expected="one value per series per page", actual={"tile": tile_vix, "text": text_vix}))

    published = date.fromisoformat(b["published_for"][:10])
    rate_date = date.fromisoformat(m["fred"]["rateDate"])
    labeled_today = [k for k, v in b["tiles"].items() if isinstance(v, dict) and v.get("label") == "today"]
    lag = (published - rate_date).days
    out.append(Check(
        "F-STALE-AS-TODAY", "L1", "Rate tiles labelled 'today' carry an older reading",
        "finding" if labeled_today and lag > 1 else "pass", "medium",
        f"{F}/brief_claims.json:tiles[*].label == 'today' vs reference_market.json:fred.rateDate",
        expected=f"label shows the observation date ({rate_date})", actual={"tiles": labeled_today, "observation": str(rate_date), "published": str(published), "days_old": lag}))

    gdp = next((t for t in b["text_numbers"] if t["series"] == "gdpNow"), None)
    if gdp:
        age = (published - date.fromisoformat(gdp["as_of"])).days
        limit = MAX_AGE_DAYS[SERIES_FREQ.get(SERIES["gdpNow"], "daily")]
        out.append(Check(
            "F-STALE-GDPNOW", "L1", "GDPNow reading older than its freshness limit is still printed",
            "finding" if age > limit else "pass", "low",
            f"{F}/brief_claims.json:text_numbers[gdpNow].as_of; limit MAX_AGE_DAYS['{SERIES_FREQ.get(SERIES['gdpNow'])}']={limit}",
            expected=f"<= {limit} days old or omitted", actual=f"{age} days old",
            detail="The page discloses the age, but a 116-day-old nowcast is not a current GDP read; suppress or refresh."))

    pct_for_yield = [t["id"] for t in b["text_numbers"] if t.get("unit_written") == "%" and t["series"].startswith("yield")]
    out.append(Check(
        "F-UNITS", "L1", "Yield changes written as percent instead of percentage points",
        "finding" if pct_for_yield else "pass", "low",
        f"{F}/brief_claims.json:text_numbers[unit_written=='%' and series startswith 'yield']",
        expected="-0.17 percentage points (17 bp)", actual=pct_for_yield,
        detail="'fell 0.17%' reads as a 0.17% relative move (about 0.8 bp)."))

    lo, hi = d["earningsWindow"]
    calendar = {e["symbol"] for e in d["earnings"]}
    missed = [e for e in b["earnings_mentions"] if lo <= e["date"] <= hi and e["symbol"] in reader.all_tickers and e["symbol"] not in calendar]
    out.append(Check(
        "F-EARNINGS-COVERAGE", "L3", "Reader companies reporting this week missing from the earnings calendar",
        "finding" if missed else "pass", "high" if missed else "info",
        f"{F}/brief_claims.json:earnings_mentions in window {lo}..{hi} minus reference_disclosures.json:earnings",
        expected=sorted({e['symbol'] for e in b['earnings_mentions'] if lo <= e['date'] <= hi}),
        actual={"calendar": sorted(calendar), "missing": [f"{e['symbol']} {e['date']}" for e in missed]},
        detail=("The brief's own news text dates these reports inside the window, but Week Ahead lists only the "
                "calendar's names. Both cannot be right: either the FMP calendar missed them or the text is wrong. "
                "The live check (EDGAR 8-K item 2.02 after the date) settles it.")))

    missing_feeds = d["newsMeta"].get("feedsMissing", [])
    out.append(Check(
        "F-FEED-MISSING", "L0", "News feeds that fetched but never reached the aggregator",
        "finding" if missing_feeds else "pass", "medium",
        f"{F}/reference_disclosures.json:newsMeta.feedsMissing",
        expected=[], actual=missing_feeds,
        detail="RSS Aggregate runs once per inbound wire; it emitted before the Google News node finished."))

    funds_as_fin = sorted(t for t, s in d["sectorMapping"].items() if t in FUNDS and s == "Financial Services")
    out.append(Check(
        "F-FUND-SECTOR", "L1", "Index funds classified as the Financial Services sector",
        "finding" if funds_as_fin else "pass", "low",
        f"{F}/reference_disclosures.json:sectorMapping[fund tickers]",
        expected="funds looked through to their holdings (or excluded)", actual=funds_as_fin,
        detail="FMP's profile sector for an ETF is the issuer's industry; any sector exposure built on it is wrong."))

    exposure = sorted({bf.SECTOR_ETFS[bf.PROFILE_SECTOR_TO_ETF[s]] for t, s in d["sectorMapping"].items()
                       if t in reader.holdings and t not in FUNDS and s in bf.PROFILE_SECTOR_TO_ETF})
    shown = {("Health Care" if x == "Healthcare" else x) for x in b["sector_exposure_shown"]}
    omitted = [s for s in exposure if s not in shown]
    out.append(Check(
        "F-SECTOR-EXPOSURE", "L3", "Sectors the reader holds that the brief left out",
        "finding" if omitted else "pass", "low",
        f"holdings minus funds -> {F}/reference_disclosures.json:sectorMapping -> SPDR sector; vs brief_claims.json:sector_exposure_shown",
        expected=exposure, actual={"shown": sorted(shown), "omitted": omitted,
                                    "omitted_moves": {s: next(v["changePercent"] for v in m["sectors"].values() if v["sector"] == s) for s in omitted}}))

    # Sensitivity scenarios vs the session's moves (the first Shadow Brief "missed" item)
    crude = m["price"]["commodities"]["crudePct"]
    energy = m["sectors"]["XLE"]["changePercent"]
    hits = []
    for sc in reader.top_sensitivities(7):
        if "oil" in sc.scenario.lower() and crude is not None and abs(crude) >= 2:
            hits.append({"scenario": sc.scenario, "concern": sc.concern,
                         "evidence": {"crudePct": crude, "XLE": energy, "XLE_rank": "best sector" if m["sectorSummary"]["best"] == "XLE" else ""}})
    out.append(Check(
        "F-SENSITIVITY-UNLINKED", "L3", "A reader's top-rated risk moved, and the brief did not connect them",
        "finding" if hits else "pass", "medium" if hits else "info",
        f"ReaderProfile.top_sensitivities(7) x {F}/reference_market.json:price.commodities.crudePct, sectors.XLE",
        expected="brief references the reader's stated scenario when its driver moves >= 2%",
        actual=hits,
        detail="The workflow's Aggregate Sheets node drops the Sensitivity tab, so the model never sees it."))
    return out


# --------------------------------------------------------------------------- live

def _close_and_change(eod_rows: list[dict], session: str) -> tuple[float | None, float | None]:
    rows = sorted((r for r in eod_rows if r.get("date", "")[:10] <= session), key=lambda r: r["date"])
    if len(rows) < 2 or rows[-1]["date"][:10] != session:
        return None, None
    c, p = rows[-1]["close"], rows[-2]["close"]
    return c, (c / p - 1) * 100


def live_checks(fx: RunFixtures, reader: ReaderProfile, fmp, fred, sec, session: str,
                price_tol: float = 0.011, pct_tol: float = 0.02, rate_tol: float = 0.005) -> list[Check]:
    """Re-fetch the session through the snapshot store and compare to the run.

    `session` is the trading day the brief describes (2026-10-23 for run 6361).
    """
    out: list[Check] = []
    start = (date.fromisoformat(session).replace(day=1)).isoformat()
    ref_q = {q["symbol"]: q for q in fx.market["price"]["quotes"] + fx.market["price"]["watchlistQuotes"]}
    for sym in reader.all_tickers:
        try:
            rows, prov = fmp.historical_eod(sym, start, session)
        except Exception as e:  # noqa: BLE001 - every failure becomes a reported check
            out.append(Check(f"L-EOD-{sym}", "L0", f"{sym} session close", "fail", "medium", f"fmp.historical_eod('{sym}', '{start}', '{session}')", detail=str(e)))
            continue
        close, chg = _close_and_change(rows if isinstance(rows, list) else [], session)
        q = f"fmp.historical_eod('{sym}', '{start}', '{session}')  [{prov.ref()}]"
        if sym not in ref_q:
            out.append(Check(f"L-EOD-{sym}", "L0", f"{sym} session close", "finding" if close is None else "pass",
                             "medium" if close is None else "info", q, None, close,
                             "not in the run's quotes" + ("; no EOD data either" if close is None else "")))
            continue
        r = ref_q[sym]
        ok = close is not None and abs(close - r["price"]) <= price_tol and abs(chg - r["changePct"]) <= pct_tol
        out.append(Check(f"L-EOD-{sym}", "L2", f"{sym} close and daily change", "pass" if ok else "fail",
                         "info" if ok else "high", q, {"close": r["price"], "changePct": r["changePct"]},
                         {"close": close, "changePct": None if chg is None else round(chg, 4)}))

    for sym, ref in fx.market["sectors"].items():
        try:
            rows, prov = fmp.historical_eod(sym, start, session)
            close, chg = _close_and_change(rows, session)
            ok = close is not None and abs(close - ref["price"]) <= price_tol and abs(chg - ref["changePercent"]) <= pct_tol
            out.append(Check(f"L-SECTOR-{sym}", "L2", f"{ref['sector']} ({sym}) close and change", "pass" if ok else "fail",
                             "info" if ok else "medium", f"fmp.historical_eod('{sym}', '{start}', '{session}')  [{prov.ref()}]",
                             {"close": ref["price"], "changePct": ref["changePercent"]}, {"close": close, "changePct": None if chg is None else round(chg, 4)}))
        except Exception as e:  # noqa: BLE001
            out.append(Check(f"L-SECTOR-{sym}", "L0", f"{sym} close", "fail", "medium", f"fmp.historical_eod('{sym}', ...)", detail=str(e)))

    fred_start = (date.fromisoformat(session).replace(year=date.fromisoformat(session).year - 1)).isoformat()
    for field_name, series_id in SERIES.items():
        ref_val = fx.market["fred"].get(field_name)
        if ref_val is None:
            continue
        q = f"fred.latest_with_change('{series_id}', '{fred_start}', '{session}')"
        try:
            reading = fred.latest_with_change(series_id, fred_start, session)
        except Exception as e:  # noqa: BLE001
            out.append(Check(f"L-FRED-{field_name}", "L0", f"FRED {series_id}", "fail", "medium", q, detail=str(e)))
            continue
        if reading is None:
            out.append(Check(f"L-FRED-{field_name}", "L0", f"FRED {series_id}", "fail", "medium", q, ref_val, None, "no observations"))
            continue
        ok = abs(reading.value - float(ref_val)) <= rate_tol
        out.append(Check(f"L-FRED-{field_name}", "L2", f"{field_name} ({series_id})", "pass" if ok else "fail",
                         "info" if ok else "medium", f"{q}  [{reading.prov.ref()}]", float(ref_val),
                         {"value": reading.value, "date": reading.date},
                         "" if ok else "differs from the run; check observation date and series revisions"))

    # ratings, recomputed from a fresh /grades pull at the run's original timestamp
    rows: list[dict] = []
    for sym in reader.all_tickers:
        try:
            data, _ = fmp.grades(sym)
            rows.extend(r for r in data if isinstance(r, dict))
        except Exception:  # noqa: BLE001
            pass
    recomputed = bf.rating_changes(rows, fx.run_time)
    key = lambda rs: [(r["symbol"], r["date"], r["firm"]) for r in rs]
    out.append(_eq("L-RATINGS", "Rating actions recomputed from a fresh /grades pull", key(fx.disclosures["ratings"]),
                   key(recomputed), f"brief_facts.rating_changes(fmp.grades(each ticker), now={fx.run_time.isoformat()})"))

    # SEC 8-K item codes straight from EDGAR for the 5 days before the run
    try:
        ciks, _ = sec.cik_map()
        lo = (date.fromisoformat(session).toordinal() - 4)
        lo_s = date.fromordinal(lo).isoformat()
        from shadowdesk.ingest.sec import filings_in_window
        found = []
        for sym in reader.all_tickers:
            cik = ciks.get(sym)
            if not cik or sym in FUNDS:
                continue
            subs, prov = sec.submissions(cik)
            found += [(f.symbol, f.form, f.filed, f.items) for f in filings_in_window(sym, cik, subs, prov, lo_s, fx.run_time.date().isoformat(), forms=("8-K",))]
        ref = [(f["symbol"], f["form"], f["filed"][:10], tuple(f["items"])) for f in fx.disclosures["secFilings"]]
        missing = [r for r in found if (r[0], r[1], r[2]) not in {(x[0], x[1], x[2]) for x in ref}]
        out.append(Check("L-SEC-8K", "L2", "8-K filings on the reader's companies (EDGAR direct)",
                         "pass" if not missing else "finding", "info" if not missing else "medium",
                         f"sec.submissions(cik) for each ticker; 8-K filed {lo_s}..{fx.run_time.date()}",
                         ref, found, "" if not missing else "EDGAR shows 8-Ks the brief did not list"))
    except Exception as e:  # noqa: BLE001
        out.append(Check("L-SEC-8K", "L0", "8-K filings (EDGAR)", "fail", "medium", "sec.cik_map(); sec.submissions(cik)", detail=str(e)))
    return out
