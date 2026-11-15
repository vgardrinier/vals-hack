from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_CASE_FIELDS = {
    "id",
    "title",
    "industry",
    "company",
    "category",
    "difficulty",
    "action_type",
    "context_files",
    "task",
    "implicit_constraints",
    "expected_behavior",
    "failure_criteria",
    "scoring_blueprint",
}


def load_case(case_path: Path, contexts_root: Path) -> dict[str, Any]:
    case = json.loads(case_path.read_text(encoding="utf-8"))
    missing = REQUIRED_CASE_FIELDS - case.keys()
    if missing:
        raise ValueError(f"{case_path}: missing fields {sorted(missing)}")
    case_context_dir = contexts_root / case["id"]
    documents = []
    for name in case["context_files"]:
        document_path = case_context_dir / name
        if not document_path.is_file():
            raise FileNotFoundError(f"{case['id']}: missing context {document_path}")
        documents.append({"name": name, "content": document_path.read_text(encoding="utf-8")})
    case["_documents"] = documents
    return case


def load_cases(
    cases_root: Path,
    contexts_root: Path,
    selected_ids: set[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    paths = sorted(cases_root.glob("*.json"))
    if selected_ids:
        paths = [path for path in paths if path.stem in selected_ids]
        found = {path.stem for path in paths}
        missing = selected_ids - found
        if missing:
            raise ValueError(f"unknown case IDs: {sorted(missing)}")
    if limit is not None:
        paths = paths[:limit]
    return [load_case(path, contexts_root) for path in paths]
