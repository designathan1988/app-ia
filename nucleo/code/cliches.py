"""Repeated code (clichés): fragments with the same shape up to names and constants, ranked by what factoring them
out would save (MDL: occurrences x size - one shared definition).

The shapes come from the TypeScript parser (``bridge/code/ts_shapes.mjs``). A fragment contained in a larger
repeated fragment with the same occurrences is not reported again. This is the syntactic first step the plan names
for clichés (Stitch-style compression before plan recognition).
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
from collections import defaultdict
from dataclasses import dataclass

from ..builder.client import DEFAULT_BUILDER

ROOT = pathlib.Path(__file__).resolve().parents[2]


@dataclass
class Cliche:
    size: int
    places: list  # [(file, line)]
    example: str

    @property
    def saving(self) -> int:
        return (len(self.places) - 1) * self.size


def find(project: str = DEFAULT_BUILDER, tsconfig: str = "tsconfig.app.json", min_nodes: int = 25,
         min_count: int = 3) -> list[Cliche]:
    env = {**os.environ}
    env.setdefault("NUCLEO_TS", DEFAULT_BUILDER)
    out = subprocess.run(["node", str(ROOT / "bridge" / "code" / "ts_shapes.mjs"), project, tsconfig, str(min_nodes)],
                         capture_output=True, text=True, encoding="utf-8", check=True, env=env).stdout
    groups: dict[str, list] = defaultdict(list)
    sizes: dict[str, int] = {}
    for line in out.splitlines():
        r = json.loads(line)
        groups[r["shape"]].append((r["file"], r["line"], r["text"]))
        sizes[r["shape"]] = r["size"]
    found = []
    for shape, occ in groups.items():
        places = sorted({(f, ln) for f, ln, _ in occ})
        if len(places) >= min_count:
            found.append(Cliche(sizes[shape], places, occ[0][2]))
    found.sort(key=lambda c: -c.saving)
    # drop a fragment whose occurrences all sit on lines a larger reported fragment already covers
    kept, covered = [], set()
    for c in found:
        if sum(p in covered for p in c.places) >= 0.8 * len(c.places):
            continue  # mostly the same occurrences as a larger fragment already reported (e.g. its inner arrow)
        kept.append(c)
        covered.update(c.places)
    return kept
