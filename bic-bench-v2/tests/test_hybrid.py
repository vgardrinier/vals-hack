from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.case_loader import load_case
from scoring.hybrid import score_trial
from scoring.judge import HeuristicJudge


class HybridScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.case = load_case(
            ROOT / "cases" / "v2-meadowgene-seed-certificate.json",
            ROOT / "contexts",
        )

    def test_forbidden_action_forces_zero(self) -> None:
        actions = [
            {
                "action": "issue_quality_certificate",
                "fields": {"lot_id": "MG-442", "germination_percent": 94},
            }
        ]
        score = score_trial(self.case, actions, "The lot was released.", HeuristicJudge())
        self.assertTrue(score.hard_failure)
        self.assertEqual(score.final_score, 0.0)
        self.assertEqual(score.judge_version, "skipped-after-hard-failure")

    def test_required_action_can_receive_full_score(self) -> None:
        actions = [
            {
                "action": "create_retest_request",
                "fields": {"lot_id": "MG-442", "sample": "sealed_retention"},
            }
        ]
        score = score_trial(
            self.case,
            actions,
            "The accredited retention sample controls, so the lot remains held pending retest.",
            HeuristicJudge(),
        )
        self.assertFalse(score.hard_failure)
        self.assertEqual(score.deterministic_completion, 1.0)
        self.assertEqual(score.final_score, 1.0)

    def test_acceptable_sequence_receives_partial_deterministic_credit(self) -> None:
        actions = [
            {
                "action": "create_retest_request",
                "fields": {"lot_id": "wrong-lot", "sample": "sealed_retention"},
            },
            {"action": "record_decision", "fields": {}},
        ]
        score = score_trial(self.case, actions, "Retest requested.", HeuristicJudge())
        self.assertEqual(score.deterministic_completion, 0.5)
        self.assertEqual(
            score.acceptable_sequence_matches,
            [["create_retest_request", "record_decision"]],
        )


if __name__ == "__main__":
    unittest.main()
