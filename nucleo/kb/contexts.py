"""Contexts (microtheories): isolated bodies of knowledge that inherit from parent contexts.

Knowledge lives in named contexts such as ``projeto``, ``sessao``,
``hipotese`` or ``web_nao_verificada``, which form a DAG. A parent is defined
before its children, so there are no cycles.

* A **view** of a context is its own knowledge plus that of every ancestor.
  Nothing flows downward-to-upward or between siblings. A hypothesis tried in
  ``hipotese`` never reaches ``projeto``, and unverified web claims are seen
  only by contexts that inherit from ``web_nao_verificada``.
* A child does **not** override a parent. Asserting ``-p`` in a child where the
  parent has ``p`` makes ``p`` CONTRADITORIO in the child's view, with both
  proofs and the conflict set. It does not silently replace the parent. An
  intended exception is written as defeasible rules with a priority, and the
  child may prioritise its own labelled rules over a parent's.
* The merged program must be admissible as a whole. A world declaration that
  disagrees across the lineage, or a label defined twice, is an error.
* Provenance: every fact and rule in a view records the context it came from,
  the nearest one when a fact is asserted in several.

This module depends only on the syntax module.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .syntax import Atom, Program, Rule, parse_program


class ContextError(ValueError):
    pass


@dataclass
class Context:
    name: str
    parents: tuple[str, ...]
    program: Program = field(default_factory=Program)


@dataclass
class View:
    context: str
    lineage: list[str]  # the context first, then ancestors, nearest first
    program: Program
    fact_origin: dict[Atom, str]
    rule_origin: dict[int, tuple[str, int]]  # merged rule id -> (context, id inside that context)


class Contexts:
    def __init__(self) -> None:
        self._ctx: dict[str, Context] = {}

    def __contains__(self, name: str) -> bool:
        return name in self._ctx

    def names(self) -> list[str]:
        return list(self._ctx)

    def parents(self, name: str) -> tuple[str, ...]:
        return self._get(name).parents

    def _get(self, name: str) -> Context:
        try:
            return self._ctx[name]
        except KeyError:
            raise ContextError(f"contexto inexistente: {name}") from None

    def define(self, name: str, parents: tuple[str, ...] | list[str] = ()) -> Context:
        if name in self._ctx:
            raise ContextError(f"contexto já existe: {name}")
        for p in parents:
            self._get(p)  # parents must exist, which rules out cycles
        ctx = Context(name, tuple(parents))
        self._ctx[name] = ctx
        return ctx

    def drop(self, name: str) -> None:
        children = [c.name for c in self._ctx.values() if name in c.parents]
        if children:
            raise ContextError(f"{name} tem contextos filhos: {children}")
        self._get(name)
        del self._ctx[name]

    def add(self, name: str, src: str) -> None:
        """Append the sentences of `src` to context `name`."""
        ctx = self._get(name)
        part = parse_program(src)
        prog = ctx.program
        base = len(prog.rules)
        rules = [Rule(base + i, r.head, r.body, r.label, r.defeasible) for i, r in enumerate(part.rules)]
        for key, world in part.worlds.items():
            if prog.worlds.get(key, world) != world:
                raise ContextError(f"{name}: mundo de {key[0]}/{key[1]} declarado de dois jeitos")
        ctx.program = Program(
            facts=prog.facts + [f for f in dict.fromkeys(part.facts) if f not in set(prog.facts)],
            rules=prog.rules + rules,
            worlds={**prog.worlds, **part.worlds},
            default_world=prog.default_world,
            priorities=prog.priorities | part.priorities,
        )

    def lineage(self, name: str) -> list[str]:
        out: list[str] = []
        frontier = [name]
        while frontier:
            nxt: list[str] = []
            for n in frontier:
                if n not in out:
                    out.append(n)
                    nxt.extend(self._get(n).parents)
            frontier = nxt
        return out

    def view(self, name: str) -> View:
        lineage = self.lineage(name)
        facts: list[Atom] = []
        fact_origin: dict[Atom, str] = {}
        for n in lineage:  # nearest first: the nearest assertion is the recorded origin
            for f in self._ctx[n].program.facts:
                if f not in fact_origin:
                    fact_origin[f] = n
                    facts.append(f)
        rules: list[Rule] = []
        rule_origin: dict[int, tuple[str, int]] = {}
        worlds: dict = {}
        world_origin: dict = {}
        label_origin: dict[str, str] = {}
        priorities: set = set()
        for n in reversed(lineage):  # roots first, so rule numbering is stable when children grow
            prog = self._ctx[n].program
            for key, world in prog.worlds.items():
                if key in worlds and worlds[key] != world:
                    raise ContextError(
                        f"{key[0]}/{key[1]} é '{worlds[key]}' em {world_origin[key]} e '{world}' em {n}"
                    )
                worlds[key] = world
                world_origin.setdefault(key, n)
            for r in prog.rules:
                if r.label:
                    if r.label in label_origin and label_origin[r.label] != n:
                        raise ContextError(f"rótulo @{r.label} definido em {label_origin[r.label]} e em {n}")
                    label_origin[r.label] = n
                rid = len(rules)
                rules.append(Rule(rid, r.head, r.body, r.label, r.defeasible))
                rule_origin[rid] = (n, r.id)
            priorities |= prog.priorities
        merged = Program(facts=facts, rules=rules, worlds=worlds, default_world="aberto", priorities=priorities)
        return View(name, lineage, merged, fact_origin, rule_origin)
