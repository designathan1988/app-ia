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
