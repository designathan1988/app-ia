"""Teaching words by definition: what is taught is used, what is not understood is not learned."""

from __future__ import annotations

import pytest

from nucleo.builder.scenarios import load_fixture
from nucleo.lang import learned, lexicon
from nucleo.lang.syntax import MODELS
from nucleo.lang.understand import World, understand

pytestmark = pytest.mark.skipif(not (MODELS / "parser.json").exists(), reason="modelos sintáticos não treinados")


@pytest.fixture()
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(learned, "STORE", tmp_path / "vocabulario.json")
    lexicon.load.cache_clear()
    yield World.from_document(load_fixture("aurora"), [])
    lexicon.load.cache_clear()


def test_a_taught_verb_means_its_definition(world):
    assert understand("centralize o título Title", world).decision == "perguntar"
    assert understand("centralizar significa definir o alinhamento do texto como center", world).decision == "aprendido"
    u = understand("centralize o título Title", world)
    assert u.decision == "executar"
    assert u.best.constraints == [{"kind": "style", "id": "n-title", "breakpoint": "desktop", "state": "base",
                                   "property": "text-align", "value": "center"}]


def test_a_taught_phrase_names_the_same_entity(world):
    assert understand("mude a cor de fundo da seção Hero para #fff", world).decision != "executar"
    assert understand("cor de fundo significa fundo", world).decision == "aprendido"
    u = understand("mude a cor de fundo da seção Hero para #fff", world)
    assert u.decision == "executar" and u.best.constraints[0]["property"] == "background-color"


@pytest.mark.parametrize("definition", ["blorfar significa fazer mágica", "cor de fundo significa sei lá"])
def test_what_is_not_understood_is_not_learned(world, definition):
    assert understand(definition, world).decision == "nao_entendi"
    assert not learned.verbs() and not learned.phrases()


def test_forgetting(world):
    understand("cor de fundo significa fundo", world)
    assert learned.forget("cor de fundo")
    assert understand("mude a cor de fundo da seção Hero para #fff", world).decision != "executar"


def test_a_taught_structure_is_built_whole(tmp_path, monkeypatch):
    from nucleo.builder.client import Builder, walk
    from nucleo.session import Session

    monkeypatch.setattr(learned, "STORE", tmp_path / "vocabulario.json")
    lexicon.load.cache_clear()
    with Builder() as b:
        s = Session(b)
        assert s.ask("insira uma seção na página e depois renomeie a seção para Planos").ok
        a = s.ask('card significa um artigo com um título com o texto "Plano" e um botão com o texto "Assinar"')
        assert a.decision == "aprendido"
        assert s.ask("insira um card na seção Planos").ok
        nodes = [(n["type"], n.get("text")) for n in walk(s.document()["document"]["pages"][0]["tree"])]
        assert nodes[2:] == [("article", None), ("heading", "Plano"), ("button", "Assinar")]
        assert s.ask("herói significa uma seção com um carrossel mágico").decision == "nao_entendi"
    lexicon.load.cache_clear()


def test_undone_readings_become_costlier(tmp_path, monkeypatch):
    from nucleo.lang import preferences

    monkeypatch.setattr(preferences, "STORE", tmp_path / "prefs.json")
    assert preferences.penalty("colocar", "mover") == 0.0
    preferences.kept("colocar", "mover")
    preferences.undone("colocar", "mover")
    preferences.undone("colocar", "mover")
    p = preferences.penalty("colocar", "mover")
    assert 0.9 < p <= preferences.PENALTY and preferences.penalty("colocar", "existir") == 0.0
