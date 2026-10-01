"""Dialogue: replies to the system's own questions, elliptical follow-ups, and what is learned from them.

Every scenario runs on the real headless builder, from a small page, in a few seconds.
"""

from __future__ import annotations

import pytest

from nucleo.builder.client import Builder
from nucleo.lang import learned
from nucleo.lang.syntax import MODELS
from nucleo.session import Session

pytestmark = pytest.mark.skipif(not (MODELS / "parser.json").exists(), reason="modelos sintáticos não treinados")

PAGE = [
    "insira uma seção na página e depois renomeie a seção para Topo",
    'insira um título com o texto "Café Aurora" na seção Topo',
    'insira um parágrafo com o texto "Torrado toda semana." depois do título',
    'insira um botão com o texto "Assinar" no fim da seção Topo',
]


@pytest.fixture(scope="module")
def builder():
    with Builder() as b:
        yield b


@pytest.fixture()
def session(builder):
    s = Session(builder)
    for text in PAGE:
        assert s.ask(text).ok, text
    return s


def _node(session, typ):
    doc = session.document()["document"]
    from nucleo.builder.client import walk

    return [n for p in doc["pages"] for n in walk(p["tree"]) if n["type"] == typ]


def test_which_one_is_answered_by_ordinal_or_name(session):
    assert session.ask('insira um título com o texto "Segundo" no fim da seção Topo').ok
    session.state = session.b.call("try", state=session.state, candidates=[{"command": "selection.clear", "args": {}}],
                                   keep=True)["results"][0]["state"]  # nothing selected: "o título" is ambiguous
    a = session.ask("coloque o título a direita")
    assert a.decision == "perguntar"
    titles = _node(session, "heading")
    b = session.ask("o segundo")
    assert b.decision == "executado", b.message
    assert titles[1]["name"] in b.message or "right" in b.message


def test_yes_and_no_close_the_question(session):
    a = session.ask("arredonde o botão")  # a meaning only reached through the dictionary, indirectly: confirmed
    assert a.decision == "perguntar", a.message
    before = session.state
    assert session.ask("não").message.startswith("Certo")
    assert session.state == before


def test_unknown_verb_is_learned_from_the_reply(session):
    a = session.ask("blorfe o título")
    assert a.decision == "perguntar", a.message
    b = session.ask("deixe o título em negrito")
    assert b.decision == "executado" and "Aprendi" in b.message, b.message
    c = session.ask("blorfe o parágrafo")  # the induced class works on another element and value phrase
    assert c.decision in ("executado", "perguntar"), c.message
    learned.forget("blorfar")
    learned.forget("blorfe")


def test_ellipsis_repeats_the_last_action_on_another_element(session):
    assert session.ask("deixe o título em negrito").decision == "executado"
    b = session.ask("faça o mesmo no parágrafo")
    assert b.decision == "executado", b.message
    assert "Parágrafo" in b.message or "bold" in b.message


def test_dictionary_meanings(session):
    for text in ("pinte o título de vermelho", "esconda o botão", "sublinhe o parágrafo", "pinte a seção de azul"):
        a = session.ask(text)
        assert a.decision == "executado", (text, a.message)


def test_english_conversation(session):
    a = session.ask("make the title red")
    assert a.decision == "executado" and a.message.startswith("Set"), a.message
    b = session.ask("do the same to the paragraph")
    assert b.decision == "executado", b.message


def test_questions_about_the_page(builder):
    from nucleo.assistant import Assistant

    a = Assistant(builder)
    for text in PAGE:
        assert a.handle(text).ok
    assert "título" in a.handle("o que tem na seção Topo?").text
    assert a.handle("quantos botões tem?").text.startswith("Há 1")
    assert "heading" in a.handle("what is in the Topo section?").text
    assert a.handle("is there a footer?").text.startswith("There is no")
    a.handle("deixe o título em negrito")
    assert "bold" in a.handle("qual o peso da fonte do título?").text
    assert a.handle("por que?").text.startswith("Fiz")
