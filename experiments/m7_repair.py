"""M7: repair injected bugs in real functions, judged on inputs the repair never saw.

For each synthesis task (a real small function of the local standard library or packages, with its hygiene: tests
that tell it apart from trivial programs), up to K single-edit mutants are made; a mutant counts as a bug when it
fails at least one of the 6 visible tests. The repair sees only the buggy expression and the visible tests.
- correct: the repair agrees with the original on all 30 held-out inputs;
- overfitted: it passes the visible tests but not the held-out ones;
- not repaired: nothing within two edits passes the visible tests.

Usage: python experiments/m7_repair.py [bugs-per-task] [every-kth-task]
"""
from __future__ import annotations

import collections
import pathlib
import random
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import ast  # noqa: E402
import copy  # noqa: E402

from nucleo.repair.templates import mutants, passes, repair  # noqa: E402
from nucleo.session import low_priority  # noqa: E402
from nucleo.synth.tasks import build_tasks  # noqa: E402

UNRELATED = {"strip": "title", "lower": "strip", "upper": "strip", "startswith": "count", "endswith": "find",
             "split": "partition", "replace": "replace", "find": "count", "join": "join"}


def foreign_mutants(expr: str):
    """Bugs of kinds the repair templates do not cover: a constant off by 2..5, a call dropped (its argument or
    receiver kept), a method replaced by an unrelated one, an operand replaced by a constant."""
    tree = ast.parse(expr, mode="eval").body
    nodes = list(ast.walk(tree))
    for idx, n in enumerate(nodes):
        def variant(change):
            t = copy.deepcopy(tree)
            target = list(ast.walk(t))[idx]
            r = change(target, t)
            return ast.unparse(r if r is not None else t)
        if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool):
            for d in (2, -2, 3, 5):
                yield variant(lambda x, t, d=d: setattr(x, "value", x.value + d))
        if isinstance(n, ast.Call) and idx == 0:
            inner = n.args[0] if n.args else (n.func.value if isinstance(n.func, ast.Attribute) else None)
            if inner is not None:
                yield ast.unparse(inner)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in UNRELATED                 and UNRELATED[n.func.attr] != n.func.attr:
            yield variant(lambda x, t: setattr(x.func, "attr", UNRELATED[x.func.attr]))
        if isinstance(n, ast.BinOp) and isinstance(n.right, ast.Name):
            yield variant(lambda x, t: setattr(x, "right", ast.Constant(1)))


if __name__ == "__main__" and "--fora" in sys.argv:
    low_priority()
    tasks = build_tasks()[::2]
    c = collections.Counter()
    for t in tasks:
        bugs = [m for m in dict.fromkeys(foreign_mutants(t.body)) if m != t.body and not passes(t.params, m, t.train)]
        for bug in bugs[:2]:
            c["defeitos"] += 1
            r = repair(t.params, bug, t.train)
            c["não reparado" if r.source is None else "correto" if passes(t.params, r.source, t.test)
              else "sobreajustado"] += 1
    n = max(c["defeitos"], 1)
    print(f"defeitos FORA dos templates: {dict(c)}; corretos {c['correto'] / n:.1%}; "
          f"sobreajustados {c['sobreajustado'] / n:.1%}")
    sys.exit(0)

if __name__ == "__main__":
    low_priority()
    per = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    every = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    tasks = build_tasks()[::every]
    rng = random.Random(0)
    c = collections.Counter()
    samples = []
    t0 = time.time()
    for t in tasks:
        bugs = [m for m in mutants(t.body, t.params) if not passes(t.params, m, t.train)]
        rng.shuffle(bugs)
        for bug in bugs[:per]:
            c["defeitos"] += 1
            r = repair(t.params, bug, t.train)
            if r.source is None:
                c["não reparado"] += 1
            elif passes(t.params, r.source, t.test):
                c["correto"] += 1
                if len(samples) < 8:
                    samples.append((t.body, bug, r.source))
            else:
                c["sobreajustado"] += 1
    n = max(c["defeitos"], 1)
    print(f"{c['defeitos']} defeitos em {len(tasks)} funções, {time.time() - t0:.0f}s: {dict(c)}")
    print(f"corretos {c['correto'] / n:.1%}; sobreajustados {c['sobreajustado'] / n:.1%} "
          f"(entre os propostos: {c['sobreajustado'] / max(c['correto'] + c['sobreajustado'], 1):.1%})")
    for orig, bug, fix in samples:
        print(f"  original: {orig[:50]:50s} | defeito: {bug[:45]:45s} | reparo: {fix[:45]}")
