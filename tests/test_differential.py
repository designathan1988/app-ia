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


def _run(seed: int) -> dict:
    src = random_program(seed)
    program = parse_program(src)
    analysis = analyze(program)  # generator guarantees admissibility
    model = evaluate(program, analysis)
    engine_set = set(model.entries)

    ref = naive.perfect_model(program)
    assert engine_set == ref, f"seed {seed}: motor != oráculo ingênuo\n{src}"
    asp = clingo_bridge.answer_set(program)
    assert engine_set == asp, f"seed {seed}: motor != clingo\n{src}"

    clean = naive.clean_model(program)
    S = check_model(program, model_certificate(model))
    stats = {"derivados": len(engine_set - set(program.facts)), "status": {}}
    for atom in ground_atoms(program):
        st = status_of(model, atom)
        exp = naive.expected_status(program, ref, clean, atom)
        assert (st.value, st.qualifier) == exp, f"seed {seed}: status de {atom}: {st} != {exp}\n{src}"
        neg = Atom(atom.pred.negated(), atom.args)
        proof = proof_tree(model, atom) if atom in model else None
        neg_proof = proof_tree(model, neg) if neg in model else None
        check_status(program, atom, st.value, st.qualifier, S, proof, neg_proof)
        key = str(st)
        stats["status"][key] = stats["status"].get(key, 0) + 1
    return stats


def test_differential_random_worlds():
    totals: dict[str, int] = {}
    derived_programs = 0
    for seed in range(SEED0, SEED0 + N):
        stats = _run(seed)
        derived_programs += stats["derivados"] > 0
        for k, v in stats["status"].items():
            totals[k] = totals.get(k, 0) + v
    # non-triviality: the random worlds must actually exercise every status
    print("\nstatus totals:", totals, "| programs with derivations:", derived_programs, "/", N)
    for needed in ("VERDADEIRO(afirmado)", "VERDADEIRO(inferido)", "VERDADEIRO(presumido)",
                   "FALSO(afirmado)", "FALSO(mundo_fechado)", "CONTRADITORIO", "DESCONHECIDO"):
        assert totals.get(needed, 0) > 0, f"geração trivial: nenhum caso de {needed}"
    assert derived_programs >= N // 2


def test_generated_programs_are_admissible():
    for seed in range(SEED0, SEED0 + 200):
        try:
            analyze(parse_program(random_program(seed)))
        except ProgramError as e:  # pragma: no cover - would be a generator bug
            pytest.fail(f"seed {seed}: gerador produziu programa inadmissível: {e}")
