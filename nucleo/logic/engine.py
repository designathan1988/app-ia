"""Bottom-up evaluation with minimum-cost provenance, aggregates and defeasible conflict resolution.

**Order of evaluation.** A stratified program is evaluated component by
component, dependencies first. Each component uses semi-naive iteration.

**Proof cost.** Each atom keeps its **best justification** under the
lexicographic cost ``(taint, size)``:

* ``taint`` is 1 when the proof relies on an assumption about open-world
  knowledge: a ``nao_consta``, or an aggregate over open predicates, which is
  only a bound. It is 0 otherwise.
* Clean proofs are therefore preferred, and among them the shortest wins.
* An improvement re-enters the delta. Every step adds at least 1 to the size,
  so costs strictly decrease, the iteration terminates, and justifications are
  acyclic (every premise is strictly cheaper than its conclusion).

**Aggregates.** An aggregate is evaluated over strictly lower strata, which are
complete when it is read (guaranteed by the analysis).

**Defeasible rules.** For a pair ``p`` / ``-p`` with defeasible rules (and no
strict rules), every ground atom is decided once, when its component is
reached. At that point every body predicate is complete.

1. An asserted fact always wins over a defeasible conclusion.
2. Otherwise, let the supporters be the firing instances for ``p(c)`` and the
   attackers those for ``-p(c)``.
3. ``p(c)`` holds if every attacker is beaten by some supporter ("team defeat").
   Symmetrically for ``-p(c)``.
4. Rule ``r`` beats rule ``s`` if a priority ``@r > @s`` is declared. Without a
   priority either way, ``r`` beats ``s`` if it is strictly more specific: the
   body of ``s`` follows from the body of ``r`` by the strict positive rules,
   and not vice versa.
5. If neither side wins, the atom is **INDETERMINADO**, which is different from
   a contradiction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from ..kb.syntax import Agg, Atom, Cmp, Naf, NaoConsta, Pos, PredKey, Program, Rule, Var, const_key
from .analysis import Analysis, analyze


@dataclass(frozen=True)
class Justification:
    rule: int | None  # None = asserted fact
    subst: tuple  # ((var_name, value), ...) sorted by var name
    premises: tuple  # positive (incl. strong-negation) atoms used, in body order
    absences: tuple  # (("not"|"nao_consta", Atom), ...)
    comparisons: tuple  # ((op, left_value, right_value), ...)
    aggregates: tuple = ()  # ((body_index, func, elements_tuple, value), ...)
    defeats: tuple = ()  # ((attacker_rule_id, attacker_subst, reason), ...) for defeasible conclusions


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


def aggregate_value(func: str, elements: set):
    """Value of an aggregate over a set of tuples, or None when undefined."""
    if func == "count":
        return len(elements)
    firsts = [e[0] for e in elements]
    if func == "sum":
        return sum(x for x in firsts if isinstance(x, int) and not isinstance(x, bool))
    if not firsts:
        return None
    key = sorted(firsts, key=const_key)
    return key[0] if func == "min" else key[-1]


class Model:
    """The perfect model of a program, with the best justification of every atom."""

    def __init__(self, program: Program, analysis: Analysis) -> None:
        self.program = program
        self.analysis = analysis
        self.entries: dict[Atom, Entry] = {}
        self.relations: dict[PredKey, dict[tuple, Atom]] = {}
        self.facts: frozenset[Atom] = frozenset(program.facts)
        self.indeterminate: set[Atom] = set()  # positive atoms whose defeasible conflict has no winner
        # predicate -> bound positions -> key -> atoms (built lazily, kept up to date by _add/_remove_many)
        self._indexes: dict[PredKey, dict[tuple[int, ...], dict[tuple, list[Atom]]]] = {}

    def __contains__(self, atom: Atom) -> bool:
        return atom in self.entries

    def atoms(self, pred: PredKey) -> list[Atom]:
        return list(self.relations.get(pred, {}).values())

    def _index(self, pred: PredKey, positions: tuple[int, ...]) -> dict[tuple, list[Atom]]:
        by_pos = self._indexes.setdefault(pred, {})
        idx = by_pos.get(positions)
        if idx is None:
            idx = {}
            for atom in self.relations.get(pred, {}).values():
                idx.setdefault(tuple(atom.args[p] for p in positions), []).append(atom)
            by_pos[positions] = idx
        return idx

    def _add(self, atom: Atom, entry: Entry) -> bool:
        old = self.entries.get(atom)
        if old is not None and old.cost <= entry.cost:
            return False
        self.entries[atom] = entry
        if old is None:
            self.relations.setdefault(atom.pred, {})[atom.args] = atom
            for positions, idx in self._indexes.get(atom.pred, {}).items():
                idx.setdefault(tuple(atom.args[p] for p in positions), []).append(atom)
        return True

    def _remove_many(self, atoms) -> None:
        for atom in atoms:
            if self.entries.pop(atom, None) is not None:
                del self.relations[atom.pred][atom.args]
                for positions, idx in self._indexes.get(atom.pred, {}).items():
                    idx[tuple(atom.args[p] for p in positions)].remove(atom)

    def _share(self, other: "Model", pred: PredKey) -> None:
        """Take a final relation of `other` as is (a reused component: same content, never modified again)."""
        rel = other.relations.get(pred)
        if rel is None:
            return
        self.relations[pred] = rel
        for atom in rel.values():
            self.entries[atom] = other.entries[atom]
        if pred in other._indexes:
            self._indexes[pred] = other._indexes[pred]

    def _copy(self, other: "Model", pred: PredKey) -> None:
        """Start a relation from `other`'s content, to be modified here (a maintained component)."""
        rel = other.relations.get(pred)
        if rel is None:
            return
        self.relations[pred] = dict(rel)
        for atom in rel.values():
            self.entries[atom] = other.entries[atom]
        if pred in other._indexes:
            self._indexes[pred] = {pos: {k: list(v) for k, v in idx.items()}
                                   for pos, idx in other._indexes[pred].items()}

    def lookup(self, pattern: Atom, subst: dict) -> Iterator[Atom]:
        bound = tuple(i for i, t in enumerate(pattern.args) if not isinstance(t, Var) or t in subst)
        if not bound:
            yield from list(self.relations.get(pattern.pred, {}).values())
            return
        key = tuple(subst[t] if isinstance(t, Var) else t for t in (pattern.args[i] for i in bound))
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


def _order_class(lit) -> int:
    if isinstance(lit, Pos):
        return 0
    if isinstance(lit, Agg):
        return 1
    if isinstance(lit, Cmp):
        return 2
    return 3


class _Evaluator:
    def __init__(self, model: Model) -> None:
        self.model = model

    def _open_taint(self, agg: Agg) -> int:
        program = self.model.program
        for lit in agg.body:
            if isinstance(lit, NaoConsta):
                return 1
            if isinstance(lit, (Pos, Naf)) and not program.is_closed(lit.atom.pred):
                return 1
        return 0

    def eval_aggregate(self, agg: Agg, subst: dict) -> tuple[set, int] | None:
        """Elements and inner taint of an aggregate under `subst` (lower strata are complete)."""
        model = self.model
        inner = sorted(agg.body, key=_order_class)
        elements: set = set()
        taint = self._open_taint(agg)

        def rec(k: int, s: dict, t: int):
            nonlocal taint
            if k == len(inner):
                elements.add(tuple(_value(x, s) for x in agg.terms))
                taint = max(taint, t)
                return
            lit = inner[k]
            if isinstance(lit, Pos):
                for atom in model.lookup(lit.atom, s):
                    s2 = _unify(lit.atom, atom, s)
                    if s2 is not None:
                        rec(k + 1, s2, max(t, model.entries[atom].cost[0]))
            elif isinstance(lit, Cmp):
                if compare(lit.op, _value(lit.left, s), _value(lit.right, s)):
                    rec(k + 1, s, t)
            else:
                if _ground(lit.atom, s) not in model:
                    rec(k + 1, s, max(t, 1 if isinstance(lit, NaoConsta) else 0))

        rec(0, subst, 0)
        return elements, taint

    def _ordered_body(self, rule: Rule, delta_pos: int | None) -> list[tuple[int, object]]:
        items = list(enumerate(rule.body))
        items.sort(key=lambda it: (_order_class(it[1]), it[0] != delta_pos if delta_pos is not None else 0))
        return items

    def fire(self, rule: Rule, delta_pos: int | None, delta: dict[PredKey, set[Atom]], bound: dict | None = None):
        """Yield (head_atom, entry) for every rule instance, using `delta` at position delta_pos, with the variables
        in `bound` already fixed (rederiving one head)."""
        body = self._ordered_body(rule, delta_pos)
        model = self.model

        def rec(k: int, subst: dict, premises: list, absences: list, comps: list, aggs: list, taint0: int):
            if k == len(body):
                head = _ground(rule.head, subst)
                ordered = tuple(atom for _, atom in sorted(premises, key=lambda x: x[0]))
                taint = taint0
                size = 1 + len(absences) + len(comps) + sum(len(a[2]) + 1 for a in aggs)
                for p in ordered:
                    c = model.entries[p].cost
                    taint = max(taint, c[0])
                    size += c[1]
                if any(kind == "nao_consta" for kind, _ in absences):
                    taint = 1
                just = Justification(
                    rule.id,
                    tuple(sorted(((v.name, val) for v, val in subst.items()), key=lambda x: x[0])),
                    ordered,
                    tuple(absences),
                    tuple(comps),
                    tuple(sorted(aggs, key=lambda a: a[0])),
                )
                yield head, Entry((taint, size), just)
                return
            idx, lit = body[k]
            if isinstance(lit, Pos):
                if idx == delta_pos:
                    candidates = [a for a in delta.get(lit.atom.pred, ()) if _unify(lit.atom, a, subst) is not None]
                else:
                    candidates = model.lookup(lit.atom, subst)
                for atom in candidates:
                    s2 = _unify(lit.atom, atom, subst)
                    if s2 is None:
                        continue
                    premises.append((idx, atom))
                    yield from rec(k + 1, s2, premises, absences, comps, aggs, taint0)
                    premises.pop()
            elif isinstance(lit, Agg):
                elements, t = self.eval_aggregate(lit, subst)
                value = aggregate_value(lit.func, elements)
                if value is None:
                    return
                if isinstance(lit.result, Var) and lit.result not in subst:
                    s2 = dict(subst)
                    s2[lit.result] = value
                elif _value(lit.result, subst) == value:
                    s2 = subst
                else:
                    return
                aggs.append((idx, lit.func, tuple(sorted(elements, key=lambda e: tuple(const_key(x) for x in e))), value))
                yield from rec(k + 1, s2, premises, absences, comps, aggs, max(taint0, t))
                aggs.pop()
            elif isinstance(lit, Cmp):
                left, right = _value(lit.left, subst), _value(lit.right, subst)
                if compare(lit.op, left, right):
                    comps.append((lit.op, left, right))
                    yield from rec(k + 1, subst, premises, absences, comps, aggs, taint0)
                    comps.pop()
            else:  # Naf / NaoConsta: the target lives in an already-completed component
                target = _ground(lit.atom, subst)
                if target not in model:
                    kind = "not" if isinstance(lit, Naf) else "nao_consta"
                    absences.append((kind, target))
                    yield from rec(k + 1, subst, premises, absences, comps, aggs, taint0)
                    absences.pop()

        yield from rec(0, dict(bound or {}), [], [], [], [], 0)


# ---------------------------------------------------------------------------
# Defeasible resolution
# ---------------------------------------------------------------------------


def strict_closure(program: Program, atoms: set[Atom]) -> set[Atom]:
    """Closure of `atoms` under the strict rules whose body has only positive literals and comparisons."""
    rules = [
        r for r in program.rules
        if not r.defeasible and all(isinstance(l, (Pos, Cmp)) for l in r.body)
    ]
    known = set(atoms)
    changed = True
    while changed:
        changed = False
        for r in rules:
            for s in _match_all([l for l in r.body if isinstance(l, Pos)], known, {}):
                if all(compare(l.op, _value(l.left, s), _value(l.right, s)) for l in r.body if isinstance(l, Cmp)):
                    h = _ground(r.head, s)
                    if h not in known:
                        known.add(h)
                        changed = True
    return known


def _match_all(pos: list[Pos], known: set[Atom], subst: dict):
    if not pos:
        yield subst
        return
    first, rest = pos[0], pos[1:]
    for atom in [a for a in known if a.pred == first.atom.pred]:
        s2 = _unify(first.atom, atom, subst)
        if s2 is not None:
            yield from _match_all(rest, known, s2)


def more_specific(program: Program, r_premises: tuple, s_premises: tuple) -> bool:
    """r is at least as specific as s: s's body follows from r's body by the strict rules."""
    return set(s_premises) <= strict_closure(program, set(r_premises))


def beats(program: Program, r: tuple[Rule, Entry], s: tuple[Rule, Entry]) -> str | None:
    """Reason why instance r beats instance s, or None."""
    rr, re = r
    sr, se = s
    if rr.label and sr.label:
        if (rr.label, sr.label) in program.priorities:
            return "prioridade"
        if (sr.label, rr.label) in program.priorities:
            return None
    if more_specific(program, re.just.premises, se.just.premises) and not more_specific(
        program, se.just.premises, re.just.premises
    ):
        return "especificidade"
    return None


def _resolve_defeasible(ev: _Evaluator, model: Model, rules: list[Rule]) -> None:
    program = model.program
    instances: dict[Atom, list[tuple[Rule, Entry]]] = {}
    for rule in rules:
        for head, entry in list(ev.fire(rule, None, {})):
            instances.setdefault(head, []).append((rule, entry))
    targets = {Atom(PredKey(a.pred.name, a.pred.arity, False), a.args) for a in instances}
    for pos_atom in sorted(targets, key=str):
        neg_atom = Atom(pos_atom.pred.negated(), pos_atom.args)
        if pos_atom in model.facts or neg_atom in model.facts:
            continue  # asserted knowledge always wins (and is already in the model)
        sup = instances.get(pos_atom, [])
        att = instances.get(neg_atom, [])
        winner = None
        for side, others, atom in ((sup, att, pos_atom), (att, sup, neg_atom)):
            if not side:
                continue
            defeats = []
            ok = True
            for other in others:
                reason = None
                for mine in side:
                    reason = beats(program, mine, other)
                    if reason:
                        break
                if reason is None:
                    ok = False
                    break
                defeats.append((other[0].id, other[1].just.subst, reason))
            if ok:
                best = min(side, key=lambda it: it[1].cost)
                j = best[1].just
                entry = Entry(best[1].cost, Justification(j.rule, j.subst, j.premises, j.absences,
                                                          j.comparisons, j.aggregates, tuple(defeats)))
                if winner is None:
                    winner = (atom, entry)
                else:  # both sides beat each other (priority cycle): no winner
                    winner = "ambos"
        if winner is None or winner == "ambos":
            model.indeterminate.add(pos_atom)
        else:
            model._add(*winner)


def _maintainable(rules: list[Rule], comp, analysis: Analysis) -> bool:
    """A component maintained tuple by tuple: strict rules with positive literals, comparisons and absences (whose
    targets live in lower, already final components). Aggregates and defeasible pairs are evaluated again."""
    if any(pred.base in analysis.defeasible_of for pred in comp):
        return False
    return all(not r.defeasible and all(isinstance(lit, (Pos, Cmp, Naf, NaoConsta)) for lit in r.body)
               for r in rules)


def _diff(model: Model, reuse: Model, candidates) -> tuple[dict, set]:
    """What changed among `candidates` against the old model: grown (new or cheaper) atoms by predicate, and
    shrunk (removed or dearer) atoms."""
    grown: dict[PredKey, set[Atom]] = {}
    shrunk: set[Atom] = set()
    for atom in candidates:
        new, old = model.entries.get(atom), reuse.entries.get(atom)
        if new is not None and (old is None or new.cost < old.cost):
            grown.setdefault(atom.pred, set()).add(atom)
        elif old is not None and (new is None or new.cost > old.cost):
            shrunk.add(atom)
    return grown, shrunk


def _maintain(ev: "_Evaluator", model: Model, reuse: Model, comp, rules: list[Rule], facts: list[Atom],
              grown_in: dict, shrunk_in: set) -> set[Atom]:
    """Tuple-level maintenance of a component (DRed: delete and rederive, then semi-naive insertion).

    1. The old content is copied.
    2. Every copied atom whose best justification used a removed fact, a shrunk input, the absence of an atom that
       now exists, or an atom invalidated here is invalidated (transitively) and removed. What remains has a valid
       justification with its old cost, which is still its minimum unless a grown input or a vanished atom offers a
       cheaper one (step 4).
    3. Each invalidated atom is rederived from what remains: its own fact, or its rules fired with the head bound.
    4. New instances: rules fired with a grown input at a positive literal, or with an atom that vanished at an
       absence (``not``/``nao_consta``); then semi-naive iteration, where improvements re-enter the delta, as in
       full evaluation.
    """
    new_facts = set(facts)
    rev: dict[Atom, list[Atom]] = {}
    for pred in comp:
        model._copy(reuse, pred)
        for atom in reuse.atoms(pred):
            entry = reuse.entries[atom]
            for prem in entry.just.premises:
                rev.setdefault(prem, []).append(atom)
            for _, absent in entry.just.absences:
                rev.setdefault(absent, []).append(atom)
    invalid: set[Atom] = set()
    stack = [a for pred in comp for a in reuse.atoms(pred)
             if reuse.entries[a].just.rule is None and a not in new_facts]
    appeared = [a for atoms in grown_in.values() for a in atoms if a not in reuse.entries]
    stack += [d for a in list(shrunk_in) + appeared for d in rev.get(a, ())]
    while stack:
        a = stack.pop()
        if a in invalid:
            continue
        invalid.add(a)
        stack.extend(rev.get(a, ()))
    model._remove_many(invalid)
    touched = set(invalid)  # every atom whose entry may differ from the old model

    delta: dict[PredKey, set[Atom]] = {}
    for f in facts:
        if model._add(f, Entry(FACT_COST, Justification(None, (), (), (), ()))):
            delta.setdefault(f.pred, set()).add(f)
    by_head: dict[PredKey, list[Rule]] = {}
    for rule in rules:
        by_head.setdefault(rule.head.pred, []).append(rule)
    for atom in invalid:
        for rule in by_head.get(atom.pred, ()):
            bound = _unify(rule.head, atom, {})
            if bound is None:
                continue
            for head, entry in list(ev.fire(rule, None, {}, bound)):
                if model._add(head, entry):
                    delta.setdefault(head.pred, set()).add(head)
    vanished: dict[PredKey, list[Atom]] = {}
    for a in shrunk_in:
        if a not in model.entries:
            vanished.setdefault(a.pred, []).append(a)
    for rule in rules:
        for i, lit in enumerate(rule.body):
            if isinstance(lit, Pos) and lit.atom.pred in grown_in:
                for head, entry in list(ev.fire(rule, i, grown_in)):
                    if model._add(head, entry):
                        delta.setdefault(head.pred, set()).add(head)
            elif isinstance(lit, (Naf, NaoConsta)):
                for gone in vanished.get(lit.atom.pred, ()):
                    bound = _unify(lit.atom, gone, {})
                    if bound is None:
                        continue
                    for head, entry in list(ev.fire(rule, None, {}, bound)):
                        if model._add(head, entry):
                            delta.setdefault(head.pred, set()).add(head)
    recursive = [(rule, i) for rule in rules for i, lit in enumerate(rule.body)
                 if isinstance(lit, Pos) and lit.atom.pred in comp]
    while delta and recursive:
        new_delta: dict[PredKey, set[Atom]] = {}
        for rule, pos in recursive:
            if rule.body[pos].atom.pred not in delta:
                continue
            for head, entry in list(ev.fire(rule, pos, delta)):
                if model._add(head, entry):
                    new_delta.setdefault(head.pred, set()).add(head)
        touched.update(a for atoms in delta.values() for a in atoms)
        delta = new_delta
    touched.update(a for atoms in delta.values() for a in atoms)
    return touched


def evaluate(program: Program, analysis: Analysis | None = None, *,
             reuse: Model | None = None, affected: set[PredKey] | None = None) -> Model:
    """The perfect model of `program`.

    With `reuse` and `affected` (incremental maintenance): every component with
    no predicate in `affected` is copied from `reuse` instead of evaluated. This
    is sound only when `affected` is closed under dependency (see
    ``incremental.affected_by``) and `reuse` is the model of a program with the
    same rules, since a component's content depends only on the facts of its own
    predicates and on the components below it. An affected component that is
    without aggregates or defeasible rules is maintained tuple by tuple
    (``_maintain``); the others are evaluated again.
    """
    analysis = analysis or analyze(program)
    model = Model(program, analysis)
    model.reused_components = 0
    model.maintained_components = 0
    ev = _Evaluator(model)
    grown: dict[PredKey, set[Atom]] = {}  # changes against `reuse`, for the components above
    shrunk: set[Atom] = set()
    facts_by_pred: dict[PredKey, list[Atom]] = {}
    for f in program.facts:
        facts_by_pred.setdefault(f.pred, []).append(f)
    resolved: set[tuple[str, int]] = set()

    for ci, comp in enumerate(analysis.components):
        if reuse is not None and affected is not None and not (comp & affected):
            for pred in comp:
                model._share(reuse, pred)
            model.indeterminate |= {a for a in reuse.indeterminate if a.pred in comp}
            resolved |= {pred.base for pred in comp if pred.base in analysis.defeasible_of}
            model.reused_components += 1
            continue
        rules = analysis.rules_of[ci]
        if reuse is not None and affected is not None and _maintainable(rules, comp, analysis):
            facts = [f for pred in comp for f in facts_by_pred.get(pred, ())]
            touched = _maintain(ev, model, reuse, comp, rules, facts, grown, shrunk)
            model.maintained_components += 1
        else:
            _evaluate_component(ev, model, analysis, comp, rules, facts_by_pred, resolved)
            touched = [a for pred in comp for a in model.atoms(pred) + reuse.atoms(pred)] if reuse else []
        if reuse is not None:
            g, sh = _diff(model, reuse, touched)
            grown.update(g)
            shrunk |= sh
    return model


def _evaluate_component(ev: "_Evaluator", model: Model, analysis: Analysis, comp, rules: list[Rule],
                        facts_by_pred: dict, resolved: set) -> None:
    delta: dict[PredKey, set[Atom]] = {}
    for pred in comp:
        for f in facts_by_pred.get(pred, ()):
            if model._add(f, Entry(FACT_COST, Justification(None, (), (), (), ()))):
                delta.setdefault(pred, set()).add(f)
    for pred in comp:
        base = pred.base
        if base in analysis.defeasible_of and base not in resolved:
            # both p and -p facts must be present before deciding
            for other in (PredKey(base[0], base[1], False), PredKey(base[0], base[1], True)):
                for f in facts_by_pred.get(other, ()):
                    model._add(f, Entry(FACT_COST, Justification(None, (), (), (), ())))
            _resolve_defeasible(ev, model, analysis.defeasible_of[base])
            resolved.add(base)
    for rule in rules:
        for head, entry in list(ev.fire(rule, None, {})):
            if model._add(head, entry):
                delta.setdefault(head.pred, set()).add(head)
    recursive = [
        (rule, i) for rule in rules for i, lit in enumerate(rule.body)
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
