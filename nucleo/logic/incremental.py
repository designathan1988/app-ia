"""Incremental maintenance of a model under fact insertions and removals.

The unit of recomputation is the **dependency cone** of the changed predicates.
A predicate is affected if its facts changed, or if it depends (through any
body literal, including aggregate bodies) on an affected predicate. For a
defeasible pair ``p``/``-p``, both sides are decided together, so affecting one
affects the other.

Every component with no affected predicate has exactly the same content in the
new model as in the old one: its content is a function of its own facts and of
the components below it, and none of those changed. Those components are
copied; the others are evaluated as usual, over the copied ones.

The cone is conservative, and deletion is handled by recomputing the cone, not
by counting derivations. For negation and aggregates this is the simplest
sound choice. Rule changes are not incremental: rule ids name rules in the
justifications, so a changed rule set is evaluated from scratch.

Correctness is checked by comparison with full recomputation on random update
sequences (``tests/test_incremental.py``), not argued only here.
"""

from __future__ import annotations

from ..kb.syntax import Atom, PredKey, Program, body_atoms
from .analysis import analyze
from .engine import Model, evaluate


def dependents(program: Program) -> dict[PredKey, set[PredKey]]:
    """Forward dependency graph: body predicate -> head predicates that read it."""
    out: dict[PredKey, set[PredKey]] = {}
    for r in program.rules:
        heads = {r.head.pred, r.head.pred.negated()} if r.defeasible else {r.head.pred}
        for lit in r.body:
            for atom in body_atoms(lit):
                out.setdefault(atom.pred, set()).update(heads)
    return out


def affected_by(program: Program, changed: set[PredKey]) -> set[PredKey]:
    defeasible = {r.head.pred.base for r in program.rules if r.defeasible}
    graph = dependents(program)
    seen: set[PredKey] = set()
    stack = list(changed)
    while stack:
        p = stack.pop()
        if p in seen:
            continue
        seen.add(p)
        if p.base in defeasible:
            stack.append(p.negated())
        stack.extend(graph.get(p, ()))
    return seen


def with_facts(program: Program, add=(), remove=()) -> Program:
    removed = set(remove)
    facts = [f for f in program.facts if f not in removed]
    present = set(facts)
    for f in add:
        if f not in present:
            facts.append(f)
            present.add(f)
    return Program(facts=facts, rules=program.rules, worlds=program.worlds,
                   default_world=program.default_world, priorities=program.priorities)


def update(model: Model, add: list[Atom] = (), remove: list[Atom] = ()) -> Model:
    """New model after asserting `add` and retracting `remove`. The old model is not modified."""
    for a in list(add) + list(remove):
        if not a.is_ground():
            raise ValueError(f"fato com variável: {a}")
    old = model.program
    current = set(old.facts)
    real_add = [a for a in add if a not in current]
    real_remove = [a for a in remove if a in current]
    program = with_facts(old, real_add, real_remove)
    changed = {a.pred for a in real_add} | {a.pred for a in real_remove}
    analysis = analyze(program)  # facts may introduce new predicates; rules are unchanged
    if not changed:
        return evaluate(program, analysis, reuse=model, affected=set())
    return evaluate(program, analysis, reuse=model, affected=affected_by(program, changed))
