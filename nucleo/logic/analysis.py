"""Static analysis: safety, open/closed-world discipline, defeasible discipline and stratification.

A program is admitted only if:

* **Safety.**
  - Every variable in the head, in a ``not``/``nao_consta`` literal or in a
    comparison occurs in a positive body literal or is the result of an aggregate.
  - Inside an aggregate, every variable of the tuple, of comparisons and of
    absences occurs in a positive literal of the aggregate's body or is global
    (bound outside).
* **Negation discipline.**
  - ``not q`` only for CLOSED ``q``.
  - Absence over OPEN knowledge is ``nao_consta(q)``, and conclusions using it
    are PRESUMIDO.
  - No negation of strong-negation atoms.
* **Closed-world closure.** A closed predicate may only be derived from closed
  predicates: no ``nao_consta``, no aggregate over open knowledge, and not by a
  defeasible rule.
* **Defeasible discipline.**
  - A predicate pair ``p``/``-p`` that has defeasible rules has no strict rules.
    Facts are allowed and always win.
  - The bodies of those rules only use strictly lower strata, so the conflict
    between ``p`` and ``-p`` is decided once, over complete knowledge.
  - Priorities must name labelled rules.
* **Stratification.** No cycle of the dependency graph passes through a negative
  edge. Negative edges are ``not``, ``nao_consta``, any aggregate body, and the
  bodies of defeasible rules. A rejected program is reported with the cycle.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..kb.syntax import Agg, Cmp, Naf, NaoConsta, Pos, PredKey, Program, Rule, Var, body_atoms, literal_vars


class ProgramError(ValueError):
    pass


@dataclass
class Analysis:
    program: Program
    components: list[frozenset[PredKey]]  # SCCs in evaluation order (dependencies first)
    component_of: dict[PredKey, int]
    rules_of: dict[int, list[Rule]]  # component -> strict rules whose head is in it
    defeasible_of: dict[tuple[str, int], list[Rule]]  # base predicate -> defeasible rules for p and -p


def _positive_vars(lits) -> set:
    out = set()
    for lit in lits:
        if isinstance(lit, Pos):
            out |= lit.atom.vars()
        elif isinstance(lit, Agg) and isinstance(lit.result, Var):
            out.add(lit.result)
    return out


def _check_rule(rule: Rule, program: Program) -> None:
    bound = _positive_vars(rule.body)
    unsafe = rule.head.vars() - bound
    for lit in rule.body:
        if isinstance(lit, (Naf, NaoConsta, Cmp)):
            unsafe |= literal_vars(lit) - bound
        elif isinstance(lit, Agg):
            outer_bound = _positive_vars([l for l in rule.body if isinstance(l, Pos)])
            inner_bound = _positive_vars(lit.body) | outer_bound
            for inner in lit.body:
                if isinstance(inner, (Naf, NaoConsta, Cmp)):
                    unsafe |= literal_vars(inner) - inner_bound
            unsafe |= {t for t in lit.terms if isinstance(t, Var)} - inner_bound
            if isinstance(lit.result, Var) and lit.result in lit.inner_vars():
                raise ProgramError(f"variável de resultado do agregado aparece dentro dele: {rule}")
            if lit.func not in ("count",) and not lit.terms:
                raise ProgramError(f"#{lit.func} exige ao menos um termo: {rule}")
    if unsafe:
        names = ", ".join(sorted(v.name for v in unsafe))
        raise ProgramError(f"regra insegura (variáveis {names} não ligadas por literal positivo): {rule}")

    def check_negations(lits):
        for lit in lits:
            if isinstance(lit, (Naf, NaoConsta)) and lit.atom.pred.neg:
                raise ProgramError(f"negação sobre átomo de negação forte não suportada: {rule}")
            if isinstance(lit, Naf) and not program.is_closed(lit.atom.pred):
                raise ProgramError(
                    f"'not' exige predicado de mundo fechado; use nao_consta(...) para "
                    f"{lit.atom.pred.name}/{lit.atom.pred.arity} (aberto): {rule}"
                )
            if isinstance(lit, Agg):
                check_negations(lit.body)

    check_negations(rule.body)
    if program.is_closed(rule.head.pred):
        if rule.defeasible:
            raise ProgramError(f"predicado fechado {rule.head.pred} não pode ter regra derrotável: {rule}")
        for lit in rule.body:
            for inner in (lit.body if isinstance(lit, Agg) else (lit,)):
                if isinstance(inner, Cmp):
                    continue
                if isinstance(inner, NaoConsta) or not program.is_closed(inner.atom.pred):
                    raise ProgramError(
                        f"predicado fechado {rule.head.pred} não pode depender de "
                        f"conhecimento aberto ({inner}): {rule}"
                    )


def _sccs(nodes: list[PredKey], edges: dict[PredKey, set[PredKey]]) -> list[list[PredKey]]:
    """Tarjan's algorithm, iterative. SCCs come out dependencies-first for head->dependency edges."""
    index: dict[PredKey, int] = {}
    low: dict[PredKey, int] = {}
    on_stack: set[PredKey] = set()
    stack: list[PredKey] = []
    out: list[list[PredKey]] = []
    counter = 0
    for root in nodes:
        if root in index:
            continue
        work = [(root, iter(sorted(edges.get(root, ()))))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, it = work[-1]
            advanced = False
            for succ in it:
                if succ not in index:
                    index[succ] = low[succ] = counter
                    counter += 1
                    stack.append(succ)
                    on_stack.add(succ)
                    work.append((succ, iter(sorted(edges.get(succ, ())))))
                    advanced = True
                    break
                if succ in on_stack:
                    low[node] = min(low[node], index[succ])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                comp = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                out.append(comp)
    return out


def _negative_cycle(comp: set, neg_edges: set, edges: dict) -> list | None:
    """A cycle head -> dep -> ... -> head that uses a negative edge, if the SCC has one."""
    for head, dep in sorted(neg_edges):
        if head not in comp or dep not in comp:
            continue
        prev: dict = {dep: None}
        queue = [dep]
        while queue and head not in prev:
            cur = queue.pop(0)
            for nxt in sorted(edges.get(cur, ())):
                if nxt in comp and nxt not in prev:
                    prev[nxt] = cur
                    queue.append(nxt)
        path: list = []
        cur = head
        while cur is not None:
            path.append(cur)
            cur = prev.get(cur)
        path.reverse()
        return [head] + path
    return None


def analyze(program: Program) -> Analysis:
    for fact in program.facts:
        if not fact.is_ground():
            raise ProgramError(f"fato não é fechado (tem variável): {fact}")
    for rule in program.rules:
        _check_rule(rule, program)

    labels = {r.label for r in program.rules if r.label}
    for hi, lo in program.priorities:
        if hi not in labels or lo not in labels:
            raise ProgramError(f"prioridade @{hi} > @{lo} cita regra inexistente")

    defeasible_of: dict[tuple[str, int], list[Rule]] = {}
    for rule in program.rules:
        if rule.defeasible:
            defeasible_of.setdefault(rule.head.pred.base, []).append(rule)
    for rule in program.rules:
        if not rule.defeasible and rule.head.pred.base in defeasible_of:
            raise ProgramError(
                f"{rule.head.pred.name}/{rule.head.pred.arity} tem regras derrotáveis e não pode ter regra estrita: {rule}"
            )

    preds = sorted(program.predicates())
    edges: dict[PredKey, set[PredKey]] = {p: set() for p in preds}
    neg_edges: set = set()

    def add(head: PredKey, dep: PredKey, negative: bool) -> None:
        edges.setdefault(head, set()).add(dep)
        edges.setdefault(dep, set())
        if negative:
            neg_edges.add((head, dep))

    for rule in program.rules:
        heads = [rule.head.pred]
        if rule.defeasible:  # p and -p are decided together, over strictly lower knowledge
            heads = [PredKey(rule.head.pred.name, rule.head.pred.arity, False),
                     PredKey(rule.head.pred.name, rule.head.pred.arity, True)]
        for head in heads:
            for lit in rule.body:
                if isinstance(lit, Cmp):
                    continue
                negative = rule.defeasible or isinstance(lit, (Naf, NaoConsta, Agg))
                for atom in body_atoms(lit):
                    add(head, atom.pred, negative)
    preds = sorted(edges)

    comps = _sccs(preds, edges)
    for comp in comps:
        cycle = _negative_cycle(set(comp), neg_edges, edges)
        if cycle is not None:
            shown = " -> ".join(str(p) for p in cycle)
            raise ProgramError(f"programa não estratificável: ciclo por negação {shown}")

    components = [frozenset(c) for c in comps]
    component_of = {p: i for i, c in enumerate(components) for p in c}
    rules_of: dict[int, list[Rule]] = {i: [] for i in range(len(components))}
    for rule in program.rules:
        if not rule.defeasible:
            rules_of[component_of[rule.head.pred]].append(rule)
    return Analysis(program, components, component_of, rules_of, defeasible_of)
