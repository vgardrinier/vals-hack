from __future__ import annotations

import json
from pathlib import Path

from challenge12.materialize import (
    BLUEPRINTS_PATH,
    CASES_ROOT,
    CONTEXTS_ROOT,
    materialize_dataset,
)
from generate_harbor_tasks import GENERIC_ACTION_CATALOG, write_task


DATASET_NAME = "implicit-challenge-12"


def main() -> None:
    materialize_dataset()
    blueprints = json.loads(BLUEPRINTS_PATH.read_text(encoding="utf-8"))
    case_paths = sorted(CASES_ROOT.glob("*.json"))
    for case_path in case_paths:
        case = json.loads(case_path.read_text(encoding="utf-8"))
        context_root = CONTEXTS_ROOT / case["id"]
        documents = {
            name: (context_root / name).read_text(encoding="utf-8")
            for name in case["context_files"]
        }
        write_task(
            case,
            "challenge",
            documents,
            GENERIC_ACTION_CATALOG,
            blueprints[case["id"]],
            output_name=DATASET_NAME,
        )
    output = Path(__file__).resolve().parent.parent / "valkyrie_tasks" / DATASET_NAME
    print(f"Generated {len(case_paths)} offline Harbor tasks in {output}.")


if __name__ == "__main__":
    main()
