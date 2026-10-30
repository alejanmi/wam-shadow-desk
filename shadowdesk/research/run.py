"""First autoresearch run: test WAM's conclusions and the loop's own hypotheses.

Each claim becomes a falsifiable statement about weekly returns, is tested
against a stated null with a block bootstrap (or an empirical window/walk-
forward null), and all p-values in the run go through Benjamini-Hochberg.
The result is one InquiryRecord per claim, with the exact queries used.

Model (weekly, estimation window ends at the session the brief describes):
    r_i = a + b_mkt*r_VOO + b_oil*r_WTI + b_rate*dY10 + b_usd*r_DXY + e
`b_oil` is the oil effect holding the market fixed (company-specific).
The do() total effect of an oil shock also flows through the market:
    TE_i = b_oil_i + b_mkt_i * g,   g = effect of oil on VOO (adjusting for rates and dollar)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from shadowdesk.research import stats
from shadowdesk.research.data import FACTORS, Panel
from shadowdesk.research.inquiry import InquiryRecord

STOCKS = ["T", "JNJ", "MSFT", "ORCL", "AMZN"]          # Annie's single-stock holdings
FACTOR_ORDER = ["mkt", "oil", "rate", "usd"]
COL = {f: i for i, f in enumerate(FACTOR_ORDER)}       # coefficient index = 1 + COL[f]
B, BLOCK, SEED, Q_FDR, ALPHA = 2000, 8, 7, 0.10, 0.05


@dataclass
class ClaimResult:
    claim_id: str
    source: str                    # "WAM brief" or "loop"
    quote: str                     # what WAM wrote, or the loop's statement
    test: str                      # the falsifiable form
    null: str                      # e.g. "N1", "N2", "N4", "L4 sign"
    estimate: float | None = None
    ci: tuple[float, float] | None = None
    p: float | None = None
    direction: str | None = None   # neg/pos expected sign
    survives_fdr: bool | None = None
    outcome: str = ""              # Corroborated | Not corroborated | Contradicted | Untestable
    queries: list[str] = field(default_factory=list)
    notes: str = ""
    extra: dict = field(default_factory=dict)


class Research:
    def __init__(self, panel: Panel):
        self.p = panel
        sl = panel.est_slice()
        self.n = sl.stop
        self.X = np.column_stack([panel.returns(FACTORS[f])[sl] for f in FACTOR_ORDER])
        self.Y = {s: panel.returns(s)[sl] for s in panel.prices if s not in FACTORS.values()}
        self.data_ref = f"fixtures/market_weekly#sha256={panel.sha256[:12]} weeks {panel.return_dates[0]}..{panel.as_of}"
        self.window_q = (f"returns(weekly log; ^TNX in pp) {panel.return_dates[0]}..{panel.as_of}, n={self.n}; "
                         f"model r_i ~ VOO + CL=F + ^TNX + DX-Y.NYB (Newey-West lags 2)")

    # ---- primitives -------------------------------------------------------
    def beta(self, sym: str, factor: str, idx: np.ndarray | None = None) -> float:
        i = slice(None) if idx is None else idx
        return float(stats.ols(self.Y[sym][i], self.X[i], hac_lags=0).coef[1 + COL[factor]])

    def g_oil_on_mkt(self, idx=None) -> float:
        i = slice(None) if idx is None else idx
        mkt = self.X[i][:, COL["mkt"]]
        others = self.X[i][:, [COL["oil"], COL["rate"], COL["usd"]]]
        return float(stats.ols(mkt, others, hac_lags=0).coef[1])

    def total_oil_effect(self, sym: str, idx=None) -> float:
        if sym == FACTORS["mkt"]:          # the market itself: its only oil channel is g
            return self.g_oil_on_mkt(idx)
        return self.beta(sym, "oil", idx) + self.beta(sym, "mkt", idx) * self.g_oil_on_mkt(idx)

    def boot(self, fn, seed_offset: int = 0) -> np.ndarray:
        return stats.block_bootstrap(fn, self.n, B=B, block=BLOCK, seed=SEED + seed_offset)

    def _sign_test(self, r: ClaimResult, fn, direction: str, seed_offset: int) -> ClaimResult:
        est = fn(np.arange(self.n))
        bs = self.boot(fn, seed_offset)
        r.estimate, r.ci, r.direction = est, (float(np.percentile(bs, 5)), float(np.percentile(bs, 95))), direction
        r.p = stats.centered_pvalue(bs, est, direction)
        r.extra["p_opposite"] = stats.centered_pvalue(bs, est, "pos" if direction == "neg" else "neg")
        r.queries += [self.window_q, f"block_bootstrap(B={B}, block={BLOCK}, seed={SEED + seed_offset}); centered_pvalue, one-sided H1: stat {'<' if direction == 'neg' else '>'} 0"]
        return r

    # ---- WAM's conclusions (Pocket Pulse, 2026-10-24) ---------------------
    def wam_claims(self) -> list[ClaimResult]:
        out = []
        r = ClaimResult("W1", "WAM brief", "AT&T and Johnson & Johnson have large operations that use fuel, while Microsoft and Oracle are less directly exposed.",
                        "Market-adjusted oil beta of {T, JNJ} is below that of {MSFT, ORCL}", "L4 sign")
        out.append(self._sign_test(r, lambda i: (self.beta("T", "oil", i) + self.beta("JNJ", "oil", i)) / 2
                                   - (self.beta("MSFT", "oil", i) + self.beta("ORCL", "oil", i)) / 2, "neg", 1))
        r.extra["betas"] = {s: round(self.beta(s, "oil"), 4) for s in ["T", "JNJ", "MSFT", "ORCL"]}

        for k, s in enumerate(["AMZN", "JNJ"]):
            r = ClaimResult(f"W2-{s}", "WAM brief", "Higher oil prices increase costs for transportation and manufacturing, which can squeeze profit margins at companies like Amazon and Johnson & Johnson.",
                            f"{s}'s market-adjusted oil beta is negative (price reaction as proxy for margins)", "L4 sign")
            out.append(self._sign_test(r, lambda i, s=s: self.beta(s, "oil", i), "neg", 10 + k))

        r = ClaimResult("W3", "WAM brief", "Rate decisions feed through to every company you own, and most directly to AT&T, which carries significant debt.",
                        "T has the most negative market-adjusted 10Y-yield beta among Annie's 5 stocks", "L4 sign")
        out.append(self._sign_test(r, lambda i: self.beta("T", "rate", i) - min(self.beta(s, "rate", i) for s in STOCKS if s != "T"), "neg", 20))
        r.extra["betas"] = {s: round(self.beta(s, "rate"), 4) for s in STOCKS}

        for k, s in enumerate(["MSFT", "AMZN", "GOOG"]):
            r = ClaimResult(f"W4-{s}", "WAM brief", "A stronger dollar can reduce the value of overseas earnings for multinational companies.",
                            f"{s}'s market-adjusted dollar-index beta is negative", "L4 sign")
            out.append(self._sign_test(r, lambda i, s=s: self.beta(s, "usd", i), "neg", 30 + k))

        out.append(ClaimResult("W5", "WAM brief", "When bond yields fall, it can make borrowing cheaper for companies, but it also reflects concerns about economic growth.",
                               "No falsifiable form: both outcomes are compatible with the sentence", "none", outcome="Untestable",
                               notes="Logged, never scored. A testable version would name a horizon and a growth series."))
        return out

    # ---- the loop's own hypotheses --------------------------------------
    def loop_claims(self, sensitivity_scenario: str = "Strait of Hormuz / Middle East Oil Shock") -> list[ClaimResult]:
        out = []
        # H1: do(oil +10%) total effect on Annie's holdings (Pearl), with a placebo
        effects = {s: self.total_oil_effect(s) for s in STOCKS + ["VOO"]}
        shock = np.log(1.10)
        r = ClaimResult("H1", "loop", f"Reader's top concern ({sensitivity_scenario}, 8/10): a +10% weekly oil shock lowers an equal-weight basket of her holdings.",
                        "Equal-weight total effect of do(WTI +10%) on {T, JNJ, MSFT, ORCL, AMZN, VOO} is negative", "L4 sign + L5 placebo")
        self._sign_test(r, lambda i: shock * np.mean([self.total_oil_effect(s, i) for s in STOCKS + ["VOO"]]), "neg", 40)
        r.extra["per_holding_pct"] = {s: round(float(100 * shock * e), 2) for s, e in sorted(effects.items(), key=lambda kv: kv[1])}
        r.extra["g_oil_on_mkt"] = round(self.g_oil_on_mkt(), 4)
        # placebo: oil shifted 26 weeks breaks the causal timing; the effect must vanish
        Xp = self.X.copy()
        Xp[:, COL["oil"]] = np.roll(Xp[:, COL["oil"]], 26)
        saved, self.X = self.X, Xp
        placebo = shock * np.mean([self.total_oil_effect(s) for s in STOCKS + ["VOO"]])
        pb = self.boot(lambda i: shock * np.mean([self.total_oil_effect(s, i) for s in STOCKS + ["VOO"]]), 41)
        self.X = saved
        r.extra["placebo_effect_pct"] = round(float(100 * placebo), 3)
        r.extra["placebo_p_neg"] = stats.centered_pvalue(pb, placebo, "neg")
        r.queries.append("do(): TE_i = b_oil_i + b_mkt_i * g, g = coef of CL=F in VOO ~ CL=F + ^TNX + DX-Y.NYB; adjustment set {^TNX, DX-Y.NYB}; placebo = CL=F rolled 26 weeks")
        r.notes = "Assumed DAG: oil -> market -> stock and oil -> stock; rates and dollar as common causes. Not identified if oil and stocks share an omitted driver (e.g. global demand)."
        out.append(r)

        # H2: Echo x Shadow for the oil channel (dual plane)
        oil = self.X[:, COL["oil"]]
        z_echo, p_echo = stats.residual_percentile(oil - oil.mean())
        shadows = {}
        for s in STOCKS + ["VOO"]:
            latest, p_sh, _ = stats.window_percentile(self.Y[s] if s != "VOO" else self.X[:, COL["mkt"]],
                                                      self.X[:, [c for c in range(4) if s != "VOO" or c != COL["mkt"]]],
                                                      col=COL["oil"] if s != "VOO" else 0, window=26)
            shadows[s] = (round(latest, 4), round(p_sh, 4))
        p_shadow = min(p for _, p in shadows.values())
        r = ClaimResult("H2", "loop", "The oil shock is a dual-plane signal: an unusual oil move (Echo) while the oil-to-holdings relationship has changed (Shadow).",
                        "Echo: |oil weekly return| unusual vs 5y (N1). Shadow: any holding's 26-week oil beta unusual vs its history (N2). Both needed.", "N1 x N2")
        r.estimate, r.p = float(z_echo), max(p_echo, min(1.0, p_shadow * len(shadows)))   # Bonferroni across holdings, then AND of planes
        r.extra = {"echo_z": round(z_echo, 2), "echo_p": round(p_echo, 4), "shadow_latest_beta_and_p": shadows,
                   "oil_week_return_pct": round(float(100 * oil[-1]), 2)}
        r.queries += [self.window_q, "Echo: residual_percentile(CL=F weekly log return, demeaned); Shadow: window_percentile(beta_oil, window=26) per holding, Bonferroni x6; dual-plane p = max(p_echo, p_shadow)"]
        r.notes = "N3 (coincidence null) and N4 (lead time) are not run for this pattern yet; a dual-plane hit here is a candidate, not an alert."
        out.append(r)

        # H3: AT&T's drop that week - idiosyncratic or factor-driven?
        fit = stats.ols(self.Y["T"], self.X)
        actual = float(self.Y["T"][-1])
        explained = float(fit.coef[0] + self.X[-1] @ fit.coef[1:])
        z, p_res = stats.residual_percentile(fit.resid)
        r = ClaimResult("H3", "loop", "AT&T's fall in the week of Oct 19 was company-specific (earnings), not a rates or market move.",
                        "T's residual that week is unusual vs its history (N1) and is most of the move", "N1")
        r.estimate, r.p = z, p_res
        r.extra = {"actual_pct": round(100 * actual, 2), "explained_by_factors_pct": round(100 * explained, 2),
                   "residual_pct": round(100 * (actual - explained), 2), "residual_share": round((actual - explained) / actual, 2) if actual else None}
        r.queries += [self.window_q, "ols(T ~ factors); residual_percentile(resid) for the as_of week"]
        r.notes = "Bears on WAM's People Watch line that rates reach AT&T most directly: that week, rates explain little of the drop."
        out.append(r)

        # H4: lead-lag - does last week's oil move predict this week's returns? (N4, walk-forward)
        res = {}
        for s in ["XLE", "T", "VOO"]:
            y = self.Y[s] if s != "VOO" else self.X[:, COL["mkt"]]
            res[s] = stats.walk_forward_r2(y, oil)
        r = ClaimResult("H4", "loop", "Last week's oil move predicts this week's returns for energy, AT&T and the market (a lead the brief could use).",
                        "Walk-forward out-of-sample R^2 of r(t) on oil(t-1) is > 0 for at least one of XLE, T, VOO", "N4")
        best = max(res, key=lambda k: res[k][0])
        r.estimate = res[best][0]
        r.p = 0.01 if r.estimate > 0.02 else 0.5 if r.estimate > 0 else 1.0   # coarse: N4 judged on OOS R^2 sign/size
        r.extra = {s: {"oos_r2": round(v[0], 4), "forecasts": v[1]} for s, v in res.items()}
        r.queries += [self.window_q, "walk_forward_r2(y_t, CL=F_{t-1}, min_train=104 weeks, expanding refit)"]
        out.append(r)
        return out

    # ---- falsifier self-test (Phase 3 exit test) --------------------------
    def self_test(self, n_null: int = 1000, n_planted: int = 200, b: int = 500, beta_true: float = -0.08) -> dict:
        rng = np.random.default_rng(123)
        oil = self.X[:, COL["oil"]]
        resid_sd = float(np.std(stats.ols(self.Y["T"], self.X).resid))
        def p_for(y):
            fn = lambda i: float(stats.ols(y[i], self.X[i], hac_lags=0).coef[1 + COL["oil"]])
            bs = stats.block_bootstrap(fn, self.n, B=b, block=BLOCK, seed=int(rng.integers(1e9)))
            return stats.centered_pvalue(bs, fn(np.arange(self.n)), "neg")
        def series(beta):  # AR(1) noise so the bootstrap is tested on autocorrelated residuals
            e = rng.normal(0, resid_sd, self.n)
            for t in range(1, self.n):
                e[t] += 0.2 * e[t - 1]
            return self.X @ np.array([0.9, beta, 0.0, 0.0]) + e
        fp = np.mean([p_for(series(0.0)) < ALPHA for _ in range(n_null)])
        power = np.mean([p_for(series(beta_true)) < ALPHA for _ in range(n_planted)])
        se = lambda x, n: float(np.sqrt(max(x * (1 - x), 1e-9) / n))
        return {"false_positive_rate": float(fp), "fpr_se": se(fp, n_null), "n_null": n_null,
                "power": float(power), "power_se": se(power, n_planted), "n_planted": n_planted,
                "planted_beta": beta_true, "alpha": ALPHA, "bootstrap_B": b}

    # ---- outcome (L7): what happened the following (partial) week ---------
    def outcome_week(self) -> dict | None:
        i = self.p.outcome_index()
        if i is None:
            return None
        rows = {s: round(100 * float(np.exp(self.p.returns(s)[i]) - 1), 2) for s in STOCKS + ["VOO", "XLE", "CL=F", "DX-Y.NYB"]}
        rows["^TNX_pp"] = round(float(self.p.returns("^TNX")[i]), 3)
        return {"week": self.p.return_dates[i], "returns_pct": rows,
                "note": "Partial week (through Thu Oct 29). One observation; recorded for the ledger, not scored."}


def judge(results: list[ClaimResult]) -> list[ClaimResult]:
    pv = {r.claim_id: r.p for r in results if r.p is not None and r.outcome != "Untestable"}
    keep = stats.benjamini_hochberg(pv, Q_FDR)
    for r in results:
        if r.outcome == "Untestable" or r.p is None:
            continue
        r.survives_fdr = keep[r.claim_id]
        r.extra["suggestive"] = bool(r.p < ALPHA and not r.survives_fdr)
        if r.survives_fdr:
            r.outcome = "Corroborated"
        elif r.extra.get("p_opposite") is not None and r.extra["p_opposite"] < ALPHA:
            r.outcome = "Contradicted"
        else:
            r.outcome = "Not corroborated"
        if r.claim_id == "H1" and r.outcome == "Corroborated" and r.extra.get("placebo_p_neg", 1) < ALPHA:
            r.outcome = "Not corroborated"
            r.notes += " Placebo also showed an effect, so the causal reading fails (L5)."
    return results


def to_inquiry(r: ClaimResult, data_ref: str) -> InquiryRecord:
    layers = ["L0", "L1", "L2"]
    failed = None
    nulls: dict[str, float | None] = {}
    if r.outcome == "Untestable":
        return InquiryRecord(claim_id=f"2026-10-24-{r.claim_id}", statement=r.quote, queries=["(no falsifiable form)"],
                             layers_passed=layers, data_refs=[data_ref])
    key = {"N1": "N1", "N4": "N4", "N1 x N2": "N2"}.get(r.null, "N1")
    nulls[key] = r.p
    if r.outcome == "Corroborated":
        layers.append("L4")
        if r.claim_id == "H1":
            layers.append("L5")
    else:
        failed = "L4" if r.outcome != "Contradicted" else f"{key}-contradicted"
    rec = InquiryRecord(claim_id=f"2026-10-24-{r.claim_id}", statement=r.quote, queries=r.queries, layers_passed=layers,
                        failed_at=failed, nulls=nulls, data_refs=[data_ref],
                        rivals=[] if r.source == "loop" else ["no effect beyond the market", "effect of the opposite sign"])
    return rec
