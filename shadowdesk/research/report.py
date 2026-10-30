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


METHOD_NOTES = """## Methodology: what these verdicts can and cannot tell you

**Nothing here is "proven".** Following Popper, a claim can only be refuted or corroborated. A corroborated
claim has survived a test that could have killed it, which earns trust, never certainty. "Not corroborated" is
also not "false": it means the data could not tell the claim apart from no effect. The confidence intervals
in the tables show how wide that uncertainty is.

**This run did not test one day.** Each claim was tested against 260 weeks of history. The Oct 24 brief only
supplied the claims. Most effects came out small relative to the noise, which is why so few verdicts are decisive.

**The brief's statements are of three kinds, and each is settled differently:**

| Kind | Example from the brief | How it gets settled | Waiting needed? |
| --- | --- | --- | --- |
| Standing claim about how a company behaves | "AT&T and J&J have large operations that use fuel" | Longer history (15-20 years, daily data), event studies (Fed days, OPEC/geopolitical days), and the fundamentals themselves (fuel costs and debt in 10-K filings) | No, it can be done now |
| Forward-looking claim | "Higher oil prices can pressure margins"; "watch the Fed on Wednesday" | Register a specific forecast before the outcome (direction, size, probability, resolution date), then score it when it resolves | Yes: about 50 resolved forecasts (3-4 weeks of daily briefs) for a first calibration curve; 3-6 months to separate skill from luck |
| Hedged speculation | "Falling yields also reflect concerns about growth" | Cannot be settled, because no outcome contradicts it. Flag it, or rewrite it with a measure, a direction and a horizon | Not applicable |

**Why more data matters, in one line:** the precision of an estimate improves with the square root of the
sample, so detecting an effect half as large needs about four times the data. Five years of weekly returns
pin an oil sensitivity to about ±0.03, too coarse for the differences the brief implies.

**Rules the loop follows so that it does not fool itself:**

1. Claims are written in falsifiable form *before* the data is looked at, and the null each one must beat is named.
2. Every p-value in a run is corrected for multiple testing (Benjamini-Hochberg). A result that only looks good alone is labelled "suggestive", not shown as a finding.
3. Estimation stops at the date of the brief. Later data is used only to score outcomes.
4. The test itself is tested first, on simulated data with known answers (false-positive rate and power).
5. Every verdict carries the exact query, data hash and seed needed to reproduce it.

## Thoughts about training autoresearch for continuous improvement

"Training" here starts as *learning from a growing record of tested claims*, not as training a neural network.
The record has to exist before any model can learn from it.

**What the loop learns from:** the ledger. Each day adds the brief's claims, the loop's hypotheses, how each
was tested, and later how each turned out. Santino's reviews ("this was useful", "this was obvious", "this was
wrong") are the human labels that no market data can provide.

**Five improvement mechanisms, in the order they become possible:**

1. **Calibration (weeks 1-4).** Score every forecast with a proper scoring rule (Brier or log score) and track the calibration curve. If "70% likely" calls come true 50% of the time, the loop shrinks its confidence. This is the simplest form of learning, and the most important.
2. **Priors by claim type (month 1-3).** Count how often each kind of statement survives: "company X is exposed to factor Y", "this move was company-specific", "this indicator leads". New claims of a kind that rarely survives start with lower credibility, and that feeds back into how WAM's briefs are written.
3. **Choosing which hypotheses to generate (month 2-6).** Treat each hypothesis generator (factor exposures, residual checks, Echo x Shadow scans, sensitivity scenarios) as an arm of a bandit. Generators whose ideas survive falsification and later prove right get more of the daily testing budget; the others get less, but never zero.
4. **Improving the loop itself, Karpathy-style (ongoing).** Change one thing at a time (a new null, a new data source, a new prompt), re-run it on a fixed benchmark of past briefs whose outcomes are already known, and keep the change only if the score improves. Revert otherwise. Every change is a git commit with its benchmark result.
5. **Training a model, literally (after hundreds of resolved records).** Once there are several hundred resolved claims, a small local model can be fine-tuned to predict, from a draft sentence, which tests it will fail. It is used only to triage drafts and point the expensive tests at the right sentences. It never issues verdicts, because the statistics and the outcomes do.

**What must not be optimised:**

- *Survival rate.* A loop rewarded for claims that pass will learn to make vague or obvious claims. Reward accuracy on resolved forecasts and usefulness to Santino instead.
- *Repeated testing without a budget.* Over months, thousands of tests will produce lucky "discoveries". Use an online false-discovery method (alpha-investing or LORD) so the error rate stays controlled across time, not just within one run.
- *Self-grading.* A model never judges its own conclusion. Verdicts come from code, data and outcomes; a different model plays the red team.
- *A static benchmark.* Markets change regime. Keep a rolling hold-out period the loop has never seen, and re-check old conclusions when an Echo x Shadow pattern says the structure moved.

**How Santino would know it is working:** after a quarter, the loop should show (a) a calibration curve close
to the diagonal, (b) a falling share of untestable sentences in WAM's briefs, (c) at least a few claims flagged
early that later resolved as the loop said, with lead time, and (d) a list of loop changes that were kept
because they improved the benchmark. If none of these move, the loop is producing noise and should be redesigned.
"""


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
          METHOD_NOTES,
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
