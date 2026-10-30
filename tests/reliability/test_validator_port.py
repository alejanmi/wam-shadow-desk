import unittest
from pathlib import Path

from shadowdesk.reliability.trace import ExecutionTrace
from shadowdesk.reliability.validator_port import run_validator

FIXTURES = Path(__file__).resolve().parents[2] / "shadowdesk" / "reliability" / "assets" / "fixtures"


class TestValidatorPort(unittest.TestCase):
    def test_ok_fixture_is_clean(self):
        trace = ExecutionTrace.load(FIXTURES / "execution_ok.json")
        a = trace.attempts[0]
        result = run_validator(a.output_text)
        self.assertTrue(result.ok)
        self.assertEqual(result.failures, [])

    def test_truncated_fixture_fails_on_joke_block(self):
        trace = ExecutionTrace.load(FIXTURES / "execution_truncated_joke_block.json")
        result = run_validator(trace.attempts[0].output_text)
        self.assertFalse(result.ok)
        self.assertTrue(any("joke block count" in f for f in result.failures))
        self.assertTrue(any("truncation" in f for f in result.failures))

    def test_missing_section_fixture(self):
        trace = ExecutionTrace.load(FIXTURES / "execution_missing_section_and_placeholder.json")
        result = run_validator(trace.attempts[0].output_text)
        self.assertFalse(result.ok)
        self.assertIn("missing section: situations", result.failures)
        self.assertTrue(any("placeholder" in f for f in result.failures))
        self.assertTrue(any("em dash" in f for f in result.failures))

    def test_threshold_override_can_clear_a_size_failure(self):
        trace = ExecutionTrace.load(FIXTURES / "execution_preflight_catchable.json")
        text = trace.attempts[0].output_text
        default_result = run_validator(text)
        self.assertFalse(default_result.ok)
        lenient = run_validator(text, thresholds={"chars_min": 1000})
        # size failure specifically should be gone, even though other structural failures remain
        self.assertFalse(any("output too short" in f for f in lenient.failures))

    def test_fixtures_recorded_validator_result_matches_replay(self):
        for name in [
            "execution_ok.json",
            "execution_truncated_joke_block.json",
            "execution_missing_section_and_placeholder.json",
        ]:
            trace = ExecutionTrace.load(FIXTURES / name)
            for a in trace.attempts:
                replayed = run_validator(a.output_text)
                self.assertEqual(replayed.ok, a.validator.ok, msg=f"{name} attempt {a.attempt_index}")
                self.assertEqual(sorted(replayed.failures), sorted(a.validator.failures), msg=name)


if __name__ == "__main__":
    unittest.main()
