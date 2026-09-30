"""A probabilistic grammar of Python expressions, learned by counting a real code corpus (no neural model).

For every expression in the corpus, the operator it uses is counted: binary, comparison, boolean and unary
operators, subscripts and slices, builtin calls by name, method calls by name, plain names, and constants by value.
The cost of an operator in the synthesizer is -log2 of its smoothed relative frequency, so what programmers write
often is tried first.

Counts are kept per file, so that a task taken from a file is solved with a prior that has never seen that file
(leave-one-file-out): the prior cannot memorise the answer.
"""

from __future__ import annotations

import ast
import json
import math
import pathlib
from collections import Counter

from .enumerate import OPS

CACHE = pathlib.Path(__file__).resolve().parents[2] / "data" / "cache" / "prior_counts.json"


def _count(tree: ast.AST) -> Counter:
    c: Counter = Counter()
    for n in ast.walk(tree):
        if isinstance(n, ast.BinOp):
            c[type(n.op).__name__] += 1
        elif isinstance(n, ast.Compare):
            for op in n.ops:
                c[type(op).__name__] += 1
        elif isinstance(n, ast.BoolOp):
            c[type(n.op).__name__] += len(n.values) - 1
        elif isinstance(n, ast.UnaryOp):
            c[type(n.op).__name__] += 1
        elif isinstance(n, ast.IfExp):
            c["IfExp"] += 1
        elif isinstance(n, ast.Tuple) and isinstance(n.ctx, ast.Load):
            c["Tuple"] += 1
        elif isinstance(n, ast.Subscript):
            s = n.slice
            if isinstance(s, ast.Slice):
                if s.step is not None and s.lower is None and s.upper is None:
                    c["Reverse"] += 1
                elif s.lower is not None and s.upper is None:
                    c["SliceFrom"] += 1
                elif s.upper is not None and s.lower is None:
                    c["SliceTo"] += 1
            else:
                c["Subscript"] += 1
        elif isinstance(n, ast.Call):
            if isinstance(n.func, ast.Name):
                c[f"call:{n.func.id}"] += 1
            elif isinstance(n.func, ast.Attribute):
                c[f"method:{n.func.attr}"] += 1
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            c["Name"] += 1
        elif isinstance(n, ast.Constant) and isinstance(n.value, (int, str, bool, type(None))):
            v = n.value
            if isinstance(v, str) and len(v) > 12:
                continue
            c[f"const:{json.dumps(v)}"] += 1
    return c


def count_corpus(files: list[pathlib.Path]) -> dict[str, dict]:
    out = {}
    for p in files:
        try:
            out[str(p)] = dict(_count(ast.parse(p.read_text(encoding="utf-8", errors="replace"))))
        except (SyntaxError, ValueError):
            continue
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(out), encoding="utf-8")
    return out


class Prior:
    def __init__(self, per_file: dict[str, dict], exclude: str | None = None) -> None:
        total: Counter = Counter()
        for f, c in per_file.items():
            if f != exclude:
                total.update(c)
        names = [op.name for op in OPS] + ["Name"]
        op_total = sum(total[n] for n in names) + len(names)
        self._op = {n: -math.log2((total[n] + 1) / op_total) for n in names}
        consts = {k: v for k, v in total.items() if k.startswith("const:")}
        c_total = sum(consts.values()) + 1000
        self._const = {k: -math.log2((v + 1) / c_total) for k, v in consts.items()}
        self._const_default = -math.log2(1 / c_total)
        self.top_constants = [json.loads(k[6:]) for k, _ in sorted(consts.items(), key=lambda x: -x[1])[:40]]

    def cost(self, name: str) -> float:
        return self._op.get(name, 20.0)

    def const_cost(self, value) -> float:
        return self._const.get(f"const:{json.dumps(value)}", self._const_default)


def load_counts() -> dict[str, dict]:
    return json.loads(CACHE.read_text(encoding="utf-8"))
