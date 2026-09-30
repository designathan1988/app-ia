"""Naive reference evaluator: brute-force grounding over the active domain, iterated to a fixpoint.

This is a different algorithm from the engine:

* the engine does join-based semi-naive evaluation over SCCs, with best-cost
  provenance;
* this module assigns every variable to every constant, computes stratum
  levels by relaxation, evaluates aggregates by enumerating local variables, and
  decides defeasible conflicts with its own implementation of priority,
  specificity and team defeat.

It is only meant for small programs. It exists to be obviously correct, not
fast. It imports only the syntax module.
"""

from __future__ import annotations

import itertools

from nucleo.kb.syntax import Agg, Atom, Cmp, Naf, NaoConsta, Pos, PredKey, Program, Sym, Text, Var, body_atoms


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
    preds = set(program.predicates())
    for r in program.rules:
        preds.add(r.head.pred.negated())
    level = {p: 0 for p in preds}
    limit = len(preds) + 2
    changed = True
    while changed:
        changed = False
        for r in program.rules:
            heads = [r.head.pred] + ([r.head.pred.negated()] if r.defeasible else [])
            for lit in r.body:
                for atom in body_atoms(lit):
                    negative = r.defeasible or isinstance(lit, (Naf, NaoConsta, Agg))
                    need = level[atom.pred] + (1 if negative else 0)
                    for h in heads:
                        if level[h] < need:
                            level[h] = need
                            changed = True
                            if level[h] > limit:
                                raise NotStratifiable(str(h))
            if r.defeasible:  # p and -p are decided together
                a, b = r.head.pred, r.head.pred.negated()
                top = max(level[a], level[b])
                if level[a] != top or level[b] != top:
                    level[a] = level[b] = top
                    changed = True
    return level


def _agg_value(func, elements):
    if func == "count":
        return len(elements)
    firsts = [e[0] for e in elements]
    if func == "sum":
        return sum(x for x in firsts if isinstance(x, int) and not isinstance(x, bool))
    if not firsts:
        return None
    s = sorted(firsts, key=_key)
    return s[0] if func == "min" else s[-1]


def _ground(a, s):
    return Atom(a.pred, tuple(s[t] if isinstance(t, Var) else t for t in a.args))


def _literal_ok(lit, s, model):
    if isinstance(lit, Pos):
        return _ground(lit.atom, s) in model
    if isinstance(lit, (Naf, NaoConsta)):
        return _ground(lit.atom, s) not in model
    lv = s[lit.left] if isinstance(lit.left, Var) else lit.left
    rv = s[lit.right] if isinstance(lit.right, Var) else lit.right
    return _holds(lit.op, lv, rv)


def _agg_elements(agg: Agg, s: dict, model: set, domain: list) -> set:
    local = sorted(({v for lit in agg.body for v in _vars(lit)} | {t for t in agg.terms if isinstance(t, Var)})
                   - set(s), key=lambda v: v.name)
    out = set()
    for values in itertools.product(domain, repeat=len(local)):
        s2 = dict(s)
        s2.update(zip(local, values))
        if all(_literal_ok(l, s2, model) for l in agg.body):
            out.add(tuple(s2[t] if isinstance(t, Var) else t for t in agg.terms))
    return out


def _agg_matched_atoms(agg: Agg, s: dict, model: set, domain: list) -> list:
    """Positive atoms that take part in some satisfying assignment of the aggregate's body."""
    local = sorted(({v for lit in agg.body for v in _vars(lit)} | {t for t in agg.terms if isinstance(t, Var)})
                   - set(s), key=lambda v: v.name)
    out = []
    for values in itertools.product(domain, repeat=len(local)):
        s2 = dict(s)
        s2.update(zip(local, values))
        if all(_literal_ok(l, s2, model) for l in agg.body):
            out += [_ground(l.atom, s2) for l in agg.body if isinstance(l, Pos)]
    return out


def _vars(lit):
    if isinstance(lit, Cmp):
        return {t for t in (lit.left, lit.right) if isinstance(t, Var)}
    if isinstance(lit, Agg):
        return set()  # handled separately
    return lit.atom.vars()


def _instances(rule, model: set, domain: list):
    """All substitutions making the rule body true in `model` (aggregates computed, results bound)."""
    agg_results = {l.result for l in rule.body if isinstance(l, Agg) and isinstance(l.result, Var)}
    outer = sorted(({v for l in rule.body for v in _vars(l)} | rule.head.vars()) - agg_results, key=lambda v: v.name)
    for values in itertools.product(domain, repeat=len(outer)):
        s = dict(zip(outer, values))
        if not all(_literal_ok(l, s, model) for l in rule.body if isinstance(l, Pos)):
            continue
        ok = True
        for l in rule.body:
            if isinstance(l, Agg):
                v = _agg_value(l.func, _agg_elements(l, s, model, domain))
                if v is None:
                    ok = False
                    break
                if isinstance(l.result, Var) and l.result not in s:
                    s[l.result] = v
                elif (s[l.result] if isinstance(l.result, Var) else l.result) != v:
                    ok = False
                    break
        if not ok:
            continue
        if all(_literal_ok(l, s, model) for l in rule.body if isinstance(l, (Naf, NaoConsta, Cmp))):
            yield s


def _domain(program: Program, model: set) -> list:
    dom = set(program.constants())
    for a in model:
        dom.update(a.args)
    return sorted(dom, key=_key)


def _closure(program: Program, atoms: set) -> set:
    rules = [r for r in program.rules if not r.defeasible and all(isinstance(l, (Pos, Cmp)) for l in r.body)]
    known = set(atoms)
    dom = sorted({x for a in known for x in a.args} | set(program.constants()), key=_key)
    changed = True
    while changed:
        changed = False
        for r in rules:
            for s in _instances(r, known, dom):
                h = _ground(r.head, s)
                if h not in known:
                    known.add(h)
                    changed = True
    return known


def _prem(rule, s):
    return {_ground(l.atom, s) for l in rule.body if isinstance(l, Pos)}


def _beats(program, r, rs, o, os):
    if r.label and o.label:
        if (r.label, o.label) in program.priorities:
            return True
        if (o.label, r.label) in program.priorities:
            return False
    a, b = _prem(r, rs), _prem(o, os)
    return b <= _closure(program, a) and not a <= _closure(program, b)


def perfect_model(program: Program, *, with_indeterminate: bool = False):
    lvl = levels(program)
    model = set(program.facts)
    facts = set(program.facts)
    indeterminate: set = set()
    max_level = max(lvl.values(), default=0)
    for L in range(max_level + 1):
        # 1. defeasible decisions at this level (their bodies are strictly lower, hence complete)
        dpreds = {r.head.pred.base for r in program.rules if r.defeasible and lvl[r.head.pred] == L}
        for base in sorted(dpreds):
            dom = _domain(program, model)
            inst: dict = {}
            for r in program.rules:
                if r.defeasible and r.head.pred.base == base:
                    for s in _instances(r, model, dom):
                        inst.setdefault(_ground(r.head, s), []).append((r, s))
            targets = {Atom(PredKey(a.pred.name, a.pred.arity, False), a.args) for a in inst}
            for pos in targets:
                neg = Atom(pos.pred.negated(), pos.args)
                if pos in facts or neg in facts:
                    continue
                sup, att = inst.get(pos, []), inst.get(neg, [])

                def wins(mine, others):
                    return bool(mine) and all(any(_beats(program, m, ms, o, os) for m, ms in mine) for o, os in others)

                p, n = wins(sup, att), wins(att, sup)
                if p and not n:
                    model.add(pos)
                elif n and not p:
                    model.add(neg)
                else:
                    indeterminate.add(pos)
        # 2. strict rules at this level, to a fixpoint
        rules = [r for r in program.rules if not r.defeasible and lvl[r.head.pred] == L]
        changed = True
        while changed:
            changed = False
            dom = _domain(program, model)
            for r in rules:
                for s in list(_instances(r, model, dom)):
                    h = _ground(r.head, s)
                    if h not in model:
                        model.add(h)
                        changed = True
    return (model, indeterminate) if with_indeterminate else model


def _assumes_open(program: Program, rule) -> int:
    for l in rule.body:
        if isinstance(l, NaoConsta):
            return 1
        if isinstance(l, Agg):
            for inner in l.body:
                if isinstance(inner, NaoConsta) or (isinstance(inner, (Pos, Naf)) and not program.is_closed(inner.atom.pred)):
                    return 1
    return 0


def taints(program: Program, model: set) -> dict:
    """Minimum assumption level (0 clean / 1 relies on open-world assumption) of every atom, by definition:
    min over derivations (true rule instances with head in the model) of max(premise taints, rule assumption),
    including, for aggregates, the taint of the atoms they aggregate over."""
    INF = 9
    t = {a: INF for a in model}
    for f in program.facts:
        t[f] = 0
    dom = _domain(program, model)
    insts = []
    for r in program.rules:
        for s in _instances(r, model, dom):
            h = _ground(r.head, s)
            if h in model and h not in set(program.facts):
                prem = [_ground(l.atom, s) for l in r.body if isinstance(l, Pos)]
                agg_atoms = []
                for l in r.body:
                    if isinstance(l, Agg):
                        agg_atoms += _agg_matched_atoms(l, s, model, dom)
                insts.append((h, prem, agg_atoms, _assumes_open(program, r)))
    changed = True
    while changed:
        changed = False
        for h, prem, agg_atoms, own in insts:
            if any(t.get(p, INF) >= INF for p in prem):
                continue
            v = max([own] + [t[p] for p in prem] + [min(t.get(a, 0), 1) for a in agg_atoms])
            if v < t[h]:
                t[h] = v
                changed = True
    return t


def expected_status(program: Program, model: set, taint: dict, atom: Atom, indeterminate: set = frozenset()):
    neg = Atom(atom.pred.negated(), atom.args)
    pos_in, neg_in = atom in model, neg in model
    facts = set(program.facts)

    def qual(a):
        if a in facts:
            return "afirmado"
        return "inferido" if taint.get(a, 9) == 0 else "presumido"

    if pos_in and neg_in:
        return ("CONTRADITORIO", None)
    if pos_in:
        return ("VERDADEIRO", qual(atom))
    if neg_in:
        return ("FALSO", qual(neg))
    if atom in indeterminate:
        return ("INDETERMINADO", None)
    if program.is_closed(atom.pred):
        return ("FALSO", "mundo_fechado")
    return ("DESCONHECIDO", None)
