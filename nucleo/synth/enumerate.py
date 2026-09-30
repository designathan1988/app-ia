"""Bottom-up enumerative synthesis of Python expressions from input/output examples.

* **Search.** Programs are built from smaller ones in order of cost (Dijkstra over a bank of expressions). Two
  expressions that give the same values on every example are the same for the search (observational equivalence),
  and only the cheaper is kept. That is what keeps the space finite.
* **Values, not text.** Every expression carries its vector of values on the examples, computed by applying the
  operator to its children's vectors. An expression is never re-run from its source.
* **Prior.** The cost of an operator is -log2 of its frequency in a real code corpus (a PCFG learned by counting;
  `prior.py`), with the task's own file left out. Without a prior, every operator costs the same (the ablation).
* **Types.** Operators apply only to values of the kinds they accept; an operator that raises on some example makes
  that candidate invalid, not the search.

The result is the cheapest expression matching every training example, then checked on held-out inputs.
"""

from __future__ import annotations

import heapq
import itertools
import math
import time
from dataclasses import dataclass

ERR = object()


@dataclass(frozen=True)
class Op:
    name: str  # also the key in the prior
    arity: int
    fn: object
    show: object  # (child strings) -> source


def _b(f):
    def g(*xs):
        try:
            return f(*xs)
        except Exception:  # noqa: BLE001
            return ERR
    return g


def _guard_int(f):
    def g(a, b):
        if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, int) or not isinstance(b, int):
            return ERR
        if abs(a) > 10**12 or abs(b) > 10**6:
            return ERR
        return f(a, b)
    return g


def _pow(a, b):
    if not isinstance(a, int) or not isinstance(b, int) or b < 0 or b > 64 or abs(a) > 10**6:
        return ERR
    return a ** b


def _shift(a, b):
    if not isinstance(a, int) or not isinstance(b, int) or b < 0 or b > 64:
        return ERR
    return a << b


def _mul(a, b):
    if isinstance(a, (str, list)) and isinstance(b, int) and b > 50:
        return ERR
    if isinstance(b, (str, list)) and isinstance(a, int) and a > 50:
        return ERR
    return a * b


OPS = [
    Op("Add", 2, _b(lambda a, b: a + b), lambda a, b: f"({a} + {b})"),
    Op("Sub", 2, _b(lambda a, b: a - b), lambda a, b: f"({a} - {b})"),
    Op("Mult", 2, _b(_mul), lambda a, b: f"({a} * {b})"),
    Op("FloorDiv", 2, _b(_guard_int(lambda a, b: a // b)), lambda a, b: f"({a} // {b})"),
    Op("Mod", 2, _b(_guard_int(lambda a, b: a % b)), lambda a, b: f"({a} % {b})"),
    Op("Pow", 2, _b(_pow), lambda a, b: f"({a} ** {b})"),
    Op("BitAnd", 2, _b(_guard_int(lambda a, b: a & b)), lambda a, b: f"({a} & {b})"),
    Op("BitOr", 2, _b(_guard_int(lambda a, b: a | b)), lambda a, b: f"({a} | {b})"),
    Op("BitXor", 2, _b(_guard_int(lambda a, b: a ^ b)), lambda a, b: f"({a} ^ {b})"),
    Op("LShift", 2, _b(_shift), lambda a, b: f"({a} << {b})"),
    Op("RShift", 2, _b(_guard_int(lambda a, b: a >> b if b >= 0 else ERR)), lambda a, b: f"({a} >> {b})"),
    Op("Lt", 2, _b(lambda a, b: a < b), lambda a, b: f"({a} < {b})"),
    Op("LtE", 2, _b(lambda a, b: a <= b), lambda a, b: f"({a} <= {b})"),
    Op("Eq", 2, _b(lambda a, b: a == b), lambda a, b: f"({a} == {b})"),
    Op("NotEq", 2, _b(lambda a, b: a != b), lambda a, b: f"({a} != {b})"),
    Op("In", 2, _b(lambda a, b: a in b), lambda a, b: f"({a} in {b})"),
    Op("And", 2, _b(lambda a, b: a and b), lambda a, b: f"({a} and {b})"),
    Op("Or", 2, _b(lambda a, b: a or b), lambda a, b: f"({a} or {b})"),
    Op("USub", 1, _b(lambda a: -a if not isinstance(a, bool) else ERR), lambda a: f"(-{a})"),
    Op("Invert", 1, _b(lambda a: ~a if isinstance(a, int) and not isinstance(a, bool) else ERR), lambda a: f"(~{a})"),
    Op("Not", 1, _b(lambda a: not a), lambda a: f"(not {a})"),
    Op("UAdd", 1, _b(lambda a: +a if isinstance(a, int) and not isinstance(a, bool) else ERR), lambda a: f"(+{a})"),
    Op("Subscript", 2, _b(lambda a, i: a[i] if isinstance(a, (str, list, tuple)) and isinstance(i, int) else ERR),
       lambda a, i: f"{a}[{i}]"),
    Op("SliceFrom", 2, _b(lambda a, i: a[i:] if isinstance(a, (str, list)) and isinstance(i, int) else ERR),
       lambda a, i: f"{a}[{i}:]"),
    Op("SliceTo", 2, _b(lambda a, i: a[:i] if isinstance(a, (str, list)) and isinstance(i, int) else ERR),
       lambda a, i: f"{a}[:{i}]"),
    Op("Reverse", 1, _b(lambda a: a[::-1] if isinstance(a, (str, list)) else ERR), lambda a: f"{a}[::-1]"),
    Op("Tuple", 2, _b(lambda a, b: (a, b)), lambda a, b: f"({a}, {b})"),
    Op("IfExp", 3, _b(lambda c, a, b: a if c else b), lambda c, a, b: f"({a} if {c} else {b})"),
]
for fname, f in [("len", len), ("abs", abs), ("str", str), ("int", int), ("sorted", sorted), ("sum", sum),
                 ("min", min), ("max", max), ("bool", bool), ("list", list), ("set", set), ("tuple", tuple),
                 ("ord", ord), ("chr", chr), ("repr", repr), ("hex", hex), ("bin", bin), ("round", round),
                 ("float", float), ("any", any), ("all", all)]:
    OPS.append(Op(f"call:{fname}", 1, _b(f), (lambda n: lambda a: f"{n}({a})")(fname)))
for fname, f in [("min", min), ("max", max), ("divmod", divmod), ("round", round)]:
    OPS.append(Op(f"call:{fname}", 2, _b(f), (lambda n: lambda a, b: f"{n}({a}, {b})")(fname)))
_STR_METHODS0 = ["upper", "lower", "strip", "lstrip", "rstrip", "title", "capitalize", "swapcase", "split",
                 "isdigit", "isalpha", "isupper", "islower", "isspace", "casefold"]
_STR_METHODS1 = ["split", "join", "startswith", "endswith", "count", "find", "index", "zfill", "strip", "rstrip",
                 "lstrip", "center", "ljust", "rjust", "partition", "rpartition", "rfind"]
_STR_METHODS2 = ["replace"]


def _meth(name, arity):
    def f(obj, *args):
        if not isinstance(obj, (str, int)) or isinstance(obj, bool):
            return ERR
        m = getattr(obj, name, None)
        if m is None:
            return ERR
        if name in ("zfill", "center", "ljust", "rjust") and args and isinstance(args[0], int) and args[0] > 200:
            return ERR
        return m(*args)
    return _b(f)


for m in _STR_METHODS0 + ["bit_length", "bit_count"]:
    OPS.append(Op(f"method:{m}", 1, _meth(m, 0), (lambda n: lambda a: f"{a}.{n}()")(m)))
for m in _STR_METHODS1:
    OPS.append(Op(f"method:{m}", 2, _meth(m, 1), (lambda n: lambda a, b: f"{a}.{n}({b})")(m)))
for m in _STR_METHODS2:
    OPS.append(Op(f"method:{m}", 3, _meth(m, 2), (lambda n: lambda a, b, c: f"{a}.{n}({b}, {c})")(m)))

DEFAULT_CONSTANTS = [0, 1, 2, -1, 3, 8, 10, 16, 32, 255, "", " ", ",", "-", "_", ".", "/", "\n", "\\", '"', True,
                     False, None]


def _key(vals: tuple) -> str:
    return repr(vals)


@dataclass
class Result:
    source: str | None
    cost: float
    explored: int
    seconds: float


def example_constants(train: list) -> list:
    """Constants the examples themselves suggest (as FlashFill does): a prefix or suffix every string output shares
    and no input contains, and a constant difference between an int output and an int input."""
    outs = [o for _, o in train]
    found = []
    if outs and all(isinstance(o, str) for o in outs):
        ins = [str(x) for args, _ in train for x in args]
        pre = outs[0]
        suf = outs[0]
        for o in outs[1:]:
            while not o.startswith(pre):
                pre = pre[:-1]
            while not o.endswith(suf):
                suf = suf[1:]
        for c in (pre, suf):
            if c and not any(c in i for i in ins):
                found.append(c)
    if outs and all(isinstance(o, int) and not isinstance(o, bool) for o in outs):
        n_args = len(train[0][0])
        for i in range(n_args):
            diffs = {o - args[i] for args, o in train if isinstance(args[i], int) and not isinstance(args[i], bool)}
            if len(diffs) == 1:
                found.append(diffs.pop())
    return found


def synthesize(params: list[str], train: list, prior=None, constants=None, time_limit: float = 5.0,
               max_cost: int = 40) -> Result:
    """Level-by-level bottom-up enumeration: level C holds every distinct behaviour first reached at integer cost C."""
    t0 = time.time()
    n = len(train)
    target = _key(tuple(o for _, o in train))
    cost_of = (lambda name: max(1, round(prior.cost(name)))) if prior is not None else (lambda name: 1)
    const_cost = (lambda v: max(1, round(prior.const_cost(v)))) if prior is not None else (lambda v: 1)
    seen: set[str] = set()
    levels: dict[int, list[tuple[str, tuple]]] = {}
    explored = 0

    def add(level: int, src: str, vals: tuple) -> bool:
        nonlocal explored
        if any(v is ERR for v in vals):
            return False
        k = _key(vals)
        if k in seen:
            return False
        seen.add(k)
        levels.setdefault(level, []).append((src, vals))
        explored += 1
        return k == target

    leaves = [(cost_of("Name"), p, tuple(args[i] for args, _ in train)) for i, p in enumerate(params)]
    consts = list(constants if constants is not None else DEFAULT_CONSTANTS) + example_constants(train)
    for c in consts:
        leaves.append((const_cost(c) if c not in example_constants(train) else 2, repr(c), tuple(c for _ in range(n))))
    ops = [(op, cost_of(op.name)) for op in OPS] + [(Op("Tuple1", 1, _b(lambda a: (a,)), lambda a: f"({a},)"),
                                                     cost_of("Tuple") + 1)]
    for level in range(1, max_cost + 1):
        for lc, src, vals in leaves:
            if lc == level and add(level, src, vals):
                return Result(src, level, explored, time.time() - t0)
        for op, oc in ops:
            rest = level - oc
            if rest < op.arity:
                continue
            for split in _compositions(rest, op.arity):
                pools = [levels.get(c, ()) for c in split]
                if any(not p for p in pools):
                    continue
                for combo in itertools.product(*pools):
                    out = tuple(op.fn(*(ch[1][j] for ch in combo)) for j in range(n))
                    src = op.show(*(ch[0] for ch in combo))
                    if add(level, src, out):
                        return Result(src, level, explored, time.time() - t0)
                    if explored % 2000 == 0 and time.time() - t0 > time_limit:
                        return Result(None, math.inf, explored, time.time() - t0)
            if time.time() - t0 > time_limit:
                return Result(None, math.inf, explored, time.time() - t0)
    return Result(None, math.inf, explored, time.time() - t0)


def _compositions(total: int, parts: int):
    """Ordered ways to write `total` as `parts` positive integers."""
    if parts == 1:
        yield (total,)
        return
    for first in range(1, total - parts + 2):
        for rest in _compositions(total - first, parts - 1):
            yield (first,) + rest
