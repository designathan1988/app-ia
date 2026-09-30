"""Shared test helpers (no answers here; only plumbing)."""

from __future__ import annotations

import itertools

from nucleo.kb.syntax import Atom, PredKey, Program, const_key


def ground_atoms(program: Program, max_per_pred: int = 400) -> list[Atom]:
    """Every positive ground atom over the program's constants (bounded per predicate)."""
    domain = sorted(program.constants(), key=const_key)
    out: list[Atom] = []
    bases = sorted({PredKey(p.name, p.arity) for p in program.predicates()})
    for pred in bases:
        combos = itertools.product(domain, repeat=pred.arity)
        for args in itertools.islice(combos, max_per_pred):
            out.append(Atom(pred, tuple(args)))
    return out
