"""Make N numbered copies of built tasks, so one Valkyrie run can hold every try.

    python3 gen/replicate.py <tasks_dir> <out_dir> <copies> <task> [<task> ...]

Valkyrie gives each task one attempt per run and caps the org at 10 runs at once.
Copies named <task>-r1..rN are identical tasks, so a single run per model with
--concurrency high does all tries in parallel. Prints the comma-separated task ids.
"""

import re
import shutil
import sys
from pathlib import Path

src, out, copies, names = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), sys.argv[4:]
ids = []
for name in names:
    for r in range(1, copies + 1):
        rid = f"{name}-r{r}"
        dst = out / rid
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src / name, dst)
        toml = dst / "task.toml"
        toml.write_text(re.sub(r'name = "yaya/[^"]+"', f'name = "yaya/{rid}"', toml.read_text(), count=1))
        ids.append(rid)
print(",".join(ids))
