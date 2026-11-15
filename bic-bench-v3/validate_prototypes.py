from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
PROTOTYPES_ROOT = ROOT / "prototypes"
DOC_ID_PATTERN = re.compile(r"^dsid_[0-9a-f]{32}$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: expected a JSON object")
    return value


def main() -> None:
    index = load_json(PROTOTYPES_ROOT / "index.json")
    files = [PROTOTYPES_ROOT / name for name in index["prototype_files"]]
    require(len(files) == 4, f"expected four prototypes, found {len(files)}")
    require(not index["harbor_generated"], "review gate must not contain Harbor tasks")
    require(not index["valkyrie_uploaded"], "review gate must not be uploaded")
    require(not index["model_runs_started"], "review gate must not start model runs")

    seen_ids: set[str] = set()
    anchor_ids: set[str] = set()
    for path in files:
        task = load_json(path)
        task_id = task["id"]
        require(task_id not in seen_ids, f"duplicate task id: {task_id}")
        seen_ids.add(task_id)
        require(task["status"] == "prototype", f"{task_id}: invalid status")
        require(
            task["ambiguity"]["two_defensible_actions"] is True,
            f"{task_id}: ambiguity requirement missing",
        )

        context = task["context_plan"]
        require(
            120 <= context["authentic_documents_target"] <= 250,
            f"{task_id}: authentic context target out of range",
        )
        require(
            2 <= len(context["overlay_documents"]) <= 5,
            f"{task_id}: expected two to five overlay documents",
        )
        anchors = task["anchor_documents"]
        require(len(anchors) >= 2, f"{task_id}: needs at least two source anchors")
        systems = {anchor["source_type"] for anchor in anchors}
        systems.update(item["source_type"] for item in context["overlay_documents"])
        require(len(systems) >= 3, f"{task_id}: needs at least three source systems")

        for anchor in anchors:
            doc_id = anchor["doc_id"]
            require(DOC_ID_PATTERN.fullmatch(doc_id) is not None, f"invalid doc id: {doc_id}")
            require(doc_id not in anchor_ids, f"anchor reused across prototypes: {doc_id}")
            anchor_ids.add(doc_id)
            require(anchor["decision_fact"].strip(), f"{task_id}: empty decision fact")

        constraint = task["implicit_constraint"]
        require(
            len(constraint["inference_hops"]) >= 4,
            f"{task_id}: needs at least four inference hops",
        )
        require(
            constraint["no_single_document_reason"].strip(),
            f"{task_id}: missing split-constraint rationale",
        )
        assertions = task["deterministic_assertions"]
        require(assertions["forbidden"], f"{task_id}: missing forbidden assertion")
        require(assertions["required"], f"{task_id}: missing required assertion")

    print(
        f"Validated {len(files)} corpus-grounded prototypes, "
        f"{len(anchor_ids)} unique source anchors, and "
        f"{sum(len(load_json(path)['context_plan']['overlay_documents']) for path in files)} overlays."
    )


if __name__ == "__main__":
    main()
