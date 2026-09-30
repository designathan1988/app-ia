"""Questions about code in Portuguese, answered by the code knowledge (whose references match TypeScript's own
findReferences; see test_code_world.py)."""

from __future__ import annotations

import json

import pytest

from nucleo.code.ts_extract import extract
from nucleo.lang.code_questions import CodeIndex, answer, is_code_question
from tests.test_code_world import TS_TRICKY


@pytest.fixture(scope="module")
def index(tmp_path_factory):
    d = tmp_path_factory.mktemp("tsq")
    (d / "tsconfig.json").write_text(json.dumps({"compilerOptions": {"strict": True, "target": "ES2022",
                                                 "module": "ESNext", "moduleResolution": "bundler", "noEmit": True,
                                                 "lib": ["ES2022", "DOM"]}, "include": ["src"]}), encoding="utf-8")
    (d / "package.json").write_text("{}", encoding="utf-8")
    for name, src in TS_TRICKY.items():
        (d / name).parent.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(src, encoding="utf-8")
    return CodeIndex(str(d), "tsconfig.json")


def test_definition(index):
    a = answer("onde está definido hoisted?", index)
    assert a.kind == "definicao" and a.text == "hoisted está definido em src/a.ts:3."


def test_uses_follow_imports_and_reexports(index):
    a = answer("quem usa total?", index)
    assert a.kind == "usos" and {f for f, _ in a.items} == {"src/c.ts"}


def test_impact_is_transitive(index):
    a = answer("o que é afetado se eu mudar shared?", index)
    names = {n for n, _ in a.items}
    assert {"total", "again"} <= names  # b.total uses shared; c.again uses total


def test_unused_exports(index):
    a = answer("quais exportações não são usadas?", index)
    assert "again" in {n for n, _ in a.items}


@pytest.mark.parametrize("q", ["insira um título na seção Hero", "defina o fundo da seção Hero como red"])
def test_not_a_question_about_this_code(index, q):
    assert not is_code_question(q, index)


def test_known_name_unknown_question_is_not_guessed(index):
    assert answer("hoisted é bonito?", index).kind == "nao_entendi"


def test_a_code_question_about_a_missing_name_says_so(index):
    assert is_code_question("quem chama fooBarInexistente?", index)
    assert answer("quem chama fooBarInexistente?", index).kind == "nao_entendi"
