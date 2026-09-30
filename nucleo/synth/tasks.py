"""Synthesis tasks from real code: small pure functions of local Python code, with their bodies deleted.

For every function whose body is a single ``return <expression>`` over its own parameters and builtins, the original
is run on generated inputs to obtain input/output examples; the oracle is therefore the function itself, not a
hand-written answer. A task keeps the signature, a few training examples and many held-out inputs; the body is only
used to run the oracle.

Inputs are typed by trial: each parameter tries a small set of value kinds (int, str, list[int], list[str]), and the
kinds kept are those for which the original runs without error and produces varied outputs.
"""

from __future__ import annotations

import ast
import builtins
import itertools
import pathlib
import random
import sysconfig
from dataclasses import dataclass, field

SAFE_BUILTINS = {"len", "sum", "min", "max", "abs", "sorted", "reversed", "str", "int", "list", "set", "tuple", "any",
                 "all", "round", "ord", "chr", "bool", "range", "enumerate", "zip", "map", "filter", "isinstance",
                 "float", "dict", "divmod", "pow", "repr", "hex", "bin", "oct"}
KINDS = ("int", "str", "list_int", "list_str")


@dataclass
class Task:
    name: str
    source: str  # file it came from (excluded from the prior when solving it)
    params: list[str]
    kinds: tuple
    body: str  # the deleted expression (only for reporting; never shown to the synthesizer)
    size: int
    train: list = field(default_factory=list)  # [(args, output)]
    test: list = field(default_factory=list)


def _value(kind: str, rng: random.Random, hints: tuple = ((), ())):
    """A random input of a kind. `hints` are the constants of the original body (test side only): strings are
    built around them and ints near them, so the inputs exercise what the function does."""
    str_hints, int_hints = hints
    if kind == "int":
        base = [0, 1, 2, 3, 5, 7, 10, -1, -4, 12, 25, 100]
        near = [h + d for h in int_hints for d in (-1, 0, 1)]
        return rng.choice(base + near * 2) if near else rng.choice(base)
    if kind == "str":
        pool = ["", "a", "abc", "Hello", "hello world", "x-y-z", "  pad  ", "ABC def", "banana", "a,b,c", "42",
                "Mixed Case", "tab\tsep", "snake_case_name", "a  b   c", "UPPER-lower_mix"]
        s = rng.choice(pool)
        if str_hints and rng.random() < 0.6:
            h = rng.choice(str_hints)
            where = rng.random()
            s = h + s if where < 0.33 else s + h if where < 0.66 else s[: len(s) // 2] + h + s[len(s) // 2:]
        return s
    if kind == "list_int":
        return [rng.choice([0, 1, 2, 3, 5, -2, 8, 13]) for _ in range(rng.randint(0, 6))]
    return [rng.choice(["a", "bb", "", "ccc", "Dd", "e f"]) for _ in range(rng.randint(0, 5))]


def _size(node: ast.AST) -> int:
    return sum(1 for _ in ast.walk(node))


def _pure(expr: ast.AST, params: set) -> bool:
    for n in ast.walk(expr):
        if isinstance(n, ast.Name) and n.id not in params and n.id not in SAFE_BUILTINS:
            return False
        if isinstance(n, (ast.Lambda, ast.Await, ast.Yield, ast.YieldFrom, ast.NamedExpr, ast.Starred)):
            return False
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id not in params:
            return False
    return True


def candidates(files: list[pathlib.Path], max_size: int = 14):
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.decorator_list:
                continue
            a = node.args
            if a.vararg or a.kwarg or a.kwonlyargs or a.posonlyargs or a.defaults or not (1 <= len(a.args) <= 3):
                continue
            params = [x.arg for x in a.args]
            if params[0] in ("self", "cls"):
                continue
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
                body = body[1:]
            if len(body) != 1 or not isinstance(body[0], ast.Return) or body[0].value is None:
                continue
            expr = body[0].value
            if _size(expr) > max_size or not _pure(expr, set(params)):
                continue
            yield node.name, str(path), params, ast.unparse(expr), _size(expr)


def _run(fn, args):
    try:
        out = fn(*[list(x) if isinstance(x, list) else x for x in args])
    except Exception:  # noqa: BLE001
        return ("erro",)
    if isinstance(out, (map, filter, zip, reversed, range, enumerate)) or hasattr(out, "__next__"):
        return ("iterador",)
    return ("ok", out)


def _hints(body: str) -> tuple:
    strs, ints = set(), set()
    for n in ast.walk(ast.parse(body, mode="eval")):
        if isinstance(n, ast.Constant):
            if isinstance(n.value, str) and 0 < len(n.value) <= 20:
                strs.add(n.value)
            elif isinstance(n.value, int) and not isinstance(n.value, bool) and abs(n.value) < 10**6:
                ints.add(n.value)
    return tuple(sorted(strs)), tuple(sorted(ints))


def make_task(name, source, params, body, size, seed=0, n_train=6, n_test=30) -> Task | None:
    env = {k: getattr(builtins, k) for k in SAFE_BUILTINS}
    try:
        fn = eval(f"lambda {', '.join(params)}: ({body})", {"__builtins__": env})  # noqa: S307 - the corpus's own code
    except SyntaxError:
        return None
    rng = random.Random(seed)
    hints = _hints(body)
    for kinds in itertools.product(KINDS, repeat=len(params)):
        rows = []
        for _ in range(90):
            args = tuple(_value(k, rng, hints) for k in kinds)
            r = _run(fn, args)
            if r[0] == "ok":
                rows.append((args, r[1]))
        outs = {repr(o) for _, o in rows}
        if len(rows) >= 40 and len(outs) >= 3:
            uniq = list({repr(a): (a, o) for a, o in rows}.values())
            if len(uniq) < n_train + 5:
                continue
            rng.shuffle(uniq)
            task = Task(name, source, params, kinds, body, size, uniq[:n_train], uniq[n_train:n_train + n_test])
            return task if discriminating(task) else None
    return None


def discriminating(task: Task) -> bool:
    """A task whose held-out tests a trivial program already passes (returning a parameter unchanged, or one
    constant) cannot tell a real reconstruction from a trivial one: it is dropped."""
    outs = [repr(o) for _, o in task.test]
    if len(set(outs)) == 1:
        return False
    for i in range(len(task.params)):
        if all(repr(a[i]) == o for (a, _), o in zip(task.test, outs)):
            return False
    return True


def corpus_files() -> list[pathlib.Path]:
    lib = pathlib.Path(sysconfig.get_paths()["stdlib"])
    site = pathlib.Path(sysconfig.get_paths()["purelib"])
    files = sorted(p for p in lib.rglob("*.py") if "test" not in p.parts and "idlelib" not in p.parts)
    files += sorted(site.rglob("*.py"))
    return files


def build_tasks(limit: int | None = None) -> list[Task]:
    seen = set()
    tasks = []
    for name, source, params, body, size in candidates(corpus_files()):
        key = (tuple(params), body)
        if key in seen:
            continue
        seen.add(key)
        t = make_task(name, source, params, body, size)
        if t is not None:
            tasks.append(t)
            if limit and len(tasks) >= limit:
                break
    return tasks
