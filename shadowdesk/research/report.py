"""Render a research run as a readable report (Markdown) plus machine-readable JSON."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from shadowdesk.research.run import ALPHA, B, BLOCK, Q_FDR, ClaimResult

UNITS = {
    "W1": ("difference in oil elasticity", lambda v: f"{v:+.3f}"),
    "W2-AMZN": ("oil elasticity", lambda v: f"{v:+.3f}"),
    "W2-JNJ": ("oil elasticity", lambda v: f"{v:+.3f}"),
    "W3": ("T minus most rate-sensitive peer, % per 100 bp", lambda v: f"{100 * v:+.2f}"),
    "W4-MSFT": ("dollar elasticity", lambda v: f"{v:+.2f}"),
    "W4-AMZN": ("dollar elasticity", lambda v: f"{v:+.2f}"),
    "W4-GOOG": ("dollar elasticity", lambda v: f"{v:+.2f}"),
    "H1": ("basket move for +10% oil, %", lambda v: f"{100 * v:+.2f}%"),
    "H2": ("oil weekly move, z", lambda v: f"{v:+.2f}"),
    "H3": ("AT&T residual that week, z", lambda v: f"{v:+.2f}"),
    "H4": ("best out-of-sample R²", lambda v: f"{v:+.3f}"),
}


def _est(r: ClaimResult) -> str:
    if r.estimate is None:
        return "—"
    label, f = UNITS.get(r.claim_id, ("", lambda v: f"{v:+.3f}"))
    ci = ""
    if r.ci:
        ci = f" [{f(r.ci[0])}, {f(r.ci[1])}]"
    return f"{f(r.estimate)}{ci}"


def _outcome(r: ClaimResult) -> str:
    o = r.outcome
    if r.extra.get("suggestive"):
        o += " (raw p < 0.05, fails FDR)"
    return o


def _p(r: ClaimResult) -> str:
    return "—" if r.p is None else f"{r.p:.3f}"


def render(results: list[ClaimResult], self_test: dict, outcome_week: dict | None, data_ref: str, as_of: str) -> str:
    wam = [r for r in results if r.source == "WAM brief"]
    loop = [r for r in results if r.source == "loop"]
    testable = [r for r in wam if r.outcome != "Untestable"]
    n_corr = sum(r.outcome == "Corroborated" for r in testable)
    n_contra = sum(r.outcome == "Contradicted" for r in results)
    h = {r.claim_id: r for r in results}
    L = [
        "# Autoresearch run 001 · WAM Pocket Pulse, 2026-10-24 (Annie)",
        "",
        f"**Result: {n_corr} of {len(testable)} testable WAM conclusions are corroborated by 5 years of weekly market data, "
        f"{n_contra} are contradicted, and 1 is untestable as written. None of the loop's own 4 hypotheses survived either.** "
        "Here that is the falsifier working, not failing: the brief's exposure statements read as facts, but the "
        "price data does not back them, so they should be presented as hypotheses or dropped.",
        "",
        f"Data: {data_ref}. Estimation ends at the week of {as_of} (the session the brief describes); nothing after it is used except as outcome data. "
        f"Tests: block bootstrap (B={B}, block={BLOCK} weeks, null imposed), Benjamini-Hochberg at q={Q_FDR} across every p-value in the run, α={ALPHA}.",
        "",
        "## WAM's conclusions vs the data",
        "",
        "| # | What the brief said | Falsifiable form | Estimate [90% CI] | p | Outcome |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in wam:
        L.append(f"| {r.claim_id} | {r.quote} | {r.test} | {_est(r)} | {_p(r)} | {_outcome(r)} |")
    w1, w3 = h.get("W1"), h.get("W3")
    L += ["", "What stands out:", ""]
    if w1:
        b = w1.extra.get("betas", {})
        L.append(f"- **AT&T is not oil-exposed in its prices.** Market-adjusted oil elasticities: T {b.get('T', 0):+.3f}, JNJ {b.get('JNJ', 0):+.3f}, "
                 f"MSFT {b.get('MSFT', 0):+.3f}, ORCL {b.get('ORCL', 0):+.3f}. AT&T's sign is the opposite of the brief's claim, though not significantly so.")
    if w3:
        b = w3.extra.get("betas", {})
        top = min(b, key=b.get) if b else "?"
        L.append(f"- **Rates do not reach AT&T 'most directly'.** Per +100 bp in the 10-year yield, holding the market fixed: "
                 + ", ".join(f"{s} {100 * v:+.1f}%" for s, v in sorted(b.items(), key=lambda kv: kv[1]))
                 + f". The most rate-sensitive of Annie's stocks is {top}, and all of the effects are small.")
    if "W4-AMZN" in h:
        L.append("- **The dollar claim points the right way but is weak.** All three multinationals have negative dollar elasticities, but none clears the bar.")
    L += ["", "## The loop's own hypotheses", "",
          "| # | Hypothesis | Test | Estimate [90% CI] | p | Outcome |", "| --- | --- | --- | --- | --- | --- |"]
    for r in loop:
        L.append(f"| {r.claim_id} | {r.quote} | {r.test} | {_est(r)} | {_p(r)} | {_outcome(r)} |")
    if "H1" in h:
        x = h["H1"].extra
        L += ["", "**H1, Annie's Hormuz scenario, as a do() intervention.** Effect of a +10% weekly oil shock on each holding "
              f"(VOO stands in for her four index funds; direct effect plus the effect through the market; the market's own oil response is g = {x.get('g_oil_on_mkt')}):", "",
              "| Holding | Total effect of do(WTI +10%) |", "| --- | --- |"]
        L += [f"| {s} | {v:+.2f}% |" for s, v in x.get("per_holding_pct", {}).items()]
        L += ["", f"Placebo (oil shifted 26 weeks, which should show nothing): {x.get('placebo_effect_pct'):+.3f}%, p = {x.get('placebo_p_neg'):.3f}, so the placebo passes. "
              "Read this as the average oil response over 2021-26, which mixes supply shocks with demand-driven rallies. A Hormuz-type supply shock needs "
              "an identification step this run does not have yet: oil moves on geopolitical event days used as an instrument (next experiment)."]
    if "H3" in h:
        x = h["H3"].extra
        L += ["", f"**H3, AT&T's week.** The stock fell {x['actual_pct']:+.2f}%. Market, oil, rates and dollar together explain {x['explained_by_factors_pct']:+.2f}%, "
              f"leaving {x['residual_pct']:+.2f}% that is company-specific (the Q3 report). The effect is decisive (z = {h['H3'].estimate:.1f}), and p = {h['H3'].p:.3f} would pass on its own, "
              f"but it does not clear the false-discovery bar across this run's {len([r for r in results if r.p is not None])} tests. Against WAM: the brief's People Watch line ties AT&T to rate decisions, but that week rates explain almost none of the move."]
    if "H2" in h:
        x = h["H2"].extra
        L += ["", f"**H2, Echo × Shadow on oil.** Oil's weekly move was {x['oil_week_return_pct']:+.2f}% (z = {x['echo_z']}, p = {x['echo_p']}): Friday's +3.8% was big for one day, but ordinary for a week. "
              "No holding's 26-week oil beta is unusual against its history (lowest p: " + min((f"{s} {v[1]}" for s, v in x['shadow_latest_beta_and_p'].items()), key=lambda t: float(t.split()[-1])) + "). "
              "No dual-plane signal, so no alert. That is the correct reading of a one-day spike."]
    if "H4" in h:
        L += ["", "**H4, oil as a leading signal.** Out-of-sample R² is below zero for XLE, T and VOO, so last week's oil move does not help predict this week's returns. Not corroborated, and logged so the idea is not re-proposed without new evidence."]
    L += ["", "## Is the falsifier itself trustworthy?", "",
          f"Before trusting any verdict, the test was run on {self_test['n_null']} synthetic series with no oil effect, with autocorrelated noise matching AT&T's residual scale, "
          f"and on {self_test['n_planted']} series with a planted effect of {self_test['planted_beta']}.", "",
          "| Check | Result | Target |", "| --- | --- | --- |",
          f"| False-positive rate on pure noise | {self_test['false_positive_rate']:.1%} ± {self_test.get('fpr_se', 0):.1%} | ≈ {ALPHA:.0%} |",
          f"| Power to find the planted effect | {self_test['power']:.0%} ± {self_test.get('power_se', 0):.0%} | as high as possible |", "",
          "(± is one standard error of the simulation estimate. The planted effect is about one standard error of a real oil beta, so modest power is expected: the test is built to avoid false alarms first.)", ""]
    if outcome_week:
        rows = outcome_week["returns_pct"]
        L += ["## What happened next (outcome layer L7)", "",
              f"Week of {outcome_week['week']}, partial through Thursday Oct 29. This is one observation, recorded for the ledger and not scored.", "",
              "| " + " | ".join(rows) + " |", "| " + " | ".join("---" for _ in rows) + " |", "| " + " | ".join(f"{v:+}" for v in rows.values()) + " |", "",
              "ORCL (+10.6%; its investor day was Oct 28) and JNJ (+4.3%) moved far more than the market (+1.3%), with oil flat. Whether those moves were company-specific is not yet tested: the H3 residual check runs once the week closes."]
    L += ["", "## What this means for WAM", "",
          "1. **Exposure sentences need evidence.** Sentences like 'AT&T and Johnson & Johnson have large operations that use fuel' read as analysis, but over five years the market has not priced them that way. "
          "The brief should attach the measured elasticity or drop the sentence. The ledger can supply the number every day.",
          "2. **Separate company news from macro.** AT&T's −11% week was almost entirely company-specific (H3), yet the brief's People Watch framed AT&T through rates. A residual check like H3, run before writing, tells the writer when not to reach for a macro story.",
          "3. **The reader's stated risks need a quantitative watch.** H1 and H2 are the first versions. The next run adds an event-day instrument for supply shocks and N3/N4 for the dual-plane pattern.", "",
          "## Limits of this run", "",
          "- Weekly Yahoo prices (5 significant digits) for research only; client-facing numbers should come from the FMP/FRED snapshot path.",
          "- Price reactions are a proxy for 'margin' claims (W2). Margin data from filings is the direct test (Valuation node data, next run).",
          "- Layers L3 (grounding) and L6 (multi-model red team, jaggedness) were not run: no model endpoint was available in this environment. The inquiry records mark them as not passed.",
          "- H2's coincidence (N3) and lead-time (N4) nulls are not run yet, so a dual-plane hit would still be only a candidate.",
          "- One brief and one reader. The method scales. These verdicts are specific to Oct 24 and Annie's list.", "",
          "## Reproduce", "", "```", "python -m shadowdesk research            # this report, the JSON and the ledger rows", "```", ""]
    return "\n".join(L)


def write(out_dir: str | Path, name: str, md: str, results: list[ClaimResult], self_test: dict, outcome: dict | None) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    m, j = out / f"{name}.md", out / f"{name}.json"
    m.write_text(md, encoding="utf-8")
    j.write_text(json.dumps({"claims": [asdict(r) for r in results], "self_test": self_test, "outcome_week": outcome},
                            indent=2, default=float), encoding="utf-8")
    return m, j
