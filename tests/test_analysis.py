"""Static admission rules and repository hygiene (import isolation, no domain literals in the engine)."""

from __future__ import annotations

import pathlib
import re

import pytest

from nucleo.kb.syntax import ParseError, parse_program
from nucleo.logic.analysis import ProgramError, analyze

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "src, fragment",
    [
        ("p(X) :- q(Y).", "insegura"),
        ("pred q/1 aberto. p(X) :- r(X), not q(X).", "mundo fechado"),
        ("pred p/1 fechado. pred q/1 aberto. p(X) :- q(X).", "não pode depender"),
        ("pred p/1 fechado. p(X) :- r(X), nao_consta(s(X)).", "não pode depender"),
        ("pred p/1 fechado. pred q/1 fechado. p(X) :- r(X), not q(X). q(X) :- r(X), not p(X).",
         "não pode depender"),
        ("pred p/1 fechado. pred q/1 fechado. pred r/1 fechado. "
         "p(X) :- r(X), not q(X). q(X) :- r(X), not p(X).", "não estratificável"),
        ("p(X) :- r(X), not -q(X).", "negação forte"),
    ],
)
def test_rejected_programs(src, fragment):
    with pytest.raises(ProgramError) as err:
        analyze(parse_program(src))
    assert fragment in str(err.value)


def test_cycle_is_shown():
    src = "pred p/1 fechado. pred q/1 fechado. pred r/1 fechado. p(X) :- r(X), not q(X). q(X) :- p(X)."
    with pytest.raises(ProgramError) as err:
        analyze(parse_program(src))
    assert "p/1" in str(err.value) and "q/1" in str(err.value)


@pytest.mark.parametrize("src", ["p(X).", "p(a) :- .", "not(a).", "p(a", 'p("x).'])
def test_parse_errors(src):
    with pytest.raises((ParseError, ProgramError)):
        analyze(parse_program(src))


def _imports(path: pathlib.Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r"^\s*(?:from|import)\s+([\w.]+)", text, flags=re.M))


def test_checker_does_not_import_engine():
    for f in (ROOT / "nucleo" / "check").glob("*.py"):
        for mod in _imports(f):
            assert "logic" not in mod, f"{f.name} importa {mod}: o checador deve ser independente"


def test_oracles_and_generator_do_not_import_engine():
    for folder in ("oracle", "gen"):
        for f in (ROOT / "tests" / folder).glob("*.py"):
            for mod in _imports(f):
                assert not mod.startswith("nucleo.logic") and not mod.startswith("nucleo.check"), (
                    f"{folder}/{f.name} importa {mod}"
                )


def test_generator_computes_no_answers():
    text = (ROOT / "tests" / "gen" / "worlds.py").read_text(encoding="utf-8")
    for forbidden in ("perfect_model", "evaluate", "answer_set", "status"):
        assert forbidden not in text, f"gerador contém '{forbidden}'"
