"""Minimal conflict sets, verified by the naive oracle (not by the engine that produced them)."""

from __future__ import annotations

import itertools
import os

from nucleo.kb.syntax import Atom, PredKey, Program, parse_atom, parse_program
from nucleo.logic.conflict import minimal_conflict
from nucleo.logic.engine import evaluate
from nucleo.logic.status import CONTRADITORIO, status_of
from tests.gen.worlds import random_program
from tests.helpers import ground_atoms
from tests.oracle import naive

N = int(os.environ.get("NUCLEO_DIFF_N", "300"))


def _conflicts_with(program: Program, facts, atom: Atom) -> bool:
    p = Program(facts=list(facts), rules=program.rules, worlds=program.worlds,
                default_world=program.default_world, priorities=program.priorities)
    m = naive.perfect_model(p)
    return atom in m and Atom(atom.pred.negated(), atom.args) in m


def test_minimal_conflict_on_random_worlds():
    seen = subset_checked = 0
    for seed in range(max(N // 2, 100)):
        for features in ({}, {"aggregates": True, "defeasible": True}):
            program = parse_program(random_program(seed, **features))
            model = evaluate(program)
            for atom in ground_atoms(program):
                if status_of(model, atom).value != CONTRADITORIO:
                    continue
                seen += 1
                res = minimal_conflict(model, atom)
                facts = res["fatos"]
                assert set(facts) <= set(program.facts)
                assert _conflicts_with(program, facts, atom), f"seed {seed}: {atom} não reproduz"
                for f in facts:
                    rest = [g for g in facts if g != f]
                    assert not _conflicts_with(program, rest, atom), f"seed {seed}: {f} é redundante"
                if res["minimalidade"] == "subconjunto" and len(facts) <= 8:
                    subset_checked += 1
                    for k in range(len(facts)):
                        for combo in itertools.combinations(facts, k):
                            assert not _conflicts_with(program, combo, atom), f"seed {seed}: {combo} menor"
    print(f"\ncontradições {seen}; minimalidade por subconjunto verificada em força bruta: {subset_checked}")
    assert seen > 50 and subset_checked > 20


def test_irrelevant_facts_are_not_blamed():
    program = parse_program("""
        ave(X) :- pinguim(X).
        voa(X) :- ave(X).
        -voa(X) :- pinguim(X).
        pinguim(tweety). ave(piu). cor(tweety, preto). ave(tweety).
    """)
    res = minimal_conflict(evaluate(program), parse_atom("voa(tweety)"))
    assert res["fatos"] == [parse_atom("pinguim(tweety)")]
    assert res["minimalidade"] == "subconjunto"


def test_protecting_fact_outside_the_proofs_is_found():
    # -p needs `not q`; q is blocked only by the fact s, which appears in no proof
    program = parse_program("""
        pred q/0 fechado. pred s/0 fechado.
        p :- a.
        -p :- b, not q.
        q :- not s.
        a. b. s. irrelevante.
    """)
    res = minimal_conflict(evaluate(program), parse_atom("p"))
    assert sorted(map(str, res["fatos"])) == ["a", "b", "s"]
    assert res["minimalidade"] == "irredundante"


def test_non_contradictory_atom_is_rejected():
    model = evaluate(parse_program("p(a)."))
    try:
        minimal_conflict(model, Atom(PredKey("p", 1), (parse_atom("p(a)").args[0],)))
    except ValueError:
        return
    raise AssertionError("deveria recusar")
