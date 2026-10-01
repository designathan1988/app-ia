"""Typed lambda calculus for meanings (Carpenter 1997; the notation of the Cornell SPF).

Terms are immutable: constants ``name:type``, variables, lambda abstractions and n-ary applications. A conjunction
or disjunction is one application with any number of arguments (type ``<t*,t>``), as in SPF.

- ``parse`` reads the SPF string form: ``(lambda $0:e (and:<t*,t> (city:<c,t> $0) (loc:<lo,<lo,t>> $0 texas:s)))``.
- ``beta`` reduces; ``apply`` and ``compose`` build ``f(g)`` and ``lambda x. f(g(x))``.
- ``key`` is a canonical form: bound variables renamed in order of appearance and the arguments of ``and``/``or``
  sorted, so two terms with the same meaning have the same key (exact-match evaluation compares keys).
- ``type_of`` infers the type of a term from its constants and variables.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

# -- types: a base type is a string; a function type is (arg, result); a variadic one is ("*", arg, result) ----
T = "t"


def parse_type(s: str):
    s = s.strip()
    if not s.startswith("<"):
        return s
    inner = s[1:-1]
    depth = 0
    for i, ch in enumerate(inner):
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        elif ch == "," and depth == 0:
            a, b = inner[:i], inner[i + 1:]
            if a.endswith("*"):
                return ("*", parse_type(a[:-1]), parse_type(b))
            return (parse_type(a), parse_type(b))
    raise ValueError(f"bad type {s!r}")


def type_str(ty) -> str:
    if isinstance(ty, str):
        return ty
    if ty[0] == "*":
        return f"<{type_str(ty[1])}*,{type_str(ty[2])}>"
    return f"<{type_str(ty[0])},{type_str(ty[1])}>"


def is_fn(ty) -> bool:
    return isinstance(ty, tuple)


def result(ty, n_args: int):
    """The type of a function of type ``ty`` applied to ``n_args`` arguments."""
    for _ in range(n_args):
        if not is_fn(ty):
            return None
        if ty[0] == "*":
            return ty[2]
        ty = ty[1]
    return ty


def arg_types(ty, n_args: int) -> list:
    out = []
    for _ in range(n_args):
        if not is_fn(ty):
            break
        if ty[0] == "*":
            out.append(ty[1])
            continue
        out.append(ty[0])
        ty = ty[1]
    return out


# -- terms ------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Const:
    name: str
    type: object

    def __str__(self) -> str:
        return f"{self.name}:{type_str(self.type)}"


_ids = itertools.count(1)


@dataclass(frozen=True)
class Var:
    id: int
    type: object

    def __str__(self) -> str:
        return f"$v{self.id}"


def fresh(ty) -> Var:
    return Var(next(_ids), ty)


@dataclass(frozen=True)
class Lam:
    var: Var
    body: object


@dataclass(frozen=True)
class App:
    fn: object
    args: tuple


STRUCTURAL = {"and", "or", "not"}  # connectives that belong to the composition, not to any word's lexeme


def is_structural(c) -> bool:
    return isinstance(c, Const) and c.name in STRUCTURAL


# -- parsing ----------------------------------------------------------------------------------------------------
def _tokens(s: str) -> list[str]:
    # (types never contain spaces or parentheses, so the SPF form splits on them; predicate names may be "<", ">")
    out, cur = [], ""
    for ch in s:
        if ch in "() \t\n":
            if cur:
                out.append(cur)
            cur = ""
            if ch in "()":
                out.append(ch)
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


def parse(s: str):
    toks = _tokens(s)
    pos = 0

    def atom(tok, env):
        if tok.startswith("$"):
            name = tok.split(":")[0]
            return env[name]
        name, _, ty = tok.rpartition(":")
        return Const(name, parse_type(ty))

    def expr(env):
        nonlocal pos
        tok = toks[pos]
        if tok != "(":
            pos += 1
            return atom(tok, env)
        pos += 1
        if toks[pos] == "lambda":
            pos += 1
            name, ty = toks[pos].split(":", 1)
            pos += 1
            v = fresh(parse_type(ty))
            body = expr({**env, name: v})
            assert toks[pos] == ")"
            pos += 1
            return Lam(v, body)
        fn = expr(env)
        args = []
        while toks[pos] != ")":
            args.append(expr(env))
        pos += 1
        return normalize(App(fn, tuple(args)))

    t = expr({})
    return t


# -- types of terms ----------------------------------------------------------------------------------------------
def type_of(t):
    if isinstance(t, (Const, Var)):
        return t.type
    if isinstance(t, Lam):
        b = type_of(t.body)
        return None if b is None else (t.var.type, b)
    if isinstance(t, App):
        return result(type_of(t.fn), len(t.args))
    raise TypeError(t)


# -- traversal ----------------------------------------------------------------------------------------------------
def free_vars(t, bound=frozenset()) -> list:
    out: list = []

    def go(x, b):
        if isinstance(x, Var):
            if x not in b and x not in out:
                out.append(x)
        elif isinstance(x, Lam):
            go(x.body, b | {x.var})
        elif isinstance(x, App):
            go(x.fn, b)
            for a in x.args:
                go(a, b)

    go(t, bound)
    return out


def constants(t) -> list:
    """The constants of a term in traversal order (with repeats), connectives excluded."""
    out: list = []

    def go(x):
        if isinstance(x, Const):
            if not is_structural(x):
                out.append(x)
        elif isinstance(x, Lam):
            go(x.body)
        elif isinstance(x, App):
            go(x.fn)
            for a in x.args:
                go(a)

    go(t)
    return out


_CSTR: dict = {}


def const_str(c) -> str:
    s = _CSTR.get(c)
    if s is None:
        s = _CSTR[c] = str(c)
    return s


def size(t) -> int:
    if isinstance(t, Lam):
        return 1 + size(t.body)
    if isinstance(t, App):
        return 1 + size(t.fn) + sum(size(a) for a in t.args)
    return 1


# -- substitution and reduction ------------------------------------------------------------------------------------
def _rename(t, m: dict):
    """A copy of ``t`` with every bound variable fresh (and free variables mapped by ``m``)."""
    if isinstance(t, Var):
        return m.get(t, t)
    if isinstance(t, Const):
        return t
    if isinstance(t, Lam):
        v = fresh(t.var.type)
        return Lam(v, _rename(t.body, {**m, t.var: v}))
    return App(_rename(t.fn, m), tuple(_rename(a, m) for a in t.args))


def subst(t, var: Var, val):
    if isinstance(t, Var):
        return _rename(val, {}) if t == var else t
    if isinstance(t, Const):
        return t
    if isinstance(t, Lam):
        return t if t.var == var else Lam(t.var, subst(t.body, var, val))
    return normalize(App(subst(t.fn, var, val), tuple(subst(a, var, val) for a in t.args)))


def normalize(t):
    """One level of normalization of an application: beta-reduce a lambda head, flatten nested applications and
    nested conjunctions/disjunctions."""
    if not isinstance(t, App):
        return t
    fn, args = t.fn, t.args
    if not args:
        return fn
    if isinstance(fn, App):
        return normalize(App(fn.fn, fn.args + args))
    if isinstance(fn, Lam):
        body = subst(fn.body, fn.var, args[0])
        rest = args[1:]
        return normalize(App(body, rest)) if rest else body
    if isinstance(fn, Const) and fn.name in ("and", "or"):
        flat = []
        for a in args:
            if isinstance(a, App) and isinstance(a.fn, Const) and a.fn.name == fn.name:
                flat.extend(a.args)
            else:
                flat.append(a)
        if len(flat) == 1:
            return flat[0]
        return App(fn, tuple(flat))
    return t


def beta(t):
    if isinstance(t, Lam):
        return Lam(t.var, beta(t.body))
    if isinstance(t, App):
        return normalize(App(beta(t.fn), tuple(beta(a) for a in t.args)))
    return t


def apply(f, g):
    return beta(normalize(App(f, (g,))))


def compose(f, g):
    """lambda x. f(g(x)), for g a function."""
    gt = type_of(g)
    if not is_fn(gt) or gt[0] == "*":
        return None
    x = fresh(gt[0])
    return Lam(x, apply(f, apply(g, x)))


# -- canonical key -------------------------------------------------------------------------------------------------
def key(t) -> str:
    names: dict = {}

    def go(x) -> str:
        if isinstance(x, Const):
            return str(x)
        if isinstance(x, Var):
            return names.get(x, f"?{x.id}")
        if isinstance(x, Lam):
            names[x.var] = f"${len(names)}"
            return f"(lambda {names[x.var]}:{type_str(x.var.type)} {go(x.body)})"
        parts = [go(a) for a in x.args]
        if isinstance(x.fn, Const) and x.fn.name in ("and", "or"):
            parts = sorted(parts)
        return "(" + " ".join([go(x.fn)] + parts) + ")"

    return go(t)


def canonical(t) -> str:
    """The key with bound variables numbered by their position in the sorted form (stable across orderings of
    conjuncts): computed twice so that names follow the sorted traversal."""
    k = key(t)
    return key(parse(k)) if "$" in k else k


def show(t) -> str:
    return key(t)
