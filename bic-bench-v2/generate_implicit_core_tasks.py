from __future__ import annotations

from generate_harbor_tasks import (
    GENERIC_ACTION_CATALOG,
    IMPLICIT_CORE5,
    current_documents,
    load_cases,
    load_harbor_blueprints,
    write_task,
)


DATASET_NAME = "implicit-core-5"


def main() -> None:
    cases = load_cases()
    blueprints = load_harbor_blueprints()
    for case_id in IMPLICIT_CORE5:
        case = cases[case_id]
        write_task(
            case,
            "core",
            current_documents(case),
            GENERIC_ACTION_CATALOG,
            blueprints[case_id],
            output_name=DATASET_NAME,
        )
    print(f"Generated {len(IMPLICIT_CORE5)} offline Harbor tasks in {DATASET_NAME}.")


if __name__ == "__main__":
    main()
