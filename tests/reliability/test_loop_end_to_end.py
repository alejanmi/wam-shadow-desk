"""End-to-end test of the full Detect -> Diagnose -> Intervene -> Verify -> Learn
loop, calling the real local Ollama daemon. Skipped automatically if Ollama
isn't reachable (e.g. in a CI environment without a GPU) rather than failing.
"""

import json
import tempfile
import unittest
from pathlib import Path

from shadowdesk.reliability.loop import run_once
from shadowdesk.reliability.memory import LearningMemory
from shadowdesk.reliability.ollama_client import is_available
from shadowdesk.reliability.trace import ExecutionTrace

FIXTURES = Path(__file__).resolve().parents[2] / "shadowdesk" / "reliability" / "assets" / "fixtures"
WORKFLOW_PATH = Path(__file__).resolve().parents[2] / "shadowdesk" / "reliability" / "assets" / "advisor_workflow_redacted.json"


@unittest.skipUnless(is_available(), "ollama daemon not reachable at OLLAMA_BASE_URL")
class TestLoopEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.memory = LearningMemory(Path(self.tmpdir.name) / "memory.db")
        with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
            self.workflow = json.load(f)

    def tearDown(self):
        self.memory.close()
        self.tmpdir.cleanup()

    def test_preflight_catchable_case_ends_in_a_diagnosis_and_memory_record(self):
        trace = ExecutionTrace.load(FIXTURES / "execution_preflight_catchable.json")
        result = run_once(trace, self.workflow, self.memory)

        self.assertTrue(len(result.anomalies) > 0)
        self.assertIsNotNone(result.diagnosis)
        self.assertIsNone(result.diagnosis.error, msg=result.diagnosis.why if result.diagnosis.error else None)
        self.assertIsNotNone(result.memory_record_id)

        precedents = self.memory.precedents(trace.behavior_signature())
        self.assertEqual(len(precedents), 1)
        self.assertEqual(precedents[0].outcome, result.outcome)

    def test_retry_storm_case_is_diagnosed(self):
        trace = ExecutionTrace.load(FIXTURES / "execution_retry_storm.json")
        result = run_once(trace, self.workflow, self.memory)

        self.assertIsNotNone(result.diagnosis)
        self.assertIsNone(result.diagnosis.error)
        signals = {a.signal for a in result.anomalies}
        self.assertIn("retry_storm", signals)

    def test_ok_case_produces_no_diagnosis(self):
        trace = ExecutionTrace.load(FIXTURES / "execution_ok.json")
        result = run_once(trace, self.workflow, self.memory)
        self.assertEqual(result.anomalies, [])
        self.assertIsNone(result.diagnosis)
        self.assertIsNone(result.memory_record_id)


if __name__ == "__main__":
    unittest.main()
