"""Incremental maintenance == full recomputation, on random update sequences over random worlds."""

from __future__ import annotations

import os
import random

from nucleo.check.checker import check_model
from nucleo.kb.syntax import Atom, PredKey, const_key, parse_program
from nucleo.logic.engine import evaluate
from nucleo.logic.incremental import affected_by, update
from nucleo.logic.proof import model_certificate
from tests.gen.worlds import random_program

N = int(os.environ.get("NUCLEO_DIFF_N", "300"))


def _random_change(rng: random.Random, program):
    consts = sorted(program.constants(), key=const_key)
    preds = sorted({p for p in program.predicates()}, key=str)
    if program.facts and rng.random() < 0.45:
        return [], [rng.choice(program.facts)]
    pred = rng.choice(preds)
    atom = Atom(pred, tuple(rng.choice(consts) for _ in range(pred.arity)))
    return [atom], []


def _same(inc, full, context: str) -> None:
    assert set(inc.entries) == set(full.entries), context
    for atom, entry in full.entries.items():
        assert inc.entries[atom].cost == entry.cost, f"{context}: custo de {atom}"
    assert inc.indeterminate == full.indeterminate, context


def _sequences(n: int, steps: int, **features) -> tuple[int, int]:
    reused = total = 0
    for seed in range(n):
        rng = random.Random(1000 + seed)
        model = evaluate(parse_program(random_program(seed, **features)))
        for step in range(steps):
            add, remove = _random_change(rng, model.program)
            model = update(model, add, remove)
            full = evaluate(model.program)
            _same(model, full, f"seed {seed} passo {step} +{add} -{remove}")
            check_model(model.program, model_certificate(model), model.indeterminate)
            reused += model.reused_components
            total += len(model.analysis.components)
    return reused, total


def test_incremental_equals_recompute():
    reused, total = _sequences(max(N // 3, 60), 8)
    print(f"\nbase: componentes reaproveitados {reused}/{total}")
    assert reused > total // 4, "o incremental quase não reaproveita: não é incremental"


def test_incremental_equals_recompute_extended():
    reused, total = _sequences(max(N // 3, 60), 8, aggregates=True, defeasible=True)
    print(f"\nagregados+derrotáveis: componentes reaproveitados {reused}/{total}")
    assert reused > total // 4


def test_retract_then_reassert_restores_model():
    for seed in range(60):
        model = evaluate(parse_program(random_program(seed, aggregates=True, defeasible=True)))
        for fact in list(model.program.facts)[:5]:
            back = update(update(model, remove=[fact]), add=[fact])
            _same(back, model, f"seed {seed} fato {fact}")


def test_affected_cone_is_closed_and_pairs_defeasible():
    program = parse_program("""
        @a voa(X) <~ ave(X).
        @b -voa(X) <~ pinguim(X).
        viaja(X) :- -voa(X).
        conta(N) :- N = #count{X : viaja(X)}.
        outro(X) :- zzz(X).
    """)
    cone = affected_by(program, {PredKey("pinguim", 1)})
    assert {PredKey("voa", 1), PredKey("voa", 1, True), PredKey("viaja", 1), PredKey("conta", 1)} <= cone
    assert PredKey("outro", 1) not in cone and PredKey("ave", 1) not in cone


def test_noop_update_reuses_everything():
    model = evaluate(parse_program(random_program(7)))
    same = update(model, add=[model.program.facts[0]])
    assert same.reused_components == len(same.analysis.components)
    _same(same, model, "sem mudança")
