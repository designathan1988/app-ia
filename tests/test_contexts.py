"""Contexts: inheritance, isolation, provenance and the errors that keep views admissible."""

from __future__ import annotations

import random

import pytest

from nucleo.kb.contexts import ContextError, Contexts
from nucleo.kb.syntax import parse_atom, parse_program
from nucleo.logic.engine import evaluate
from nucleo.logic.status import status_of
from tests.gen.worlds import random_program


def _split(seed: int, **features):
    """A random program cut into a chain raiz <- meio <- folha (worlds in raiz, priorities in folha)."""
    rng = random.Random(seed)
    lines = str(parse_program(random_program(seed, **features))).splitlines()
    parts = {"raiz": [], "meio": [], "folha": []}
    for line in lines:
        if line.startswith("pred "):
            parts["raiz"].append(line)
        elif line.startswith("@") and " > @" in line:
            parts["folha"].append(line)
        else:
            parts[rng.choice(["raiz", "meio", "folha"])].append(line)
    return lines, parts


def _same(a, b):
    assert set(a.entries) == set(b.entries)
    assert a.indeterminate == b.indeterminate


@pytest.mark.parametrize("features", [{}, {"aggregates": True, "defeasible": True}])
def test_chain_view_equals_whole_and_ancestors_see_only_their_part(features):
    for seed in range(150):
        lines, parts = _split(seed, **features)
        kb = Contexts()
        kb.define("raiz")
        kb.define("meio", ["raiz"])
        kb.define("folha", ["meio"])
        for name, ls in parts.items():
            kb.add(name, "\n".join(ls))
        _same(evaluate(kb.view("folha").program), evaluate(parse_program("\n".join(lines))))
        _same(evaluate(kb.view("raiz").program), evaluate(parse_program("\n".join(parts["raiz"]))))
        mid = parse_program("\n".join(parts["raiz"] + parts["meio"]))
        _same(evaluate(kb.view("meio").program), evaluate(mid))


def test_siblings_are_isolated():
    kb = Contexts()
    kb.define("projeto")
    kb.define("hipotese", ["projeto"])
    kb.define("web_nao_verificada", ["projeto"])
    kb.add("projeto", "botao(salvar). visivel(X) :- botao(X).")
    kb.add("hipotese", "-visivel(salvar).")
    kb.add("web_nao_verificada", "botao(cancelar).")
    proj = evaluate(kb.view("projeto").program)
    hip = evaluate(kb.view("hipotese").program)
    web = evaluate(kb.view("web_nao_verificada").program)
    assert str(status_of(proj, parse_atom("visivel(salvar)"))) == "VERDADEIRO(inferido)"
    assert str(status_of(hip, parse_atom("visivel(salvar)"))) == "CONTRADITORIO"
    assert str(status_of(web, parse_atom("visivel(salvar)"))) == "VERDADEIRO(inferido)"
    assert parse_atom("visivel(cancelar)") in web and parse_atom("visivel(cancelar)") not in hip
    assert parse_atom("visivel(cancelar)") not in proj


def test_child_exception_by_priority_over_parent_rule():
    kb = Contexts()
    kb.define("geral")
    kb.define("local", ["geral"])
    kb.add("geral", "@normal voa(X) <~ ave(X). ave(piu).")
    kb.add("local", "@aqui -voa(X) <~ ave(X). @aqui > @normal.")
    assert str(status_of(evaluate(kb.view("geral").program), parse_atom("voa(piu)"))) == "VERDADEIRO(inferido)"
    assert str(status_of(evaluate(kb.view("local").program), parse_atom("voa(piu)"))) == "FALSO(inferido)"


def test_provenance_names_the_nearest_context():
    kb = Contexts()
    kb.define("a")
    kb.define("b", ["a"])
    kb.add("a", "p(x). q(y). r(X) :- p(X).")
    kb.add("b", "p(x). s(X) :- q(X).")
    v = kb.view("b")
    assert v.fact_origin[parse_atom("p(x)")] == "b"
    assert v.fact_origin[parse_atom("q(y)")] == "a"
    origins = {str(r.head.pred.name): v.rule_origin[r.id] for r in v.program.rules}
    assert origins == {"r": ("a", 0), "s": ("b", 0)}


def test_diamond_lineage_visits_each_ancestor_once():
    kb = Contexts()
    kb.define("topo")
    kb.define("e", ["topo"])
    kb.define("d", ["topo"])
    kb.define("baixo", ["e", "d"])
    kb.add("topo", "@r p(X) <~ q(X). q(a).")
    assert kb.lineage("baixo") == ["baixo", "e", "d", "topo"]
    assert len(kb.view("baixo").program.rules) == 1  # the shared ancestor is not duplicated


def test_errors():
    kb = Contexts()
    kb.define("a")
    with pytest.raises(ContextError):
        kb.define("a")
    with pytest.raises(ContextError):
        kb.define("b", ["nao_existe"])
    kb.define("b", ["a"])
    kb.add("a", "pred p/1 fechado.")
    kb.add("b", "pred p/1 aberto.")
    with pytest.raises(ContextError):
        kb.view("b")
    with pytest.raises(ContextError):
        kb.add("a", "pred p/1 aberto.")
    kb.define("c", ["a"])
    kb.add("a", "@r x(X) <~ y(X).")
    kb.add("c", "@r -x(X) <~ z(X).")
    with pytest.raises(ContextError):
        kb.view("c")
    with pytest.raises(ContextError):
        kb.drop("a")
    kb.drop("c")
    assert "c" not in kb
