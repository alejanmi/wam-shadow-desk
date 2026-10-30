"""Python ports of the Retail Agent V1 Code nodes that turn raw data into brief facts.

Each function is a line-by-line port of the named n8n node, so that parity can
prove the loop computes the same facts without n8n. Where the original has a
defect, the faithful port keeps it, and a separate `*_fixed` function holds
the corrected logic. Parity reports the difference as a finding instead of
silently "fixing" the brief.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable


# ---- Price Data node -------------------------------------------------------

def change_pct(q: dict) -> float | None:
    pct = q.get("changesPercentage", q.get("changePct"))
    if pct is None and q.get("change") is not None and q.get("previousClose"):
        pct = q["change"] / q["previousClose"] * 100
    return pct


def breadth(quotes: Iterable[dict]) -> dict:
    up = down = flat = 0
    total = 0
    for q in quotes:
        total += 1
        v = change_pct(q)
        if v is None or not math.isfinite(float(v)):
            continue
        v = float(v)
        if v > 0:
            up += 1
        elif v < 0:
            down += 1
        else:
            flat += 1
    counted = up + down + flat
    return {"up": up, "down": down, "flat": flat, "counted": counted, "total": total,
            "summary": f"Of your {counted} companies, {up} rose and {down} fell today." if counted else ""}


def top_movers(quotes: Iterable[dict]) -> tuple[dict | None, dict | None]:
    moved = [{"symbol": q["symbol"], "changePct": float(change_pct(q)), "price": q.get("price")}
             for q in quotes if change_pct(q) is not None and math.isfinite(float(change_pct(q)))]
    moved.sort(key=lambda m: -m["changePct"])
    return (moved[0] if moved else None), (moved[-1] if len(moved) > 1 else None)


# ---- Process Sectors node --------------------------------------------------

SECTOR_ETFS = {
    "XLK": "Technology", "XLF": "Financials", "XLV": "Health Care", "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples", "XLE": "Energy", "XLI": "Industrials", "XLU": "Utilities",
    "XLB": "Materials", "XLRE": "Real Estate", "XLC": "Communication Services",
}

# FMP profile sector names -> SPDR sector ETF (for "sectors you have exposure to")
PROFILE_SECTOR_TO_ETF = {
    "Technology": "XLK", "Financial Services": "XLF", "Healthcare": "XLV", "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP", "Energy": "XLE", "Industrials": "XLI", "Utilities": "XLU",
    "Basic Materials": "XLB", "Real Estate": "XLRE", "Communication Services": "XLC",
}


def sector_summary(rows: dict[str, dict]) -> dict:
    perf = {s: r.get("changePercent") for s, r in rows.items() if s in SECTOR_ETFS}
    ordered = sorted(perf, key=lambda s: -(perf[s] if perf[s] is not None else -math.inf))
    vals = [v for v in perf.values() if v is not None]
    return {"best": ordered[0] if ordered else None, "worst": ordered[-1] if ordered else None,
            "up": sum(v > 0 for v in vals), "down": sum(v < 0 for v in vals), "flat": sum(v == 0 for v in vals)}


# ---- SRO regime node (Code in JavaScript2) ---------------------------------

def _ema(data: list[float], period: int) -> float:
    k = 2 / (period + 1)
    e = data[0]
    for x in data[1:]:
        e = x * k + e * (1 - k)
    return e


def sro(closes_oldest_first: list[float]) -> dict:
    if len(closes_oldest_first) < 35:
        return {"sro": None, "sroRegime": "INSUFFICIENT DATA"}
    e10, e35 = _ema(closes_oldest_first, 10), _ema(closes_oldest_first, 35)
    v = (e10 - e35) / e35 * 100
    if v >= 5: regime = "EXTREMELY OB"
    elif v >= 3: regime = "OVERBOUGHT"
    elif v >= 1: regime = "MILDLY OB"
    elif v > -1: regime = "NEUTRAL"
    elif v > -3: regime = "MILDLY OS"
    elif v > -5: regime = "OVERSOLD"
    else: regime = "EXTREMELY OS"
    return {"sro": round(v * 100) / 100, "sroRegime": regime, "raw": v}


# ---- RSI processor node ----------------------------------------------------

def rsi_summary(rows: Iterable[dict]) -> dict:
    valid = sorted(({"ticker": r["ticker"], "rsi": round(float(r["rsi"]), 1)} for r in rows if r.get("rsi") is not None),
                   key=lambda r: r["rsi"])
    if not valid:
        return {"avg": None}
    avg = round(sum(r["rsi"] for r in valid) / len(valid), 1)
    tag = lambda v: "OVERBOUGHT" if v >= 70 else "OVERSOLD" if v <= 30 else ""
    return {"avg": avg, "lowest3": valid[:3], "highest3": valid[-3:][::-1],
            "flags": {r["ticker"]: tag(r["rsi"]) for r in valid if tag(r["rsi"])}}


# ---- Processing node (analyst rating changes) ------------------------------

_NEWS = re.compile(r"upgraded|downgraded|started")


def _grade_fact(row: dict) -> dict:
    symbol = str(row["symbol"]).replace("-", "/", 1)
    action = str(row.get("action") or "reiterated").lower()
    firm = row.get("gradingCompany") or "A research firm"
    frm, to = row.get("previousGrade"), row.get("newGrade")
    date = str(row["date"])[:10]
    if "upgrade" in action:
        verb = "upgraded"
        fact = f"{firm} upgraded {symbol}" + (f" to {to}" if to else "") + (f" from {frm}" if frm and to and frm != to else "") + f" on {date}."
    elif "downgrade" in action:
        verb = "downgraded"
        fact = f"{firm} downgraded {symbol}" + (f" to {to}" if to else "") + (f" from {frm}" if frm and to and frm != to else "") + f" on {date}."
    elif "initiate" in action:
        verb = "started covering"
        fact = f"{firm} started covering {symbol}" + (f" with a {to} rating" if to else "") + f" on {date}."
    else:
        verb = "reiterated"
        fact = f"{firm} reiterated its {to or 'existing'} rating on {symbol} on {date}."
    return {"symbol": symbol, "date": date, "firm": firm, "action": verb, "fromGrade": frm, "toGrade": to, "fact": fact}


def _recent(rows: Iterable[dict], now: datetime, days: int = 7) -> list[dict]:
    cutoff = now - timedelta(days=days)
    out = []
    for row in rows:
        if not row.get("symbol") or (row.get("newGrade") is None and row.get("gradingCompany") is None) or not row.get("date"):
            continue
        d = datetime.fromisoformat(str(row["date"])[:10]).replace(tzinfo=timezone.utc)
        if d < cutoff:
            continue
        out.append(_grade_fact(row))
    return out


def rating_changes(rows: Iterable[dict], now: datetime, per_company: int = 2, total: int = 6) -> list[dict]:
    """Faithful port: news-first only WITHIN a company, then a global date sort and cut."""
    by_ticker: dict[str, list[dict]] = {}
    for f in _recent(rows, now):
        by_ticker.setdefault(f["symbol"], []).append(f)
    picked: list[dict] = []
    for sym, items in by_ticker.items():
        items.sort(key=lambda r: r["date"], reverse=True)
        items.sort(key=lambda r: 0 if _NEWS.search(r["action"]) else 1)
        picked.extend(items[:per_company])
    picked.sort(key=lambda r: r["date"], reverse=True)
    return picked[:total]


def rating_changes_fixed(rows: Iterable[dict], now: datetime, per_company: int = 2, total: int = 6) -> list[dict]:
    """Corrected: upgrades, downgrades and initiations always outrank reiterations globally."""
    by_ticker: dict[str, list[dict]] = {}
    for f in _recent(rows, now):
        by_ticker.setdefault(f["symbol"], []).append(f)
    picked: list[dict] = []
    for items in by_ticker.values():
        items.sort(key=lambda r: r["date"], reverse=True)
        items.sort(key=lambda r: 0 if _NEWS.search(r["action"]) else 1)
        picked.extend(items[:per_company])
    picked.sort(key=lambda r: r["date"], reverse=True)
    picked.sort(key=lambda r: 0 if _NEWS.search(r["action"]) else 1)
    return picked[:total]


# ---- Insider Pol Code node (congressional trades) --------------------------

_HONORIFIC = re.compile(r"\b(Mr|Mrs|Ms|Dr|Hon|Rep|Sen|Jr|Sr|III|II)\b\.?", re.I)


def _clean_name(first: Any, last: Any) -> str:
    n = f"{first or ''} {last or ''}".strip()
    n = re.sub(r"\s+", " ", _HONORIFIC.sub(" ", n)).strip()
    return n or "Unknown"


def politician_trades(senate: list[dict], house: list[dict], tickers: Iterable[str],
                      per_company: int = 2, total: int = 5) -> list[dict]:
    mine = {t.upper().strip() for t in tickers}
    allrows = [dict(t, chamber="Senate") for t in senate] + [dict(t, chamber="House") for t in house]
    seen, rows = set(), []
    for t in allrows:
        sym = str(t.get("symbol") or "").upper().strip()
        if not sym or sym not in mine:
            continue
        typ = str(t.get("type") or "").lower()
        is_buy = "purchase" in typ or "buy" in typ
        name = _clean_name(t.get("firstName"), t.get("lastName"))
        tx, amount = t.get("transactionDate"), t.get("amount") or ""
        key = (sym, name.lower(), tx, amount, is_buy)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"symbol": sym, "person": name, "chamber": t["chamber"], "action": "bought" if is_buy else "sold",
                     "isBuy": is_buy, "amountRange": amount or "not disclosed", "transactionDate": tx,
                     "disclosureDate": t.get("disclosureDate"), "link": t.get("link", "")})
    pairs: dict[tuple, list[int]] = {}
    for r in rows:
        k = (r["symbol"], r["person"].lower(), r["transactionDate"], r["amountRange"])
        pairs.setdefault(k, [0, 0])[0 if r["isBuy"] else 1] += 1
    cleaned = [r for r in rows if not all(pairs[(r["symbol"], r["person"].lower(), r["transactionDate"], r["amountRange"])])]
    cleaned.sort(key=lambda r: str(r["disclosureDate"] or ""), reverse=True)
    per: dict[str, int] = {}
    out = []
    for r in cleaned:
        per[r["symbol"]] = per.get(r["symbol"], 0) + 1
        if per[r["symbol"]] > per_company:
            continue
        out.append(r)
        if len(out) >= total:
            break
    return out


# ---- Earnings Calendar node -------------------------------------------------

def earnings_window(now_utc: datetime, days: int = 7) -> tuple[str, str]:
    """Window in Pacific time, computed correctly (the n8n node re-serializes a
    PT wall-clock time with toISOString, which can shift the date)."""
    from zoneinfo import ZoneInfo
    pt = now_utc.astimezone(ZoneInfo("America/Los_Angeles")).date()
    return pt.isoformat(), (pt + timedelta(days=days)).isoformat()


def earnings_this_week(calendar: list[dict], tickers: Iterable[str]) -> list[dict]:
    mine = {t.upper().strip() for t in tickers}
    out = []
    for e in calendar:
        sym = str(e.get("symbol") or "").upper().strip()
        if sym not in mine:
            continue
        raw = str(e.get("time") or "").lower().strip()
        timing = "amc" if raw == "amc" or "after" in raw else "bmo" if raw == "bmo" or "before" in raw else "TBD"
        out.append({"symbol": sym, "date": e.get("date"), "timing": timing,
                    "epsEstimate": e.get("epsEstimated"), "revenueEstimate": e.get("revenueEstimated")})
    out.sort(key=lambda m: m["date"] or "")
    return out
