import unittest
from pathlib import Path

from shadowdesk.reliability.preflight_port import run_preflight
from shadowdesk.reliability.trace import ExecutionTrace

FIXTURES = Path(__file__).resolve().parents[2] / "shadowdesk" / "reliability" / "assets" / "fixtures"


class TestPreflightPort(unittest.TestCase):
    def test_thin_payload_fails_preflight(self):
        trace = ExecutionTrace.load(FIXTURES / "execution_preflight_catchable.json")
        result = run_preflight(trace.input_payload)
        self.assertFalse(result.ok)
        self.assertTrue(any("newsContext" in f for f in result.failures))
        self.assertTrue(any("sectorExposure" in f for f in result.failures))

    def test_full_payload_passes_preflight(self):
        full_payload = {
            "Ticker": "AAPL, MSFT, NVDA",
            "advisorName": "J. Rivera",
            "Mode": "hybrid",
            "bookMove": "up 0.4%",
            "newsContext": [f"headline {i}" for i in range(80)],
            "macroContext": [f"series {i}" for i in range(15)],
            "holdingsPerf": [{"ticker": "AAPL", "chg": 0.4}] * 10,
            "sectorExposure": {"Tech": 0.3, "Health": 0.2},
            "fixedIncome": {"agg": 0.1},
            "earningsThisWeek": ["AAPL"],
            "economicCalendar": ["CPI"],
            "smartMoney": {"hasData": True},
            "padding": "x" * 200_000,  # payload size sanity check wants ~400k chars total
        }
        result = run_preflight(full_payload)
        self.assertTrue(result.ok, msg=result.failures)


if __name__ == "__main__":
    unittest.main()
