"""Consistent renaming of a scenario's node names to invented words (generalisation test, plan §7).

Every node name of the fixture is replaced by a pseudo-word. The same
replacement is applied to the selection paths, to the node paths of the diff,
to ``name`` fields of node values, and to node paths inside values (such as
``"@/Page/Hero/Intro"``).

A scenario whose expected document contains a name derived from a fixture
name without being one (for example "Title 2", which the builder derives from
"Title") cannot be renamed consistently from outside, and is reported as not
renameable instead of guessed.
"""

from __future__ import annotations

import copy
import random

from .client import walk

_SYL = ["ka", "lo", "mi", "zu", "te", "ri", "po", "sa", "ne", "vu", "bi", "dro", "fe", "gu", "xa"]


def _word(rng: random.Random, used: set) -> str:
    while True:
        w = "".join(rng.choice(_SYL) for _ in range(rng.randint(2, 3))).capitalize()
        if w not in used:
            used.add(w)
            return w


def _map_path(path: str, m: dict) -> str:
    prefix = "@" if path.startswith("@/") else ""
    body = path[len(prefix):]
    parts = body.split("/")
    out = []
    in_field = False
    for p in parts:
        if p.startswith("@"):
            in_field = True
        out.append(p if in_field else m.get(p, p))
    return prefix + "/".join(out)


def _map_value(v, m: dict, names: set, problems: list):
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            if k == "name" and isinstance(x, str):
                if x in m:
                    out[k] = m[x]
                else:
                    if any(n in x for n in names):
                        problems.append(x)
                    out[k] = x
            else:
                out[k] = _map_value(x, m, names, problems)
        return out
    if isinstance(v, list):
        return [_map_value(x, m, names, problems) for x in v]
    if isinstance(v, str) and (v.startswith("/") or v.startswith("@/")):
        return _map_path(v, m)
    return v


def rename_scenario(fixture: dict | None, selection: list, diff: list, seed: int):
    """(fixture, selection, diff) with every fixture node name replaced, or None if it cannot be done consistently."""
    if fixture is None:
        return None
    rng = random.Random(seed)
    used: set = set()
    fx = copy.deepcopy(fixture)
    m: dict[str, str] = {}
    for page in fx["pages"]:
        for node in walk(page["tree"]):
            if node["name"] not in m:
                m[node["name"]] = _word(rng, used)
            node["name"] = m[node["name"]]
    names = set(m)
    problems: list = []
    new_diff = []
    for op in diff:
        op2 = dict(op)
        op2["path"] = _map_path(op["path"], m)
        if "value" in op:
            op2["value"] = _map_value(op["value"], m, names, problems)
        new_diff.append(op2)
    if problems:
        return None
    return fx, [_map_path(p, m) for p in selection], new_diff
