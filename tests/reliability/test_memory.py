import tempfile
import unittest
from pathlib import Path

from shadowdesk.reliability.memory import LearningMemory, MemoryRecord


class TestLearningMemory(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "memory.db"
        self.memory = LearningMemory(self.db_path)

    def tearDown(self):
        self.memory.close()
        self.tmpdir.cleanup()

    def test_record_and_precedents(self):
        sig = "abc123"
        self.memory.record(MemoryRecord(
            run_id="run-1", behavior_signature=sig, signals=["structural_failure"],
            failures=["output too short: 100 chars"], mode="hybrid",
            intervention_type="adjust_generation_params", outcome="failure",
        ))
        self.memory.record(MemoryRecord(
            run_id="run-2", behavior_signature=sig, signals=["structural_failure"],
            failures=["output too short: 100 chars"], mode="hybrid",
            intervention_type="enable_preflight_check", outcome="success",
        ))
        precedents = self.memory.precedents(sig)
        self.assertEqual(len(precedents), 2)
        self.assertEqual(precedents[0].run_id, "run-2")  # newest first

    def test_pattern_frequency_and_best_known_intervention(self):
        sig = "xyz789"
        self.memory.record(MemoryRecord(
            run_id="run-1", behavior_signature=sig, signals=[], failures=[],
            intervention_type="add_system_prompt_directive", outcome="failure",
        ))
        self.memory.record(MemoryRecord(
            run_id="run-2", behavior_signature=sig, signals=[], failures=[],
            intervention_type="add_system_prompt_directive", outcome="success",
        ))
        freq = self.memory.pattern_frequency(sig)
        self.assertEqual(freq["times_seen"], 2)
        self.assertEqual(freq["by_intervention"]["add_system_prompt_directive"]["success"], 1)
        self.assertEqual(freq["by_intervention"]["add_system_prompt_directive"]["failure"], 1)

        best = self.memory.best_known_intervention(sig)
        self.assertIsNotNone(best)
        self.assertEqual(best.run_id, "run-2")

    def test_unknown_signature_has_no_precedents(self):
        self.assertEqual(self.memory.precedents("never-seen"), [])
        self.assertIsNone(self.memory.best_known_intervention("never-seen"))
        self.assertEqual(self.memory.pattern_frequency("never-seen")["times_seen"], 0)


if __name__ == "__main__":
    unittest.main()
