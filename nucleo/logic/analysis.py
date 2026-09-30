"""Static analysis: safety, open/closed-world discipline and stratification.

A program is admitted only if:

* **Safety.** Every variable in the head, in a ``not``/``nao_consta`` literal or
  in a comparison also occurs in a positive body literal.
* **Negation discipline.**
  - ``not q(...)`` (negation as failure) is allowed only when ``q`` is declared
    CLOSED-world, because absence then means falsity.
  - Absence over an OPEN-world predicate must be written ``nao_consta(q(...))``,
    and every conclusion that depends on it is marked PRESUMIDO.
  - Neither form may target a strong-negation atom in this version.
* **Closed-world closure.** A closed predicate may only be derived from closed
  predicates. Otherwise its absence would not mean falsity.
* **Stratification.** No cycle of the predicate dependency graph passes through
  a negative (``not`` / ``nao_consta``) edge. A rejected program is reported
  together with the offending cycle.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..kb.syntax import Cmp, Naf, NaoConsta, Pos, PredKey, Program, Rule, literal_vars


class ProgramError(ValueError):
    pass


@dataclass
class Analysis:
    program: Program
    # strongly connected components of predicates, in evaluation (topological) order
    components: list[frozenset[PredKey]]
    component_of: dict[PredKey, int]
    rules_of: dict[int, list[Rule]]  # component index -> rules whose head is in it


def _check_rule(rule: Rule, program: Program) -> None:
    positive_vars = set()
    for lit in rule.body:
        if isinstance(lit, Pos):
            positive_vars |= lit.atom.vars()
    unsafe = rule.head.vars() - positive_vars
    for lit in rule.body:
        if not isinstance(lit, Pos):
            unsafe |= literal_vars(lit) - positive_vars
    if unsafe:
        names = ", ".join(sorted(v.name for v in unsafe))
        raise ProgramError(f"regra insegura (variáveis {names} não ligadas por literal positivo): {rule}")
    for lit in rule.body:
        if isinstance(lit, (Naf, NaoConsta)) and lit.atom.pred.neg:
            raise ProgramError(f"negação sobre átomo de negação forte não suportada: {rule}")
        if isinstance(lit, Naf) and not program.is_closed(lit.atom.pred):
            raise ProgramError(
                f"'not' exige predicado de mundo fechado; use nao_consta(...) para "
                f"{lit.atom.pred.base[0]}/{lit.atom.pred.arity} (aberto): {rule}"
            )
    if program.is_closed(rule.head.pred):
        for lit in rule.body:
            if isinstance(lit, Cmp):
                continue
            if isinstance(lit, NaoConsta) or not program.is_closed(lit.atom.pred):
                raise ProgramError(
                    f"predicado fechado {rule.head.pred} não pode depender de "
                    f"conhecimento aberto ({lit}): {rule}"
                )


def _sccs(nodes: list[PredKey], edges: dict[PredKey, set[PredKey]]) -> list[list[PredKey]]:
    """Tarjan's algorithm, iterative. Returns SCCs in reverse topological order of `edges`."""
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


def _negative_cycle(comp: set[PredKey], neg_edges: set[tuple[PredKey, PredKey]],
                    edges: dict[PredKey, set[PredKey]]) -> list[PredKey] | None:
    """A cycle head -> dep -> ... -> head that uses a negative edge, if the SCC has one."""
    for head, dep in sorted(neg_edges):
        if head not in comp or dep not in comp:
            continue
        # BFS from dep back to head, inside the component (edges point head -> dependency)
        prev: dict[PredKey, PredKey | None] = {dep: None}
        queue = [dep]
        while queue and head not in prev:
            cur = queue.pop(0)
            for nxt in sorted(edges.get(cur, ())):
                if nxt in comp and nxt not in prev:
                    prev[nxt] = cur
                    queue.append(nxt)
        path: list[PredKey] = []
        cur: PredKey | None = head
        while cur is not None:
            path.append(cur)
            cur = prev.get(cur)
        path.reverse()  # dep ... head
        return [head] + path
    return None


def analyze(program: Program) -> Analysis:
    for fact in program.facts:
        if not fact.is_ground():
            raise ProgramError(f"fato não é fechado (tem variável): {fact}")
    for rule in program.rules:
        _check_rule(rule, program)

    preds = sorted(program.predicates())
    edges: dict[PredKey, set[PredKey]] = {p: set() for p in preds}
    neg_edges: set[tuple[PredKey, PredKey]] = set()
    for rule in program.rules:
        for lit in rule.body:
            if isinstance(lit, Cmp):
                continue
            edges[rule.head.pred].add(lit.atom.pred)
            if isinstance(lit, (Naf, NaoConsta)):
                neg_edges.add((rule.head.pred, lit.atom.pred))

    comps = _sccs(preds, edges)  # dependencies come first (reverse topological of head->dep)
    for comp in comps:
        cycle = _negative_cycle(set(comp), neg_edges, edges)
        if cycle is not None:
            shown = " -> ".join(str(p) for p in cycle)
            raise ProgramError(f"programa não estratificável: ciclo por negação {shown}")

    components = [frozenset(c) for c in comps]
    component_of = {p: i for i, c in enumerate(components) for p in c}
    rules_of: dict[int, list[Rule]] = {i: [] for i in range(len(components))}
    for rule in program.rules:
        rules_of[component_of[rule.head.pred]].append(rule)
    return Analysis(program, components, component_of, rules_of)
