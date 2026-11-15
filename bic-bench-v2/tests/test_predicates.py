from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scoring.predicates import action_matches


class PredicateTests(unittest.TestCase):
    def test_supported_operators(self) -> None:
        action = {
            "action": "publish",
            "fields": {
                "body": "Neutral operational update",
                "recipients": ["Security", "Enterprise Risk"],
                "lux": 35,
                "status": "pending",
            },
        }
        assertion = {
            "action": "publish",
            "fields": {
                "body": {"contains": "operational", "excludes_any": ["breach", "attack"]},
                "recipients": {"contains_all": ["Security", "Enterprise Risk"]},
                "lux": {"at_most": 35, "greater_than": 20},
                "status": {"not_equals": "approved"},
            },
        }
        self.assertTrue(action_matches(action, assertion))

    def test_missing_field_does_not_match(self) -> None:
        self.assertFalse(
            action_matches(
                {"action": "release", "fields": {}},
                {"action": "release", "fields": {"lot_id": {"equals": "A-1"}}},
            )
        )


if __name__ == "__main__":
    unittest.main()
