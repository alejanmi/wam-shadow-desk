import unittest
from pathlib import Path

from shadowdesk.reliability.detectors import detect_all
from shadowdesk.reliability.trace import ExecutionTrace

FIXTURES = Path(__file__).resolve().parents[2] / "shadowdesk" / "reliability" / "assets" / "fixtures"


class TestDetectors(unittest.TestCase):
    def test_ok_fixture_has_no_anomalies(self):
        trace = ExecutionTrace.load(FIXTURES / "execution_ok.json")
        self.assertEqual(detect_all(trace), [])

    def test_truncated_fixture_flags_structural_failures(self):
        trace = ExecutionTrace.load(FIXTURES / "execution_truncated_joke_block.json")
        anomalies = detect_all(trace)
        signals = {a.signal for a in anomalies}
        self.assertIn("structural_failure", signals)

    def test_retry_storm_fixture_flags_retry_storm_and_time_and_no_progress(self):
        trace = ExecutionTrace.load(FIXTURES / "execution_retry_storm.json")
        anomalies = detect_all(trace)
        signals = {a.signal for a in anomalies}
        self.assertIn("retry_storm", signals)
        self.assertIn("excessive_time", signals)
        self.assertIn("declining_information_gain", signals)
        retry_anomaly = next(a for a in anomalies if a.signal == "retry_storm")
        self.assertEqual(retry_anomaly.severity, "critical")
        self.assertEqual(len(retry_anomaly.evidence["attempt_indices"]), 3)

    def test_near_duplicate_content_flags_declining_information_gain(self):
        trace = ExecutionTrace.load(FIXTURES / "execution_retry_storm.json")
        trace.attempts[1].output_text += "<!-- harmless markup variation -->"
        anomalies = detect_all(trace)
        declining = [a for a in anomalies if a.signal == "declining_information_gain"]
        self.assertTrue(declining)
        self.assertGreaterEqual(declining[0].evidence["content_similarity"], 0.98)

    def test_preflight_catchable_fixture_flags_preflight_would_have_caught(self):
        trace = ExecutionTrace.load(FIXTURES / "execution_preflight_catchable.json")
        anomalies = detect_all(trace)
        signals = {a.signal for a in anomalies}
        self.assertIn("preflight_would_have_caught", signals)

    def test_ok_fixture_has_no_preflight_anomaly_even_with_no_payload(self):
        trace = ExecutionTrace.load(FIXTURES / "execution_ok.json")
        self.assertIsNone(trace.input_payload)
        anomalies = detect_all(trace)
        self.assertEqual([a for a in anomalies if a.signal == "preflight_would_have_caught"], [])

    def test_behavior_signature_is_stable_across_equivalent_traces(self):
        t1 = ExecutionTrace.load(FIXTURES / "execution_truncated_joke_block.json")
        t2 = ExecutionTrace.load(FIXTURES / "execution_retry_storm.json")
        # retry storm's 3 attempts share the exact same failure signature as the
        # single truncated attempt, and both are "hybrid" mode -> same behavior signature
        self.assertEqual(t1.behavior_signature(), t2.behavior_signature())


if __name__ == "__main__":
    unittest.main()
