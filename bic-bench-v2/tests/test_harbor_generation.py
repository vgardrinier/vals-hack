from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from generate_harbor_tasks import (
    GENERIC_ACTION_CATALOG,
    HARD10,
    IMPLICIT_CORE5,
    load_harbor_blueprints,
    materialize,
)


def load_harbor_scorer():
    spec = importlib.util.spec_from_file_location(
        "harbor_scorer", ROOT / "harbor" / "scorer.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class HarborGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.blueprints = load_harbor_blueprints()
        cls.scorer = load_harbor_scorer()

    def test_before_and_after_packages_are_offline(self) -> None:
        for variant in ("before", "after"):
            root = REPOSITORY_ROOT / "valkyrie_tasks" / f"hard10-{variant}"
            self.assertEqual(len(list(root.glob("*/task.toml"))), len(HARD10))
            for task_toml in root.glob("*/task.toml"):
                contents = task_toml.read_text(encoding="utf-8")
                self.assertIn("allow_internet = false", contents)
                self.assertNotIn("allow_internet = true", contents)

    def test_implicit_core_package_is_small_and_offline(self) -> None:
        root = REPOSITORY_ROOT / "valkyrie_tasks" / "implicit-core-5"
        tasks = list(root.glob("*/task.toml"))
        self.assertEqual(len(tasks), len(IMPLICIT_CORE5))
        self.assertEqual({path.parent.name for path in tasks}, set(IMPLICIT_CORE5))
        for task_toml in tasks:
            contents = task_toml.read_text(encoding="utf-8")
            self.assertIn("allow_internet = false", contents)
            self.assertNotIn("allow_internet = true", contents)

    def test_reference_actions_receive_full_reward(self) -> None:
        for case_id, blueprint in self.blueprints.items():
            with self.subTest(case_id=case_id):
                actions = []
                assertions = list(blueprint["required"])
                assertions.extend(
                    group[0] for group in blueprint.get("required_any", [])
                )
                for assertion in assertions:
                    actions.append(
                        {
                            "action": assertion["action"],
                            "fields": {
                                key: materialize(rule)
                                for key, rule in assertion.get("fields", {}).items()
                            },
                        }
                    )
                result = self._score(case_id, blueprint, actions)
                self.assertEqual(result["reward"], 1.0)

    def test_forbidden_action_forces_zero(self) -> None:
        for case_id, blueprint in self.blueprints.items():
            with self.subTest(case_id=case_id):
                assertion = blueprint["forbidden"][0]
                action = {
                    "action": assertion["action"],
                    "fields": {
                        key: materialize(rule)
                        for key, rule in assertion.get("fields", {}).items()
                    },
                }
                result = self._score(case_id, blueprint, [action])
                self.assertEqual(result["reward"], 0.0)
                self.assertEqual(result["failure_type"], "forbidden_action")

    def test_catalog_uses_only_neutral_action_names(self) -> None:
        self.assertEqual(
            set(GENERIC_ACTION_CATALOG),
            {
                "communicate",
                "configure_system",
                "create_work_item",
                "dispatch_operation",
                "draft_artifact",
                "execute_operation",
                "request_review",
                "schedule_event",
                "stage_artifact",
                "update_record",
            },
        )
        self.assertNotIn("request_beneficiary_verification", GENERIC_ACTION_CATALOG)
        self.assertNotIn("remediate_backup_residency", GENERIC_ACTION_CATALOG)

    def test_negated_completion_does_not_trip_hard_gate(self) -> None:
        case_id = "v2-cloudnest-residency-close"
        blueprint = self.blueprints[case_id]
        result = self._score(
            case_id,
            blueprint,
            [
                {
                    "action": "update_record",
                    "fields": {
                        "subject_id": "CN-EU44",
                        "field": "migration_status",
                        "value": "Not Complete - pending",
                    },
                }
            ],
        )
        self.assertNotEqual(result["failure_type"], "forbidden_action")

    def test_observable_fields_accept_natural_formatting(self) -> None:
        self.assertTrue(
            self.scorer.value_matches(
                "milestone_4_technical_completion",
                {"contains": "technical completion"},
            )
        )
        self.assertTrue(
            self.scorer.value_matches(
                "America/Los_Angeles (PT) = 10:00 ET",
                {"contains": "America/Los_Angeles"},
            )
        )

    def _score(
        self,
        case_id: str,
        blueprint: dict,
        actions: list[dict],
    ) -> dict:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = root / "expected.json"
            action_log = root / "actions.jsonl"
            expected.write_text(
                json.dumps(
                    {"id": case_id, "scoring_blueprint": blueprint}
                ),
                encoding="utf-8",
            )
            action_log.write_text(
                "".join(json.dumps(action) + "\n" for action in actions),
                encoding="utf-8",
            )
            return self.scorer.score_files(expected, action_log)


if __name__ == "__main__":
    unittest.main()
