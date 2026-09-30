"""Bottom-up evaluation with minimum-cost provenance.

Evaluates a stratified program component by component (dependencies first). Each
component is evaluated with semi-naive iteration.

**Cost of an atom.** Each derived atom keeps its **best justification** under a
lexicographic cost ``(taint, size)``:

* ``taint`` is 0 for a clean proof and 1 when the proof uses ``nao_consta`` (an
  absence over open-world knowledge) anywhere. Clean proofs are preferred, so
  PRESUMIDO is reported only when no clean proof exists.
* ``size`` is the number of steps of the proof tree. Among proofs with the same
  taint, the shortest wins.

**Updates.** When a cheaper derivation of an existing atom is found, the atom
re-enters the delta so that its consequences are re-costed too. Every proof
step adds at least 1 to the size, so costs strictly decrease on each update and
the loop terminates. For the same reason every justification's premises are
strictly cheaper than its conclusion, so the justification graph is acyclic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from ..kb.syntax import Atom, Cmp, Naf, NaoConsta, Pos, PredKey, Program, Rule, Var, const_key
from .analysis import Analysis, analyze


@dataclass(frozen=True)
class Justification:
    rule: int | None  # None = asserted fact
    subst: tuple  # ((var_name, value), ...) sorted by var name
    premises: tuple  # positive (incl. strong-negation) atoms used
    absences: tuple  # (("not"|"nao_consta", Atom), ...)
    comparisons: tuple  # ((op, left_value, right_value), ...)


@dataclass
class Entry:
    cost: tuple[int, int]  # (taint, size)
    just: Justification


FACT_COST = (0, 1)


def compare(op: str, left, right) -> bool:
    if op == "=":
        return left == right
    if op == "!=":
        return left != right
    lk, rk = const_key(left), const_key(right)
    if op == "<":
        return lk < rk
    if op == "<=":
        return lk <= rk
    if op == ">":
        return lk > rk
    if op == ">=":
        return lk >= rk
    raise ValueError(op)


class Model:
    """The perfect model of a program, with the best justification of every atom."""

    def __init__(self, program: Program, analysis: Analysis) -> None:
        self.program = program
        self.analysis = analysis
        self.entries: dict[Atom, Entry] = {}
        self.relations: dict[PredKey, dict[tuple, Atom]] = {}
        self.facts: frozenset[Atom] = frozenset(program.facts)
        self._indexes: dict[tuple[PredKey, tuple[int, ...]], dict[tuple, list[Atom]]] = {}

    # -- relation access ---------------------------------------------------
    def __contains__(self, atom: Atom) -> bool:
        return atom in self.entries

    def atoms(self, pred: PredKey) -> list[Atom]:
        return list(self.relations.get(pred, {}).values())

    def all_atoms(self) -> list[Atom]:
        return list(self.entries)

    def _index(self, pred: PredKey, positions: tuple[int, ...]) -> dict[tuple, list[Atom]]:
        key = (pred, positions)
        idx = self._indexes.get(key)
        if idx is None:
            idx = {}
            for atom in self.relations.get(pred, {}).values():
                idx.setdefault(tuple(atom.args[p] for p in positions), []).append(atom)
            self._indexes[key] = idx
        return idx

    def _add(self, atom: Atom, entry: Entry) -> bool:
        """Insert or improve. Returns True if the atom is new or got cheaper."""
        old = self.entries.get(atom)
        if old is not None and old.cost <= entry.cost:
            return False
        self.entries[atom] = entry
        if old is None:
            self.relations.setdefault(atom.pred, {})[atom.args] = atom
            for (pred, positions), idx in self._indexes.items():
                if pred == atom.pred:
                    idx.setdefault(tuple(atom.args[p] for p in positions), []).append(atom)
        return True

    def lookup(self, pattern: Atom, subst: dict) -> Iterator[Atom]:
        bound = tuple(
            i for i, t in enumerate(pattern.args) if not isinstance(t, Var) or t in subst
        )
        if not bound:
            yield from list(self.relations.get(pattern.pred, {}).values())
            return
        key = tuple(
            subst[t] if isinstance(t, Var) else t for t in (pattern.args[i] for i in bound)
        )
        yield from list(self._index(pattern.pred, bound).get(key, ()))


def _unify(pattern: Atom, atom: Atom, subst: dict) -> dict | None:
    out = subst
    copied = False
    for t, v in zip(pattern.args, atom.args):
        if isinstance(t, Var):
            if t in out:
                if out[t] != v:
                    return None
            else:
                if not copied:
                    out = dict(out)
                    copied = True
                out[t] = v
        elif t != v:
            return None
    return out


def _ground(atom: Atom, subst: dict) -> Atom:
    return Atom(atom.pred, tuple(subst[t] if isinstance(t, Var) else t for t in atom.args))


def _value(term, subst: dict):
    return subst[term] if isinstance(term, Var) else term


class _Evaluator:
    def __init__(self, model: Model) -> None:
        self.model = model

    def _ordered_body(self, rule: Rule, delta_pos: int | None) -> list[tuple[int, object]]:
        positives = [(i, lit) for i, lit in enumerate(rule.body) if isinstance(lit, Pos)]
        if delta_pos is not None:
            positives.sort(key=lambda item: item[0] != delta_pos)
        others = [(i, lit) for i, lit in enumerate(rule.body) if not isinstance(lit, Pos)]
        # comparisons before absences: both need all variables bound (guaranteed by safety)
        others.sort(key=lambda item: not isinstance(item[1], Cmp))
        return positives + others

    def fire(self, rule: Rule, delta_pos: int | None, delta: dict[PredKey, set[Atom]]):
        """Yield (head_atom, entry) for every rule instance, using `delta` at position delta_pos."""
        body = self._ordered_body(rule, delta_pos)
        model = self.model

        def rec(k: int, subst: dict, premises: list[Atom], absences: list, comps: list):
            if k == len(body):
                head = _ground(rule.head, subst)
                ordered = tuple(atom for _, atom in sorted(premises, key=lambda x: x[0]))
                taint = 0
                size = 1 + len(absences) + len(comps)
                for p in ordered:
                    c = model.entries[p].cost
                    taint = max(taint, c[0])
                    size += c[1]
                if any(kind == "nao_consta" for kind, _ in absences):
                    taint = 1
                just = Justification(
                    rule.id,
                    tuple(sorted(((v.name, val) for v, val in subst.items()), key=lambda x: x[0])),
                    ordered,  # premises in the rule's body order, not evaluation order
                    tuple(absences),
                    tuple(comps),
                )
                yield head, Entry((taint, size), just)
                return
            idx, lit = body[k]
            if isinstance(lit, Pos):
                if idx == delta_pos:
                    candidates = [
                        a for a in delta.get(lit.atom.pred, ())
                        if _unify(lit.atom, a, subst) is not None
                    ]
                else:
                    candidates = model.lookup(lit.atom, subst)
                for atom in candidates:
                    s2 = _unify(lit.atom, atom, subst)
                    if s2 is None:
                        continue
                    premises.append((idx, atom))
                    yield from rec(k + 1, s2, premises, absences, comps)
                    premises.pop()
            elif isinstance(lit, Cmp):
                left, right = _value(lit.left, subst), _value(lit.right, subst)
                if compare(lit.op, left, right):
                    comps.append((lit.op, left, right))
                    yield from rec(k + 1, subst, premises, absences, comps)
                    comps.pop()
            else:  # Naf / NaoConsta: the target lives in an already-completed component
                target = _ground(lit.atom, subst)
                if target not in model:
                    kind = "not" if isinstance(lit, Naf) else "nao_consta"
                    absences.append((kind, target))
                    yield from rec(k + 1, subst, premises, absences, comps)
                    absences.pop()

        yield from rec(0, {}, [], [], [])


def evaluate(program: Program, analysis: Analysis | None = None) -> Model:
    analysis = analysis or analyze(program)
    model = Model(program, analysis)
    ev = _Evaluator(model)
    facts_by_pred: dict[PredKey, list[Atom]] = {}
    for f in program.facts:
        facts_by_pred.setdefault(f.pred, []).append(f)

    for ci, comp in enumerate(analysis.components):
        delta: dict[PredKey, set[Atom]] = {}
        for pred in comp:
            for f in facts_by_pred.get(pred, ()):
                if model._add(f, Entry(FACT_COST, Justification(None, (), (), (), ()))):
                    delta.setdefault(pred, set()).add(f)
        rules = analysis.rules_of[ci]
        # first round: every rule over everything known so far
        for rule in rules:
            for head, entry in list(ev.fire(rule, None, {})):
                if model._add(head, entry):
                    delta.setdefault(head.pred, set()).add(head)
        # semi-naive rounds over the recursive positions
        recursive = [
            (rule, i)
            for rule in rules
            for i, lit in enumerate(rule.body)
            if isinstance(lit, Pos) and lit.atom.pred in comp
        ]
        while delta and recursive:
            new_delta: dict[PredKey, set[Atom]] = {}
            for rule, pos in recursive:
                if rule.body[pos].atom.pred not in delta:
                    continue
                for head, entry in list(ev.fire(rule, pos, delta)):
                    if model._add(head, entry):
                        new_delta.setdefault(head.pred, set()).add(head)
            delta = new_delta
    return model
