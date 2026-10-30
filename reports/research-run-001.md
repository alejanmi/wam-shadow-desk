# Autoresearch run 001 · WAM Pocket Pulse, 2026-10-24 (Annie)

**Result: 0 of 7 testable WAM conclusions are corroborated by 5 years of weekly market data, 0 are contradicted, and 1 is untestable as written. None of the loop's own 4 hypotheses survived either.** Here that is the falsifier working, not failing: the brief's exposure statements read as facts, but the price data does not back them, so they should be presented as hypotheses or dropped.

Data: fixtures/market_weekly#sha256=43a5ac4ef1f1 weeks 2021-11-01..2026-10-19. Estimation ends at the week of 2026-10-19 (the session the brief describes); nothing after it is used except as outcome data. Tests: block bootstrap (B=2000, block=8 weeks, null imposed), Benjamini-Hochberg at q=0.1 across every p-value in the run, α=0.05.

## WAM's conclusions vs the data

| # | What the brief said | Falsifiable form | Estimate [90% CI] | p | Outcome |
| --- | --- | --- | --- | --- | --- |
| W1 | AT&T and Johnson & Johnson have large operations that use fuel, while Microsoft and Oracle are less directly exposed. | Market-adjusted oil beta of {T, JNJ} is below that of {MSFT, ORCL} | +0.046 [-0.056, +0.145] | 0.776 | Not corroborated |
| W2-AMZN | Higher oil prices increase costs for transportation and manufacturing, which can squeeze profit margins at companies like Amazon and Johnson & Johnson. | AMZN's market-adjusted oil beta is negative (price reaction as proxy for margins) | -0.060 [-0.128, -0.002] | 0.074 | Not corroborated |
| W2-JNJ | Higher oil prices increase costs for transportation and manufacturing, which can squeeze profit margins at companies like Amazon and Johnson & Johnson. | JNJ's market-adjusted oil beta is negative (price reaction as proxy for margins) | -0.018 [-0.064, +0.021] | 0.242 | Not corroborated |
| W3 | Rate decisions feed through to every company you own, and most directly to AT&T, which carries significant debt. | T has the most negative market-adjusted 10Y-yield beta among Annie's 5 stocks | +1.57 [-0.84, +4.09] | 0.847 | Not corroborated |
| W4-MSFT | A stronger dollar can reduce the value of overseas earnings for multinational companies. | MSFT's market-adjusted dollar-index beta is negative | -0.22 [-0.64, +0.20] | 0.194 | Not corroborated |
| W4-AMZN | A stronger dollar can reduce the value of overseas earnings for multinational companies. | AMZN's market-adjusted dollar-index beta is negative | -0.33 [-0.87, +0.03] | 0.108 | Not corroborated |
| W4-GOOG | A stronger dollar can reduce the value of overseas earnings for multinational companies. | GOOG's market-adjusted dollar-index beta is negative | -0.25 [-0.65, +0.25] | 0.170 | Not corroborated |
| W5 | When bond yields fall, it can make borrowing cheaper for companies, but it also reflects concerns about economic growth. | No falsifiable form: both outcomes are compatible with the sentence | — | — | Untestable |

What stands out:

- **AT&T is not oil-exposed in its prices.** Market-adjusted oil elasticities: T +0.070, JNJ -0.018, MSFT -0.045, ORCL +0.005. AT&T's sign is the opposite of the brief's claim, though not significantly so.
- **Rates do not reach AT&T 'most directly'.** Per +100 bp in the 10-year yield, holding the market fixed: JNJ -2.5%, T -0.9%, ORCL -0.7%, MSFT +0.6%, AMZN +2.5%. The most rate-sensitive of Annie's stocks is JNJ, and all of the effects are small.
- **The dollar claim points the right way but is weak.** All three multinationals have negative dollar elasticities, but none clears the bar.

## The loop's own hypotheses

| # | Hypothesis | Test | Estimate [90% CI] | p | Outcome |
| --- | --- | --- | --- | --- | --- |
| H1 | Reader's top concern (Strait of Hormuz / Middle East Oil Shock, 8/10): a +10% weekly oil shock lowers an equal-weight basket of her holdings. | Equal-weight total effect of do(WTI +10%) on {T, JNJ, MSFT, ORCL, AMZN, VOO} is negative | +0.13% [-0.22%, +0.55%] | 0.729 | Not corroborated |
| H2 | The oil shock is a dual-plane signal: an unusual oil move (Echo) while the oil-to-holdings relationship has changed (Shadow). | Echo: |oil weekly return| unusual vs 5y (N1). Shadow: any holding's 26-week oil beta unusual vs its history (N2). Both needed. | +0.30 | 0.857 | Not corroborated |
| H3 | AT&T's fall in the week of Oct 19 was company-specific (earnings), not a rates or market move. | T's residual that week is unusual vs its history (N1) and is most of the move | -3.51 | 0.012 | Not corroborated (raw p < 0.05, fails FDR) |
| H4 | Last week's oil move predicts this week's returns for energy, AT&T and the market (a lead the brief could use). | Walk-forward out-of-sample R^2 of r(t) on oil(t-1) is > 0 for at least one of XLE, T, VOO | -0.008 | 1.000 | Not corroborated |

**H1, Annie's Hormuz scenario, as a do() intervention.** Effect of a +10% weekly oil shock on each holding (VOO stands in for her four index funds; direct effect plus the effect through the market; the market's own oil response is g = 0.0243):

| Holding | Total effect of do(WTI +10%) |
| --- | --- |
| AMZN | -0.23% |
| MSFT | -0.17% |
| JNJ | -0.12% |
| VOO | +0.23% |
| ORCL | +0.37% |
| T | +0.71% |

Placebo (oil shifted 26 weeks, which should show nothing): -0.115%, p = 0.287, so the placebo passes. Read this as the average oil response over 2021-26, which mixes supply shocks with demand-driven rallies. A Hormuz-type supply shock needs an identification step this run does not have yet: oil moves on geopolitical event days used as an instrument (next experiment).

**H3, AT&T's week.** The stock fell -11.33%. Market, oil, rates and dollar together explain +0.28%, leaving -11.61% that is company-specific (the Q3 report). The effect is decisive (z = -3.5), and p = 0.012 would pass on its own, but it does not clear the false-discovery bar across this run's 11 tests. Against WAM: the brief's People Watch line ties AT&T to rate decisions, but that week rates explain almost none of the move.

**H2, Echo × Shadow on oil.** Oil's weekly move was +1.82% (z = 0.3, p = 0.7231): Friday's +3.8% was big for one day, but ordinary for a week. No holding's 26-week oil beta is unusual against its history (lowest p: VOO 0.1429). No dual-plane signal, so no alert. That is the correct reading of a one-day spike.

**H4, oil as a leading signal.** Out-of-sample R² is below zero for XLE, T and VOO, so last week's oil move does not help predict this week's returns. Not corroborated, and logged so the idea is not re-proposed without new evidence.

## Is the falsifier itself trustworthy?

Before trusting any verdict, the test was run on 1000 synthetic series with no oil effect, with autocorrelated noise matching AT&T's residual scale, and on 200 series with a planted effect of -0.08.

| Check | Result | Target |
| --- | --- | --- |
| False-positive rate on pure noise | 5.8% ± 0.7% | ≈ 5% |
| Power to find the planted effect | 72% ± 3% | as high as possible |

(± is one standard error of the simulation estimate. The planted effect is about one standard error of a real oil beta, so modest power is expected: the test is built to avoid false alarms first.)

## What happened next (outcome layer L7)

Week of 2026-10-26, partial through Thursday Oct 29. This is one observation, recorded for the ledger and not scored.

| T | JNJ | MSFT | ORCL | AMZN | VOO | XLE | CL=F | DX-Y.NYB | ^TNX_pp |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| -0.05 | +4.32 | +1.07 | +10.62 | -1.7 | +1.25 | -0.89 | +0.38 | -0.08 | +0.001 |

ORCL (+10.6%; its investor day was Oct 28) and JNJ (+4.3%) moved far more than the market (+1.3%), with oil flat. Whether those moves were company-specific is not yet tested: the H3 residual check runs once the week closes.

## What this means for WAM

1. **Exposure sentences need evidence.** Sentences like 'AT&T and Johnson & Johnson have large operations that use fuel' read as analysis, but over five years the market has not priced them that way. The brief should attach the measured elasticity or drop the sentence. The ledger can supply the number every day.
2. **Separate company news from macro.** AT&T's −11% week was almost entirely company-specific (H3), yet the brief's People Watch framed AT&T through rates. A residual check like H3, run before writing, tells the writer when not to reach for a macro story.
3. **The reader's stated risks need a quantitative watch.** H1 and H2 are the first versions. The next run adds an event-day instrument for supply shocks and N3/N4 for the dual-plane pattern.

## Limits of this run

- Weekly Yahoo prices (5 significant digits) for research only; client-facing numbers should come from the FMP/FRED snapshot path.
- Price reactions are a proxy for 'margin' claims (W2). Margin data from filings is the direct test (Valuation node data, next run).
- Layers L3 (grounding) and L6 (multi-model red team, jaggedness) were not run: no model endpoint was available in this environment. The inquiry records mark them as not passed.
- H2's coincidence (N3) and lead-time (N4) nulls are not run yet, so a dual-plane hit would still be only a candidate.
- One brief and one reader. The method scales. These verdicts are specific to Oct 24 and Annie's list.

## Methodology: what these verdicts can and cannot tell you

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

## Reproduce

```
python -m shadowdesk research            # this report, the JSON and the ledger rows
```
