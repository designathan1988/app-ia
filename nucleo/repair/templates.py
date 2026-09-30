"""Repair of a faulty expression by fix templates (TBar-style), checked by tests, never trusted on tests alone.

Templates are the edits real fixes are made of: replace a binary or comparison operator by one of its kind, move an
integer constant by one, swap operands, add or drop a negation, replace a method by a sibling (strip/lstrip/rstrip,
startswith/endswith, find/rfind, lower/upper), replace a variable by another parameter. Candidates are tried from
the fewest edits up; the first that passes every available test is proposed.

The proposal is then judged on inputs the repair never saw (the benchmark's held-out tests): a repair that passes the
visible tests but fails there is counted as overfitted, not as a fix (the GenProg lesson: 2 of 105 "repairs" were
correct).
"""

from __future__ import annotations

import ast
import builtins
import copy
import itertools
from dataclasses import dataclass

from ..synth.tasks import SAFE_BUILTINS

# ** and << are not offered as replacements: they build huge numbers (and burn CPU) far more often than they fix
ARITH = [ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Mod, ast.BitAnd, ast.BitOr, ast.BitXor, ast.RShift, ast.Div]
COMPARE = [ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq]
BOOL = [ast.And, ast.Or]
SIBLING_METHODS = [{"strip", "lstrip", "rstrip"}, {"startswith", "endswith"}, {"find", "rfind", "index", "rindex"},
                   {"lower", "upper", "title", "capitalize", "casefold", "swapcase"}, {"split", "rsplit"},
                   {"removeprefix", "removesuffix"}, {"min", "max"}, {"any", "all"}]


def _edits(tree: ast.AST, params: list[str]):
    """Every single-edit variant of the expression, as new trees."""
    nodes = list(ast.walk(tree))
    for idx, node in enumerate(nodes):
        def variant(change):
            t = copy.deepcopy(tree)
            target = list(ast.walk(t))[idx]
            change(target)
            return t

        if isinstance(node, ast.BinOp):
            for op in ARITH:
                if not isinstance(node.op, op):
                    yield variant(lambda n, op=op: setattr(n, "op", op()))
            yield variant(lambda n: (setattr(n, "left", n.right), setattr(n, "right", n.left)) and None)
        elif isinstance(node, ast.Compare) and len(node.ops) == 1:
            for op in COMPARE:
                if not isinstance(node.ops[0], op):
                    yield variant(lambda n, op=op: setattr(n, "ops", [op()]))
        elif isinstance(node, ast.BoolOp):
            for op in BOOL:
                if not isinstance(node.op, op):
                    yield variant(lambda n, op=op: setattr(n, "op", op()))
        elif isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
            for d in (1, -1):
                yield variant(lambda n, d=d: setattr(n, "value", n.value + d))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.Not, ast.USub, ast.Invert)):
            yield _replace(tree, idx, lambda n: n.operand)
        elif isinstance(node, ast.Name) and node.id in params:
            for p in params:
                if p != node.id:
                    yield variant(lambda n, p=p: setattr(n, "id", p))
        elif isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
            for group in SIBLING_METHODS:
                if name in group:
                    for other in sorted(group - {name}):
                        if isinstance(node.func, ast.Attribute):
                            yield variant(lambda n, o=other: setattr(n.func, "attr", o))
                        else:
                            yield variant(lambda n, o=other: setattr(n.func, "id", o))
        if isinstance(node, (ast.Compare, ast.BoolOp, ast.Call)) and idx > 0:
            yield _replace(tree, idx, lambda n: ast.UnaryOp(ast.Not(), n))


def _replace(tree, idx, make):
    t = copy.deepcopy(tree)
    nodes = list(ast.walk(t))
    old = nodes[idx]
    for parent in nodes:
        for fname, value in ast.iter_fields(parent):
            if value is old:
                setattr(parent, fname, make(old))
                return ast.fix_missing_locations(t)
            if isinstance(value, list) and any(v is old for v in value):
                setattr(parent, fname, [make(v) if v is old else v for v in value])
                return ast.fix_missing_locations(t)
    return make(old)  # the root itself


def _compile(params: list[str], expr: str):
    env = {k: getattr(builtins, k) for k in SAFE_BUILTINS}
    return eval(f"lambda {', '.join(params)}: ({expr})", {"__builtins__": env})  # noqa: S307 - candidate under test


def passes(params: list[str], expr: str, examples: list) -> bool:
    try:
        fn = _compile(params, expr)
    except SyntaxError:
        return False
    for args, out in examples:
        try:
            got = fn(*[list(a) if isinstance(a, list) else a for a in args])
            if repr(got) != repr(out):
                return False
        except Exception:  # noqa: BLE001
            return False
    return True


@dataclass
class Repair:
    source: str | None
    edits: int
    tried: int


def repair(params: list[str], buggy: str, tests: list, max_edits: int = 2, budget: int = 20000) -> Repair:
    tree = ast.parse(buggy, mode="eval")
    frontier = [tree]
    seen = {ast.unparse(tree)}
    tried = 0
    for depth in range(1, max_edits + 1):
        nxt = []
        for t in frontier:
            for cand in _edits(t.body if isinstance(t, ast.Expression) else t, params):
                src = ast.unparse(cand)
                if src in seen:
                    continue
                seen.add(src)
                tried += 1
                if passes(params, src, tests):
                    return Repair(src, depth, tried)
                nxt.append(ast.Expression(cand) if not isinstance(cand, ast.Expression) else cand)
                if tried >= budget:
                    return Repair(None, depth, tried)
        frontier = nxt
    return Repair(None, max_edits, tried)


def mutants(expr: str, params: list[str]):
    """Single-edit faulty versions of a correct expression (the benchmark's injected bugs)."""
    tree = ast.parse(expr, mode="eval").body
    for m in itertools.islice(_edits(tree, params), 400):
        yield ast.unparse(m)
