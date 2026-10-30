import json
import tempfile
import unittest
from pathlib import Path

from shadowdesk.ledger.experiment_record import ExperimentRecord, read_record, write_record


def _make_record(**overrides):
    fields = {
        "name": "raise-preflight-threshold",
        "hypothesis": "Raising the preflight length threshold reduces false positives.",
        "changed_workflow_path": "Santi Miguel AI Agent (F) [gated].json",
        "status": "passed",
        "elapsed_seconds": 12.5,
        "evidence": {"preflight_catches": 3},
        "verification": {"verified": True, "basis": "replayed against wam fixtures"},
    }
    fields.update(overrides)
    return ExperimentRecord(**fields)


class ExperimentRecordTests(unittest.TestCase):
    def test_rejects_missing_name(self):
        with self.assertRaises(ValueError):
            _make_record(name="")

    def test_rejects_missing_hypothesis(self):
        with self.assertRaises(ValueError):
            _make_record(hypothesis="")

    def test_rejects_missing_changed_workflow_path(self):
        with self.assertRaises(ValueError):
            _make_record(changed_workflow_path="")

    def test_rejects_unknown_status(self):
        with self.assertRaises(ValueError):
            _make_record(status="maybe")

    def test_rejects_negative_elapsed_seconds(self):
        with self.assertRaises(ValueError):
            _make_record(elapsed_seconds=-1)

    def test_accepts_default_empty_evidence_and_verification(self):
        record = ExperimentRecord(
            name="baseline",
            hypothesis="No change, establish a baseline.",
            changed_workflow_path="Santi Miguel AI Agent (F).json",
            status="passed",
            elapsed_seconds=1.0,
        )
        self.assertEqual(record.evidence, {})
        self.assertEqual(record.verification, {})

    def test_to_json_round_trips_through_read_record(self):
        record = _make_record()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path = write_record(record, directory)
            restored = read_record(path)
        self.assertEqual(restored, record)

    def test_write_record_creates_directory_and_file(self):
        record = _make_record()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "runs"
            self.assertFalse(directory.exists())
            path = write_record(record, directory)
            self.assertTrue(path.exists())
            self.assertEqual(path.parent, directory)

    def test_write_record_file_is_valid_json_with_expected_fields(self):
        record = _make_record()
        with tempfile.TemporaryDirectory() as tmp:
            path = write_record(record, Path(tmp))
            data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["name"], "raise-preflight-threshold")
        self.assertEqual(data["hypothesis"], record.hypothesis)
        self.assertEqual(data["changed_workflow_path"], record.changed_workflow_path)
        self.assertEqual(data["status"], "passed")
        self.assertEqual(data["elapsed_seconds"], 12.5)
        self.assertEqual(data["evidence"], {"preflight_catches": 3})
        self.assertEqual(data["verification"], {"verified": True, "basis": "replayed against wam fixtures"})

    def test_write_record_does_not_collide_with_same_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            first = write_record(_make_record(), directory)
            second = write_record(_make_record(), directory)
            self.assertNotEqual(first, second)
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())


if __name__ == "__main__":
    unittest.main()
