"""Metamorphic properties: the engine must not depend on names, statement order or irrelevant knowledge."""

from __future__ import annotations

import random

from nucleo.kb.syntax import Atom, PredKey, Program, Rule, Sym, Var, parse_program
from nucleo.logic.engine import evaluate
from nucleo.logic.status import status_of
from tests.gen.worlds import pseudo_word, random_program
from tests.helpers import ground_atoms


def _rename(program: Program, seed: int):
    rng = random.Random(seed)
    preds = {p.name for p in program.predicates()}
    syms = {c.name for c in program.constants() if isinstance(c, Sym)}
    taken: set[str] = set()

    def fresh():
        while True:
            w = "q" + pseudo_word(rng, 3)
            if w not in taken:
                taken.add(w)
                return w

    pmap = {p: fresh() for p in sorted(preds)}
    smap = {s: fresh() for s in sorted(syms)}

    def t(x):
        return Sym(smap[x.name]) if isinstance(x, Sym) else x

    def a(atom: Atom) -> Atom:
        return Atom(PredKey(pmap[atom.pred.name], atom.pred.arity, atom.pred.neg), tuple(t(x) for x in atom.args))

    def lit(l):
        from nucleo.kb.syntax import Cmp
        if isinstance(l, Cmp):
            return Cmp(l.op, t(l.left), t(l.right))
        return type(l)(a(l.atom))

    renamed = Program(
        facts=[a(f) for f in program.facts],
        rules=[Rule(r.id, a(r.head), tuple(lit(l) for l in r.body)) for r in program.rules],
        worlds={(pmap[n], ar): w for (n, ar), w in program.worlds.items()},
    )
    return renamed, a


def test_renaming_invariance():
    for seed in range(200):
        program = parse_program(random_program(seed))
        # renaming must preserve the order of symbols for comparisons; keep only programs without
        # symbol-vs-symbol ordering comparisons to make the property exact
        if any(getattr(l, "op", None) in ("<", "<=", ">", ">=") for r in program.rules for l in r.body):
            continue
        model = evaluate(program)
        renamed, f = _rename(program, seed + 1000)
        model2 = evaluate(renamed)
        assert {f(x) for x in model.entries} == set(model2.entries), f"seed {seed}"
        for atom in ground_atoms(program, 60):
            assert status_of(model, atom) == status_of(model2, f(atom)), f"seed {seed}: {atom}"


def test_statement_order_invariance():
    for seed in range(200):
        src = random_program(seed)
        lines = src.strip().splitlines()
        random.Random(seed).shuffle(lines)
        m1 = evaluate(parse_program(src))
        m2 = evaluate(parse_program("\n".join(lines)))
        assert set(m1.entries) == set(m2.entries)
        for a in m1.entries:  # the best cost is order-independent (the proof itself may differ on ties)
            assert m1.entries[a].cost == m2.entries[a].cost


def test_irrelevant_knowledge_changes_nothing():
    for seed in range(200):
        program = parse_program(random_program(seed))
        model = evaluate(program)
        # add facts about a brand-new predicate nobody depends on
        extra = parse_program("pred zzqunrelated/2 aberto. zzqunrelated(k1, k2). zzqunrelated(k2, k3).")
        program.facts += extra.facts
        program.worlds.update(extra.worlds)
        model2 = evaluate(program)
        assert set(model.entries) <= set(model2.entries)
        assert set(model2.entries) - set(model.entries) == set(extra.facts)
