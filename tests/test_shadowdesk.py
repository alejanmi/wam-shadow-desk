import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from shadowdesk.compute import brief_facts as bf
from shadowdesk.core.http import HttpResponse, redact_url
from shadowdesk.ingest.fred import FREDClient, parse_observations
from shadowdesk.ingest.reader import load_reader
from shadowdesk.ingest.rss import parse_feed
from shadowdesk.ingest.sec import filings_in_window
from shadowdesk.ingest.snapshot import SnapshotMissing, SnapshotStore
from shadowdesk.ledger.store import Ledger
from shadowdesk.parity.checks import RunFixtures, live_checks, offline_checks
from shadowdesk.research.inquiry import InquiryRecord, Verdict

ROOT = Path(__file__).resolve().parents[1]
FX = RunFixtures.load(ROOT / "fixtures" / "run6361")
READER = load_reader(ROOT / "config" / "readers" / "annie.yaml")


class TestPortsReproduceRun6361(unittest.TestCase):
    def setUp(self):
        self.checks = {c.check_id: c for c in offline_checks(FX, READER)}

    def test_every_recomputation_matches(self):
        for cid in ("P-BREADTH", "P-MOVERS", "P-SECTORS", "P-SRO", "P-RSI", "P-RATINGS"):
            self.assertEqual(self.checks[cid].status, "pass", f"{cid}: {self.checks[cid].expected} != {self.checks[cid].actual}")

    def test_known_findings_are_raised(self):
        for cid in ("F-RATINGS-NEWS-DROPPED", "F-EARNINGS-COVERAGE", "F-TICKER", "F-VIX-TWO-VALUES",
                    "F-STALE-AS-TODAY", "F-FEED-MISSING", "F-SENSITIVITY-UNLINKED", "F-SECTOR-EXPOSURE"):
            self.assertEqual(self.checks[cid].status, "finding", cid)

    def test_every_check_has_a_query(self):
        for c in self.checks.values():
            self.assertTrue(c.query.strip(), c.check_id)


class TestRatings(unittest.TestCase):
    def test_fixed_ranks_downgrade_above_reiterations(self):
        fixed = bf.rating_changes_fixed(FX.grade_rows(), FX.run_time)
        self.assertIn(("AAPL", "downgraded"), [(r["symbol"], r["action"]) for r in fixed])
        self.assertEqual(len(fixed), 6)

    def test_window_excludes_old_rows(self):
        rows = [{"symbol": "X", "date": "2026-10-01", "gradingCompany": "A", "newGrade": "Buy", "action": "upgrade"}]
        self.assertEqual(bf.rating_changes(rows, FX.run_time), [])


class TestPoliticians(unittest.TestCase):
    def test_buy_sell_pair_dropped_and_caps(self):
        base = {"symbol": "T", "firstName": "Jane", "lastName": "Doe Jr", "transactionDate": "2026-10-01",
                "amount": "$1,001 - $15,000", "disclosureDate": "2026-10-20"}
        house = [dict(base, type="Purchase"), dict(base, type="Sale"),
                 dict(base, symbol="AMZN", type="Purchase", transactionDate="2026-10-02"),
                 dict(base, symbol="ZZZ", type="Purchase")]
        out = bf.politician_trades([], house, ["T", "AMZN"])
        self.assertEqual([(r["symbol"], r["person"]) for r in out], [("AMZN", "Jane Doe")])


class TestSnapshotStore(unittest.TestCase):
    def test_live_records_then_replay_reads_without_network(self):
        calls = []

        def fake(url, headers=None):
            calls.append(url)
            return HttpResponse(200, b'[{"close": 1}]', redact_url(url))

        with tempfile.TemporaryDirectory() as d:
            live = SnapshotStore(d, "2026-10-23", "live", fake)
            data, prov = live.get_json("fmp", "k1", "https://x/y?symbol=T&apikey=SECRET123")
            self.assertEqual(data, [{"close": 1}])
            self.assertNotIn("SECRET123", prov.url)
            meta = next(Path(d).rglob("*.meta.json")).read_text()
            self.assertNotIn("SECRET123", meta)
            replay = SnapshotStore(d, "2026-10-23", "replay")
            self.assertEqual(replay.get_json("fmp", "k1", "ignored")[0], [{"close": 1}])
            self.assertEqual(len(calls), 1)
            self.assertEqual(replay.verify(), [])
            with self.assertRaises(SnapshotMissing):
                replay.get("fmp", "other", "u")


class TestParsers(unittest.TestCase):
    def test_rss_and_atom(self):
        rss = b"""<rss><channel><item><title>Oil jumps</title><link>https://a/1</link>
        <pubDate>Fri, 23 Oct 2026 20:00:00 GMT</pubDate><description>&lt;p&gt;Crude rose&lt;/p&gt;</description></item></channel></rss>"""
        atom = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Fed holds</title>
        <link href="https://b/2"/><updated>2026-10-28T18:00:00Z</updated></entry></feed>"""
        prov = None
        a = parse_feed("t", rss, prov)[0]
        self.assertEqual((a.title, a.link, a.snippet), ("Oil jumps", "https://a/1", "Crude rose"))
        self.assertTrue(a.published.startswith("2026-10-23T20:00"))
        self.assertEqual(parse_feed("t", atom, prov)[0].link, "https://b/2")

    def test_fred_skips_missing_values(self):
        obs = parse_observations({"observations": [{"date": "2026-10-21", "value": "5.13"},
                                                   {"date": "2026-10-22", "value": "4.96"},
                                                   {"date": "2026-10-23", "value": "."}]})
        self.assertEqual(obs[-1], ("2026-10-22", 4.96))

    def test_sec_8k_items(self):
        subs = {"filings": {"recent": {"form": ["8-K", "10-Q", "8-K"], "filingDate": ["2026-10-21", "2026-10-22", "2026-09-01"],
                                       "accessionNumber": ["0000732717-26-000370", "a", "b"], "items": ["2.02,9.01", "", "5.02"],
                                       "primaryDocument": ["t-8k.htm", "q.htm", "x.htm"]}}}
        f = filings_in_window("T", 732717, subs, None, "2026-10-19", "2026-10-24", forms=("8-K",))
        self.assertEqual([(x.form, x.items) for x in f], [("8-K", ("2.02", "9.01"))])
        self.assertIn("/732717/000073271726000370/t-8k.htm", f[0].url)


class TestReader(unittest.TestCase):
    def test_profile(self):
        self.assertEqual(len(READER.all_tickers), 16)
        self.assertTrue(any("CITI" in i for i in READER.ticker_issues()))
        self.assertEqual(READER.top_sensitivities(7)[0].concern, 8)


class TestInquiryVerdicts(unittest.TestCase):
    def test_tiers(self):
        mk = lambda **k: InquiryRecord(claim_id="c", statement="s", queries=["q"], **k)
        self.assertEqual(mk(layers_passed=["L0", "L1", "L2"], hypothesis=False).verdict, Verdict.FACT)
        self.assertEqual(mk(layers_passed=["L0", "L1", "L2", "L3", "L4"]).verdict, Verdict.UNTESTABLE)  # no null run
        full = ["L0", "L1", "L2", "L3", "L4"]
        self.assertEqual(mk(layers_passed=full, nulls={"N1": 0.01}).verdict, Verdict.VERIFIED)
        self.assertEqual(mk(layers_passed=full + ["L5"], nulls={"N1": 0.01}).verdict, Verdict.SUPPORTED)
        self.assertEqual(mk(layers_passed=full, nulls={"N1": 0.01}, model_agreement=0.5).verdict, Verdict.JAGGED)
        self.assertEqual(mk(layers_passed=full, nulls={"N1": 0.01}, red_team_beaten=False).verdict, Verdict.CONTESTED)
        self.assertEqual(mk(failed_at="N3", nulls={"N3": 0.4}).verdict, Verdict.REFUTED)
        with self.assertRaises(ValueError):
            InquiryRecord(claim_id="c", statement="s", queries=[])

    def test_ledger_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            led = Ledger(Path(d) / "l.db")
            n = led.add_checks("r1", offline_checks(FX, READER))
            led.add_inquiry(InquiryRecord(claim_id="c1", statement="s", queries=["q"], layers_passed=["L0", "L1", "L2"], hypothesis=False))
            self.assertEqual(len(led.checks_for("r1")), n)
            led.close()


class _FakeFMP:
    """Serves EOD rows consistent with run 6361 so live_checks can be exercised offline."""

    def __init__(self):
        self.q = {q["symbol"]: q for q in FX.market["price"]["quotes"] + FX.market["price"]["watchlistQuotes"]}
        self.q.update({s: {"price": v["price"], "previousClose": v["previousClose"]} for s, v in FX.market["sectors"].items()})

    def historical_eod(self, sym, frm, to):
        if sym not in self.q:
            raise RuntimeError("no data")
        q = self.q[sym]
        return [{"date": "2026-10-23", "close": q["price"]}, {"date": "2026-10-22", "close": q["previousClose"]}], _P()

    def grades(self, sym):
        return [r for r in FX.grade_rows() if r["symbol"] == sym], _P()


class _P:
    def ref(self):
        return "fake"


class _FakeSEC:
    def cik_map(self):
        return {"T": 732717}, _P()

    def submissions(self, cik):
        return {"filings": {"recent": {"form": ["8-K"], "filingDate": ["2026-10-21"], "accessionNumber": ["0000732717-26-000370"],
                                       "items": ["2.02"], "primaryDocument": ["t.htm"]}}}, _P()


class TestLiveChecksShape(unittest.TestCase):
    def test_live_checks_against_consistent_data(self):
        with tempfile.TemporaryDirectory() as d:
            fred = FREDClient(SnapshotStore(d, "2026-10-23", "replay"))  # no snapshots: every FRED check reports L0 failure
            checks = {c.check_id: c for c in live_checks(FX, READER, _FakeFMP(), fred, _FakeSEC(), "2026-10-23")}
        self.assertEqual(checks["L-EOD-T"].status, "pass")
        self.assertEqual(checks["L-SECTOR-XLE"].status, "pass")
        self.assertEqual(checks["L-RATINGS"].status, "pass")
        self.assertEqual(checks["L-SEC-8K"].status, "pass")
        self.assertEqual(checks["L-EOD-CITI"].status, "fail")
        self.assertEqual(checks["L-FRED-yield10Y"].layer, "L0")


if __name__ == "__main__":
    unittest.main()
