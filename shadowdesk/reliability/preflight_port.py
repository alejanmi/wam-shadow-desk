"""Python port of the commented-out "NODE B / PRE-FLIGHT PAYLOAD CHECK" in the
Validator node's jsCode. It has never been wired into the live workflow —
the generation call runs unconditionally on whatever payload "Analyst desk
rollup" -> "Edit Fields" produced. This port lets the detection loop reason
about whether pre-flight *would have* caught a given failure retroactively,
and lets wam/interventions.py's enable_preflight_check be verified offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def _length(v) -> int:
    if isinstance(v, list):
        return len(v)
    if isinstance(v, dict):
        return len(v)
    if v:
        return len(str(v))
    return 0


@dataclass
class PreflightResult:
    ok: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    payload_chars: int = 0


def run_preflight(payload: dict) -> PreflightResult:
    p = payload
    failures: list[str] = []
    warnings: list[str] = []

    if not p.get("Ticker") or len(str(p.get("Ticker")).strip()) < 2:
        failures.append("no holdings (Ticker empty)")
    if not p.get("advisorName"):
        failures.append("no advisorName")
    if not p.get("Mode"):
        warnings.append("no Mode (hybrid assumed by prompt)")
    if not p.get("bookMove") and not p.get("BookMove"):
        failures.append("no BOOK MOVE block")
    if _length(p.get("newsContext")) < 20:
        failures.append(f"newsContext has {_length(p.get('newsContext'))} items (expected 60 to 100)")
    if _length(p.get("macroContext")) < 10:
        failures.append(f"macroContext has {_length(p.get('macroContext'))} series")
    if _length(p.get("holdingsPerf")) < 3:
        failures.append(f"holdingsPerf has {_length(p.get('holdingsPerf'))} rows")
    if not p.get("sectorExposure"):
        failures.append("no sectorExposure")
    if not p.get("fixedIncome") and not p.get("fi"):
        warnings.append("no fixed income block")
    if not p.get("earningsThisWeek"):
        warnings.append("no earningsThisWeek")
    if not p.get("economicCalendar"):
        warnings.append("no economicCalendar")
    if p.get("quoteFailures") and _length(p.get("quoteFailures")) > 3:
        warnings.append(f"quote failures: {_length(p.get('quoteFailures'))}")
    smart_money = p.get("smartMoney")
    if not smart_money or (isinstance(smart_money, dict) and smart_money.get("hasData") is False):
        warnings.append("smartMoney empty (Hedge Fund Flow will be omitted)")

    import json as _json

    payload_chars = len(_json.dumps(p))
    if payload_chars < 150_000:
        failures.append(f"payload only {payload_chars} chars (expected ~400k)")

    return PreflightResult(ok=len(failures) == 0, failures=failures, warnings=warnings, payload_chars=payload_chars)
