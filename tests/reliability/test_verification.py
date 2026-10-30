import unittest
from pathlib import Path

from shadowdesk.reliability.trace import ExecutionTrace
from shadowdesk.reliability.verification import verify

FIXTURES = Path(__file__).resolve().parents[2] / "shadowdesk" / "reliability" / "assets" / "fixtures"


class TestVerification(unittest.TestCase):
    def test_validator_threshold_change_clears_size_failure(self):
        trace = ExecutionTrace.load(FIXTURES / "execution_preflight_catchable.json")
        result = verify(trace, "loosen_validator_threshold", {"check": "chars_min", "value": 1000})
        self.assertTrue(result.passed)

    def test_preflight_intervention_verified_true_when_payload_thin(self):
        trace = ExecutionTrace.load(FIXTURES / "execution_preflight_catchable.json")
        result = verify(trace, "enable_preflight_check", {})
        self.assertTrue(result.passed)

    def test_preflight_intervention_unverifiable_without_payload(self):
        trace = ExecutionTrace.load(FIXTURES / "execution_truncated_joke_block.json")
        result = verify(trace, "enable_preflight_check", {})
        self.assertIsNone(result.passed)

    def test_max_tokens_increase_verified_true_for_truncation(self):
        trace = ExecutionTrace.load(FIXTURES / "execution_truncated_joke_block.json")
        result = verify(trace, "adjust_generation_params", {"field": "max_tokens", "value": 65536})
        self.assertTrue(result.passed)

    def test_max_tokens_increase_verified_false_when_not_meaningfully_larger(self):
        trace = ExecutionTrace.load(FIXTURES / "execution_truncated_joke_block.json")
        result = verify(trace, "adjust_generation_params", {"field": "max_tokens", "value": 32800})
        self.assertFalse(result.passed)

    def test_validator_gate_verified_true_when_final_attempt_failed(self):
        trace = ExecutionTrace.load(FIXTURES / "execution_truncated_joke_block.json")
        result = verify(trace, "enable_validator_gate", {})
        self.assertTrue(result.passed)

    def test_validator_gate_verified_false_when_final_attempt_passed(self):
        trace = ExecutionTrace.load(FIXTURES / "execution_ok.json")
        result = verify(trace, "enable_validator_gate", {})
        self.assertFalse(result.passed)

    def test_unrelated_param_change_is_unverifiable(self):
        trace = ExecutionTrace.load(FIXTURES / "execution_truncated_joke_block.json")
        result = verify(trace, "adjust_generation_params", {"field": "temperature", "value": 0.5})
        self.assertIsNone(result.passed)


if __name__ == "__main__":
    unittest.main()
