"""Naive reference evaluator: full grounding over the active domain + iterated fixpoint.

It uses a different algorithm from the engine. The engine does join-based
semi-naive evaluation over SCCs; this module does brute-force assignment of every
variable to every constant, stratum levels computed by relaxation, and naive
fixpoints. It only works for small programs, and that is fine: it exists to be
obviously correct, not fast.

It imports only the syntax module.
"""

from __future__ import annotations

import itertools

from nucleo.kb.syntax import Atom, Cmp, Naf, NaoConsta, Pos, Program, Sym, Text, Var


class NotStratifiable(Exception):
    pass


def _key(c):
    if isinstance(c, int):
        return (0, c, "")
    if isinstance(c, Sym):
        return (1, 0, c.name)
    return (2, 0, c.value)


def _holds(op, a, b):
    if op == "=":
        return a == b
    if op == "!=":
        return a != b
    ka, kb = _key(a), _key(b)
    return {"<": ka < kb, "<=": ka <= kb, ">": ka > kb, ">=": ka >= kb}[op]


def levels(program: Program) -> dict:
    preds = program.predicates()
    level = {p: 0 for p in preds}
    limit = len(preds) + 1
    changed = True
    while changed:
        changed = False
        for r in program.rules:
            h = r.head.pred
            for lit in r.body:
                if isinstance(lit, Cmp):
                    continue
                need = level[lit.atom.pred] + (1 if isinstance(lit, (Naf, NaoConsta)) else 0)
                if level[h] < need:
                    level[h] = need
                    changed = True
                    if level[h] > limit:
                        raise NotStratifiable(str(h))
    return level


def perfect_model(program: Program) -> set:
    lvl = levels(program)
    domain = sorted(program.constants(), key=_key)
    model = set(program.facts)
    max_level = max(lvl.values(), default=0)
    for L in range(max_level + 1):
        rules = [r for r in program.rules if lvl[r.head.pred] == L]
        changed = True
        while changed:
            changed = False
            for r in rules:
                vars_ = sorted({v for lit in r.body if not isinstance(lit, Cmp) for v in lit.atom.vars()}
                               | {v for lit in r.body if isinstance(lit, Cmp) for v in lit.vars()}
                               | r.head.vars(), key=lambda v: v.name)
                for values in itertools.product(domain, repeat=len(vars_)):
                    s = dict(zip(vars_, values))

                    def g(a):
                        return Atom(a.pred, tuple(s[t] if isinstance(t, Var) else t for t in a.args))

                    ok = True
                    for lit in r.body:
                        if isinstance(lit, Pos):
                            ok = g(lit.atom) in model
                        elif isinstance(lit, (Naf, NaoConsta)):
                            ok = g(lit.atom) not in model
                        else:
                            lv = s[lit.left] if isinstance(lit.left, Var) else lit.left
                            rv = s[lit.right] if isinstance(lit.right, Var) else lit.right
                            ok = _holds(lit.op, lv, rv)
                        if not ok:
                            break
                    if ok:
                        h = g(r.head)
                        if h not in model:
                            model.add(h)
                            changed = True
    return model


def clean_model(program: Program) -> set:
    """Model derivable without any nao_consta assumption (rules using nao_consta dropped)."""
    stripped = Program(
        facts=list(program.facts),
        rules=[r for r in program.rules if not any(isinstance(l, NaoConsta) for l in r.body)],
        worlds=dict(program.worlds),
        default_world=program.default_world,
    )
    # Dropping rules can only shrink the set of positive conclusions; but `not` over closed
    # predicates is unaffected because closed predicates never depend on nao_consta.
    return perfect_model(stripped)


def expected_status(program: Program, model: set, clean: set, atom: Atom) -> tuple[str, str | None]:
    neg = Atom(atom.pred.negated(), atom.args)
    pos_in, neg_in = atom in model, neg in model
    facts = set(program.facts)

    def qual(a):
        if a in facts:
            return "afirmado"
        return "inferido" if a in clean else "presumido"

    if pos_in and neg_in:
        return ("CONTRADITORIO", None)
    if pos_in:
        return ("VERDADEIRO", qual(atom))
    if neg_in:
        return ("FALSO", qual(neg))
    if program.is_closed(atom.pred):
        return ("FALSO", "mundo_fechado")
    return ("DESCONHECIDO", None)
