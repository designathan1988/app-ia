"""Versioned store: as_of(t) reproduces every past state; changes survive reopening; failures roll back."""

from __future__ import annotations

import random

import pytest

from nucleo.kb.contexts import ContextError
from nucleo.kb.syntax import parse_program
from nucleo.logic.engine import evaluate
from nucleo.store.db import Store, StoreError, sentences
from tests.gen.worlds import random_program


def _snapshot(kb) -> dict:
    """Plain description of a Contexts object: per context, parents and the set of canonical sentences."""
    out = {}
    for name in kb.names():
        prog = kb._get(name).program
        out[name] = (tuple(kb.parents(name)), frozenset(t for _, t in sentences(str(prog))))
    return out


def test_as_of_reproduces_every_past_state(tmp_path):
    for seed in range(25):
        rng = random.Random(seed)
        pool = str(parse_program(random_program(seed, aggregates=True, defeasible=True))).splitlines()
        worlds = [l for l in pool if l.startswith("pred ")]
        prios = [l for l in pool if l.startswith("@") and " > @" in l]
        items = [l for l in pool if l not in worlds and l not in prios]
        path = tmp_path / f"kb{seed}.db"
        store = Store(str(path))
        expected: dict[int, dict] = {}
        with store.transaction("teste", "contextos") as tx:
            tx.define("projeto")
            tx.define("sessao", ["projeto"])
            tx.assert_("projeto", "\n".join(worlds))
        expected[store.head()] = _snapshot(store.contexts())
        active: dict[str, set] = {"projeto": set(), "sessao": set()}
        refused = 0
        for step in range(30):
            ctx = rng.choice(["projeto", "sessao"])
            before = store.head(), _snapshot(store.contexts())
            try:
                with store.transaction("teste", f"passo {step}") as tx:
                    if active[ctx] and rng.random() < 0.4:
                        line = rng.choice(sorted(active[ctx]))
                        tx.retract(ctx, line)
                        active[ctx].discard(line)
                    else:
                        line = rng.choice(items)
                        tx.assert_(ctx, line, fonte=f"seed {seed}")
                        active[ctx].add(line)
            except ContextError:  # e.g. the same rule label in both contexts: refused, nothing changes
                refused += 1
                assert (store.head(), _snapshot(store.contexts())) == before
                continue
            expected[store.head()] = _snapshot(store.contexts())
        for t, snap in expected.items():
            assert _snapshot(store.contexts(as_of=t)) == snap, f"seed {seed} tx {t}"
        # the final state, evaluated, equals evaluating the same sentences written by hand
        view = store.contexts().view("sessao").program
        by_hand = parse_program("\n".join(worlds + sorted(active["projeto"] | active["sessao"])))
        assert set(evaluate(view).entries) == set(evaluate(by_hand).entries)
        store.close()
        reopened = Store(str(path))
        for t, snap in expected.items():
            assert _snapshot(reopened.contexts(as_of=t)) == snap
        reopened.close()


def test_failed_transaction_leaves_no_trace(tmp_path):
    store = Store(str(tmp_path / "kb.db"))
    with store.transaction("teste", "base") as tx:
        tx.define("a")
        tx.assert_("a", "pred p/1 fechado. p(x).")
    before = store.head(), _snapshot(store.contexts())
    with pytest.raises(StoreError):
        with store.transaction("teste", "falha") as tx:
            tx.assert_("a", "q(y).")
            tx.retract("a", "r(z).")  # not active: the whole transaction must be undone
    assert (store.head(), _snapshot(store.contexts())) == before
    with pytest.raises(ContextError):
        with store.transaction("teste", "mundo em conflito") as tx:
            tx.define("b", ["a"])
            tx.assert_("b", "pred p/1 aberto.")
    assert (store.head(), _snapshot(store.contexts())) == before
    store.close()


def test_same_sentence_written_differently_is_one_sentence(tmp_path):
    store = Store(str(tmp_path / "kb.db"))
    with store.transaction("teste", "a") as tx:
        tx.define("a")
        first = tx.assert_("a", "voa(X)   :-  ave(X) .")
    with store.transaction("teste", "b") as tx:
        second = tx.assert_("a", "voa(X) :- ave(X).")
    assert first == second
    with store.transaction("teste", "c") as tx:
        tx.retract("a", "voa( X ) :- ave( X ).")
    hist = store.history("a", "voa(X) :- ave(X).")
    assert [(h.add_tx, h.rem_tx) for h in hist] == [(1, 3)]
    assert store.contexts(as_of=2).view("a").program.rules and not store.contexts().view("a").program.rules
    store.close()


def test_drop_context_is_versioned(tmp_path):
    store = Store(str(tmp_path / "kb.db"))
    with store.transaction("teste", "a") as tx:
        tx.define("projeto")
        tx.define("hipotese", ["projeto"])
        tx.assert_("hipotese", "p(x).")
    with store.transaction("teste", "descarta hipótese") as tx:
        with pytest.raises(StoreError):
            tx.drop("projeto")
        tx.drop("hipotese")
    assert "hipotese" in store.contexts(as_of=1) and "hipotese" not in store.contexts()
    with store.transaction("teste", "nova hipótese") as tx:
        tx.define("hipotese", ["projeto"])
    assert not store.contexts().view("hipotese").program.facts  # the old content does not come back
    store.close()
