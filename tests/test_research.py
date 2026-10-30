import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from shadowdesk.research import run as runmod
from shadowdesk.research import stats
from shadowdesk.research.data import load_panel
from shadowdesk.research.inquiry import Verdict

MARKET = Path(__file__).resolve().parents[1] / "fixtures" / "market_weekly"


class TestStats(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(0)

    def test_ols_recovers_planted_coefficients(self):
        X = self.rng.normal(size=(500, 3))
        y = 0.5 + X @ np.array([1.0, -0.3, 0.0]) + self.rng.normal(0, 0.1, 500)
        fit = stats.ols(y, X)
        np.testing.assert_allclose(fit.coef, [0.5, 1.0, -0.3, 0.0], atol=0.03)
        self.assertGreater(abs(fit.t[2]), 20)

    def test_centered_pvalue_separates_signal_from_noise(self):
        X = self.rng.normal(size=(260, 1))
        for beta, small in ((-0.5, True), (0.0, False)):
            y = beta * X[:, 0] + self.rng.normal(0, 1, 260)
            fn = lambda i: float(stats.ols(y[i], X[i], hac_lags=0).coef[1])
            p = stats.centered_pvalue(stats.block_bootstrap(fn, 260, B=300, seed=1), fn(np.arange(260)), "neg")
            self.assertEqual(p < 0.01, small, (beta, p))

    def test_benjamini_hochberg(self):
        keep = stats.benjamini_hochberg({"a": 0.001, "b": 0.012, "c": 0.04, "d": 0.5}, q=0.05)
        self.assertEqual(keep, {"a": True, "b": True, "c": False, "d": False})
        self.assertEqual(stats.benjamini_hochberg({"x": float("nan"), "y": 0.001}, q=0.05), {"x": False, "y": True})

    def test_walk_forward_detects_a_real_lead_and_rejects_noise(self):
        x = self.rng.normal(size=400)
        y_lead = np.r_[0, 0.8 * x[:-1]] + self.rng.normal(0, 0.5, 400)
        self.assertGreater(stats.walk_forward_r2(y_lead, x)[0], 0.3)
        self.assertLess(stats.walk_forward_r2(self.rng.normal(size=400), x)[0], 0.02)

    def test_window_percentile_flags_a_structural_break(self):
        X = self.rng.normal(size=(260, 1))
        beta = np.r_[np.zeros(234), np.full(26, 1.5)]          # relationship appears in the last 26 weeks
        y = beta * X[:, 0] + self.rng.normal(0, 0.5, 260)
        latest, p, _ = stats.window_percentile(y, X, col=0, window=26)
        self.assertGreater(latest, 1.0)
        self.assertLess(p, 0.05)

    def test_residual_percentile(self):
        r = np.r_[self.rng.normal(0, 1, 259), -6.0]
        z, p = stats.residual_percentile(r)
        self.assertLess(z, -4)
        self.assertLess(p, 0.01)


class TestPanel(unittest.TestCase):
    def test_hash_verified_and_tamper_detected(self):
        panel = load_panel(MARKET)
        self.assertEqual(panel.sha256[:12], "43a5ac4ef1f1")
        self.assertEqual(panel.return_dates[panel.est_slice().stop - 1], "2026-10-19")
        self.assertEqual(panel.return_dates[panel.outcome_index()], "2026-10-26")
        with tempfile.TemporaryDirectory() as d:
            shutil.copy(MARKET / "meta.json", d)
            text = (MARKET / "series.json").read_text(encoding="utf-8").replace("20.93,20.92", "20.94,20.92")
            Path(d, "series.json").write_text(text, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_panel(d)


class TestRunEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._B = runmod.B
        runmod.B = 150                     # fast; verdicts on real data use B=2000
        R = runmod.Research(load_panel(MARKET))
        cls.R = R
        cls.results = runmod.judge(R.wam_claims() + R.loop_claims())

    @classmethod
    def tearDownClass(cls):
        runmod.B = cls._B

    def test_every_claim_is_scored_or_marked_untestable(self):
        ids = [r.claim_id for r in self.results]
        self.assertEqual(len(ids), 12)
        for r in self.results:
            if r.claim_id == "W5":
                self.assertEqual(r.outcome, "Untestable")
            else:
                self.assertIsNotNone(r.p, r.claim_id)
                self.assertTrue(r.queries, r.claim_id)
                self.assertIn(r.outcome, {"Corroborated", "Not corroborated", "Contradicted"})

    def test_att_week_is_idiosyncratic(self):
        h3 = next(r for r in self.results if r.claim_id == "H3")
        self.assertLess(h3.extra["actual_pct"], -10)
        self.assertGreater(h3.extra["residual_share"], 0.9)

    def test_no_lookahead(self):
        self.assertEqual(self.R.n, self.R.p.est_slice().stop)
        self.assertEqual(self.R.p.return_dates[self.R.n - 1], "2026-10-19")

    def test_inquiry_records(self):
        recs = [runmod.to_inquiry(r, self.R.data_ref) for r in self.results]
        by_id = {r.claim_id: r for r in recs}
        self.assertEqual(by_id["2026-10-24-W5"].verdict, Verdict.UNTESTABLE)
        for rec in recs:
            self.assertTrue(rec.data_refs[0].startswith("fixtures/market_weekly#sha256="))


if __name__ == "__main__":
    unittest.main()
