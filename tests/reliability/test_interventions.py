import json
import unittest
from pathlib import Path

from shadowdesk.reliability.diagnostics import Diagnosis
from shadowdesk.reliability.interventions import apply_intervention

WORKFLOW_PATH = Path(__file__).resolve().parents[2] / "shadowdesk" / "reliability" / "assets" / "advisor_workflow_redacted.json"


def load_workflow():
    with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def make_diagnosis(intervention_type, params):
    return Diagnosis(
        what_happened="test", why="test", is_problem=True, confidence=1.0,
        intervention_type=intervention_type, intervention_params=params,
        intervention_description="test",
    )


class TestInterventions(unittest.TestCase):
    def setUp(self):
        self.workflow = load_workflow()

    def test_does_not_mutate_input_workflow(self):
        before = json.dumps(self.workflow)
        apply_intervention(self.workflow, make_diagnosis(
            "add_system_prompt_directive", {"directive": "Always double-check tickers."}
        ))
        after = json.dumps(self.workflow)
        self.assertEqual(before, after)

    def test_add_system_prompt_directive_is_idempotent(self):
        r1 = apply_intervention(self.workflow, make_diagnosis(
            "add_system_prompt_directive", {"directive": "Never truncate before the joke block."}
        ))
        self.assertTrue(r1.applied)
        r2 = apply_intervention(r1.workflow, make_diagnosis(
            "add_system_prompt_directive", {"directive": "Never truncate before the joke block."}
        ))
        self.assertFalse(r2.applied)
        self.assertIn("already", r2.description)

    def test_adjust_generation_params_patches_deepseek_node(self):
        result = apply_intervention(self.workflow, make_diagnosis(
            "adjust_generation_params", {"field": "max_tokens", "value": 40000}
        ))
        self.assertTrue(result.applied)
        deepseek = next(n for n in result.workflow["nodes"] if n["name"] == "DeepSeek")
        self.assertIn("max_tokens: 40000", deepseek["parameters"]["jsonBody"])

    def test_adjust_generation_params_rejects_unknown_field(self):
        result = apply_intervention(self.workflow, make_diagnosis(
            "adjust_generation_params", {"field": "not_a_real_param", "value": 1}
        ))
        self.assertFalse(result.applied)

    def test_validator_threshold_patch(self):
        result = apply_intervention(self.workflow, make_diagnosis(
            "tighten_validator_threshold", {"check": "chars_min", "value": 50000}
        ))
        self.assertTrue(result.applied)
        validator = next(n for n in result.workflow["nodes"] if n["name"] == "Validator")
        self.assertIn("chars < 50000", validator["parameters"]["jsCode"])

    def test_enable_preflight_check_inserts_nodes_and_rewires(self):
        result = apply_intervention(self.workflow, make_diagnosis("enable_preflight_check", {}))
        self.assertTrue(result.applied)
        names = {n["name"] for n in result.workflow["nodes"]}
        self.assertIn("Pre-Flight Check", names)
        self.assertIn("Preflight Gate", names)

        conns = result.workflow["connections"]
        rollup_targets = {c["node"] for branch in conns["Analyst desk rollup"]["main"] for c in branch}
        self.assertIn("Pre-Flight Check", rollup_targets)
        self.assertNotIn("Edit Fields", rollup_targets)

        gate_targets = [c["node"] for branch in conns["Preflight Gate"]["main"] for c in branch]
        self.assertIn("Edit Fields", gate_targets)

        # original workflow untouched
        original_rollup_targets = {c["node"] for branch in self.workflow["connections"]["Analyst desk rollup"]["main"] for c in branch}
        self.assertIn("Edit Fields", original_rollup_targets)

    def test_enable_preflight_check_is_idempotent(self):
        r1 = apply_intervention(self.workflow, make_diagnosis("enable_preflight_check", {}))
        r2 = apply_intervention(r1.workflow, make_diagnosis("enable_preflight_check", {}))
        self.assertFalse(r2.applied)

    def test_enable_validator_gate_inserts_and_rewires(self):
        result = apply_intervention(self.workflow, make_diagnosis("enable_validator_gate", {}))
        self.assertTrue(result.applied)
        names = {n["name"] for n in result.workflow["nodes"]}
        self.assertIn("Validator Gate", names)
        self.assertIn("Validator Failed (needs alert wiring)", names)

        conns = result.workflow["connections"]
        validator_targets = {c["node"] for branch in conns["Validator"]["main"] for c in branch}
        self.assertEqual(validator_targets, {"Validator Gate"})

        true_branch = {c["node"] for c in conns["Validator Gate"]["main"][0]}
        self.assertEqual(true_branch, {"strip text1", "Formatting2"})
        false_branch = {c["node"] for c in conns["Validator Gate"]["main"][1]}
        self.assertEqual(false_branch, {"Validator Failed (needs alert wiring)"})

        # original workflow untouched
        original_targets = {c["node"] for branch in self.workflow["connections"]["Validator"]["main"] for c in branch}
        self.assertEqual(original_targets, {"strip text1", "Formatting2"})

    def test_enable_validator_gate_is_idempotent(self):
        r1 = apply_intervention(self.workflow, make_diagnosis("enable_validator_gate", {}))
        r2 = apply_intervention(r1.workflow, make_diagnosis("enable_validator_gate", {}))
        self.assertFalse(r2.applied)

    def test_both_gates_compose(self):
        r1 = apply_intervention(self.workflow, make_diagnosis("enable_preflight_check", {}))
        self.assertTrue(r1.applied)
        r2 = apply_intervention(r1.workflow, make_diagnosis("enable_validator_gate", {}))
        self.assertTrue(r2.applied)
        names = {n["name"] for n in r2.workflow["nodes"]}
        self.assertTrue({"Pre-Flight Check", "Preflight Gate", "Validator Gate"} <= names)

    def test_flag_for_human_review_does_not_change_workflow(self):
        result = apply_intervention(self.workflow, make_diagnosis(
            "flag_for_human_review", {"reason": "not confident"}
        ))
        self.assertFalse(result.applied)
        self.assertIsNone(result.workflow)


if __name__ == "__main__":
    unittest.main()
