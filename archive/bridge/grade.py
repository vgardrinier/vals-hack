"""Grade the final company state against a task's checks.

    python grade.py world.json checks.json [reward.txt]

Prints each check as PASS/FAIL. Reward is 1 only if every check passes.
"""

import json
import sys
from pathlib import Path

import automationbench.rubric.assertions  # noqa: F401  registers the check types
from automationbench.rubric.registry import AssertionRegistry
from automationbench.schema.world import WorldState


def main() -> None:
    world_path, checks_path = Path(sys.argv[1]), Path(sys.argv[2])
    world = WorldState(**json.loads(world_path.read_text()))
    checks = json.loads(checks_path.read_text())
    results = [AssertionRegistry.check(world, c) for c in checks]
    for ok, c in zip(results, checks):
        print("PASS" if ok else "FAIL", json.dumps(c))
    reward = 1 if all(results) else 0
    print(f"reward={reward} ({sum(results)}/{len(results)} checks)")
    if len(sys.argv) > 3:
        Path(sys.argv[3]).write_text(str(reward))


if __name__ == "__main__":
    main()
