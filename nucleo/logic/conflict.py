"""Minimal conflict set of a contradiction: which asserted facts, together, produce both ``p`` and ``-p``.

A CONTRADITORIO atom has a proof for each side. The facts at the leaves of
both proofs are enough for the conflict only if nothing else was needed. With
negation or aggregates, removing a fact can create a conclusion, so enough-ness
is **re-checked by evaluation**, never assumed.

Algorithm (deletion-based):

1. Restrict the program to the backward cone of ``p`` / ``-p``. Only rules
   whose head can influence them, and only facts of cone predicates, matter.
   The cone's predicates depend only on the cone, so its model agrees with the
   full model there.
2. Candidate set: the facts at the leaves of both proofs if they alone
   reproduce the conflict, otherwise every fact of the cone.
3. Try to drop each fact in a fixed order. Keep the drop when the conflict
   survives.

The result is **irredundant**: removing any single fact dissolves the conflict.
When the cone is monotone (no ``not``, ``nao_consta``, aggregate or defeasible
rule), entailment is monotone, and irredundant implies **subset-minimal**:
if a proper subset produced the conflict, so would the superset obtained by
removing one element. The result says which guarantee holds.
"""

from __future__ import annotations

from ..kb.syntax import Agg, Atom, Naf, NaoConsta, PredKey, Program, body_atoms
from .engine import Model, evaluate
from .proof import proof_tree


def _cone(program: Program, targets: set[PredKey]) -> tuple[set[PredKey], list]:
    defeasible = {r.head.pred.base for r in program.rules if r.defeasible}
    cone: set[PredKey] = set()
    stack = list(targets)
    while stack:
        p = stack.pop()
        if p in cone:
            continue
        cone.add(p)
        if p.base in defeasible:
            stack.append(p.negated())
        for r in program.rules:
            if r.head.pred == p:
                for lit in r.body:
                    stack.extend(a.pred for a in body_atoms(lit))
    rules = [r for r in program.rules if r.head.pred in cone]
    return cone, rules


def _leaves(tree: dict, out: set) -> None:
    if tree["tipo"] == "fato":
        out.add(tree["atomo"])
        return
    for p in tree["premissas"]:
        _leaves(p, out)


def _rules_used(tree: dict, out: set) -> None:
    if tree["tipo"] == "regra":
        out.add(tree["regra"])
        for p in tree["premissas"]:
            _rules_used(p, out)


def minimal_conflict(model: Model, atom: Atom) -> dict:
    neg = Atom(atom.pred.negated(), atom.args)
    if atom not in model or neg not in model:
        raise ValueError(f"{atom} não é contraditório neste modelo")
    program = model.program
    cone, rules = _cone(program, {atom.pred, neg.pred})
    labels = {r.label for r in rules if r.label}
    priorities = {(a, b) for a, b in program.priorities if a in labels and b in labels}
    cone_facts = list(dict.fromkeys(f for f in program.facts if f.pred in cone))  # a set, in program order
    monotone = all(
        not r.defeasible and not any(isinstance(l, (Naf, NaoConsta, Agg)) for l in r.body) for r in rules
    )
    checks = 0

    def sub(facts) -> Program:
        return Program(facts=list(facts), rules=rules, worlds=program.worlds,
                       default_world=program.default_world, priorities=priorities)

    def conflict(facts) -> bool:
        nonlocal checks
        checks += 1
        m = evaluate(sub(facts))
        return atom in m and neg in m

    leaves: set[Atom] = set()
    _leaves(proof_tree(model, atom), leaves)
    _leaves(proof_tree(model, neg), leaves)
    order = [f for f in cone_facts if f in leaves]
    current = order if conflict(order) else cone_facts
    for fact in list(current):
        trial = [f for f in current if f != fact]
        if conflict(trial):
            current = trial

    final = evaluate(sub(current))
    used: set[int] = set()
    _rules_used(proof_tree(final, atom), used)
    _rules_used(proof_tree(final, neg), used)
    return {
        "atomo": atom,
        "fatos": current,
        "regras": sorted(used),
        "minimalidade": "subconjunto" if monotone else "irredundante",
        "avaliacoes": checks,
    }
