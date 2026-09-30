"""Engine vs. two independent oracles on random worlds, plus the independent checker on every answer."""

from __future__ import annotations

import os

import pytest

from nucleo.check.checker import check_model, check_status
from nucleo.kb.syntax import Atom, parse_program
from nucleo.logic.analysis import ProgramError, analyze
from nucleo.logic.engine import evaluate
from nucleo.logic.proof import model_certificate, proof_tree
from nucleo.logic.status import status_of
from tests.gen.worlds import random_program
from tests.helpers import ground_atoms
from tests.oracle import clingo_bridge, naive

N = int(os.environ.get("NUCLEO_DIFF_N", "300"))
SEED0 = int(os.environ.get("NUCLEO_DIFF_SEED", "0"))


def _run(seed: int, **features) -> dict:
    src = random_program(seed, **features)
    program = parse_program(src)
    analysis = analyze(program)  # the generator guarantees admissibility
    model = evaluate(program, analysis)
    engine_set = set(model.entries)

    ref, ref_indet = naive.perfect_model(program, with_indeterminate=True)
    assert engine_set == ref, f"seed {seed}: motor != oráculo ingênuo\n{src}"
    assert model.indeterminate == ref_indet, f"seed {seed}: INDETERMINADOS diferem\n{src}"
    clingo_used = True
    try:
        asp = clingo_bridge.answer_set(program)
        assert engine_set == asp, f"seed {seed}: motor != clingo\n{src}"
    except clingo_bridge.Unsupported:
        clingo_used = False

    taint = naive.taints(program, ref)
    S = check_model(program, model_certificate(model), model.indeterminate)
    stats = {"derivados": len(engine_set - set(program.facts)), "status": {}, "clingo": clingo_used}
    for atom in ground_atoms(program):
        st = status_of(model, atom)
        exp = naive.expected_status(program, ref, taint, atom, ref_indet)
        assert (st.value, st.qualifier) == exp, f"seed {seed}: status de {atom}: {st} != {exp}\n{src}"
        neg = Atom(atom.pred.negated(), atom.args)
        proof = proof_tree(model, atom) if atom in model else None
        neg_proof = proof_tree(model, neg) if neg in model else None
        check_status(program, atom, st.value, st.qualifier, S, proof, neg_proof, model.indeterminate)
        key = str(st)
        stats["status"][key] = stats["status"].get(key, 0) + 1
    return stats


def _campaign(n: int, needed: tuple, **features) -> dict:
    totals: dict[str, int] = {}
    derived_programs = 0
    clingo_runs = 0
    for seed in range(SEED0, SEED0 + n):
        stats = _run(seed, **features)
        derived_programs += stats["derivados"] > 0
        clingo_runs += stats["clingo"]
        for k, v in stats["status"].items():
            totals[k] = totals.get(k, 0) + v
    print(f"\n{features or 'base'}: status {totals} | com derivações {derived_programs}/{n} | clingo {clingo_runs}/{n}")
    for k in needed:
        assert totals.get(k, 0) > 0, f"geração trivial: nenhum caso de {k}"
    assert derived_programs >= n // 2
    return totals


def test_differential_random_worlds():
    _campaign(N, ("VERDADEIRO(afirmado)", "VERDADEIRO(inferido)", "VERDADEIRO(presumido)",
                  "FALSO(afirmado)", "FALSO(mundo_fechado)", "CONTRADITORIO", "DESCONHECIDO"))


def test_differential_aggregates_and_defeasible():
    _campaign(max(N // 2, 100), ("VERDADEIRO(inferido)", "INDETERMINADO", "FALSO(inferido)"),
              aggregates=True, defeasible=True)


def test_differential_aggregates_with_clingo():
    totals = _campaign(max(N // 2, 100), ("VERDADEIRO(inferido)",), aggregates=True)
    assert sum(totals.values()) > 0


def test_generated_programs_are_admissible():
    for seed in range(SEED0, SEED0 + 200):
        for features in ({}, {"aggregates": True, "defeasible": True}):
            try:
                analyze(parse_program(random_program(seed, **features)))
            except ProgramError as e:  # pragma: no cover - would be a generator bug
                pytest.fail(f"seed {seed} {features}: gerador produziu programa inadmissível: {e}")
