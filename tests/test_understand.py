"""M5: Portuguese requests -> constraints -> planner -> the builder's expected document.

The end-to-end test is judged by the builder's own matchDocument on its scenarios (a fixed sample; the full run is
experiments/m5_requests.py). The adversarial tests check the property that matters most: what is not understood is
never executed silently.
"""

from __future__ import annotations

import random

import pytest

from nucleo.builder.client import Builder
from nucleo.builder.effects import CACHE, learn, load_model
from nucleo.builder.knowledge import load_domains
from nucleo.builder.planner import Planner
from nucleo.builder.scenarios import load_fixture, load_scenarios, start
from nucleo.lang.syntax import MODELS
from nucleo.lang.understand import World, understand

pytestmark = pytest.mark.skipif(not (MODELS / "parser.json").exists(),
                                reason="modelos sintáticos não treinados (experiments/x2_parser.py)")


@pytest.fixture(scope="module")
def aurora():
    return World.from_document(load_fixture("aurora"), ["n-title"])


@pytest.mark.parametrize("text, expected", [
    ("insira um título na seção Hero", {"kind": "added", "type": "heading", "parent": "n-hero"}),
    ("coloque um botão depois do parágrafo Intro", {"kind": "added", "type": "button", "parent": "n-hero", "index": 2}),
    ("apague o parágrafo Intro", {"kind": "removed", "id": "n-intro"}),
    ("defina a margem superior da seção Hero como 24px",
     {"kind": "style", "id": "n-hero", "property": "margin-top", "value": "24px"}),
    ("você pode mover o parágrafo Intro para o início da seção Hero?",
     {"kind": "moved", "id": "n-intro", "parent": "n-hero", "index": 0}),
    ("renomeie a seção Hero para Topo", {"kind": "field", "id": "n-hero", "field": "name", "value": "Topo"}),
    ("deixe o display da seção Plans em flex no tablet",
     {"kind": "style", "id": "n-plans", "breakpoint": "tablet", "value": "flex"}),
    ("quero que você ajuste o filtro da seção Hero para blur(4px)", {"kind": "style", "property": "filter",
                                                                    "value": "blur(4px)"}),
    ("por favor, remova isso", {"kind": "removed", "id": "n-title"}),
    ("coloque 18px no tamanho da fonte do parágrafo Intro", {"kind": "style", "property": "font-size", "value": "18px"}),
    ("mude a cor do texto do parágrafo Intro para red ao passar o mouse", {"kind": "style", "state": "hover"}),
    ("insira um título com o texto \"Oi\" na seção Hero", {"kind": "added", "text": "Oi"}),
])
def test_understands(aurora, text, expected):
    u = understand(text, aurora)
    assert u.decision == "executar", u.message
    c = u.best.constraints[0]
    assert {k: c.get(k) for k in expected} == expected, (text, c)


@pytest.mark.parametrize("text", [
    "faça alguma coisa bonita",
    "o céu está azul hoje",
    "blorfe o parágrafo Intro",  # an unknown verb
    "apague o parágrafo Zqwx",  # no such node
    "defina a margem superior da seção Hero",  # no value
    "mude a cor do texto do parágrafo Intro para #aa0000 no estado ativo e também o fundo",
])
def test_never_executes_what_it_did_not_understand(aurora, text):
    u = understand(text, aurora)
    if u.decision == "executar":
        # executing is only acceptable when every word was explained
        assert u.best.cost == 0, (text, u.message, u.best.assumptions)
    else:
        assert u.message


def test_ambiguous_reference_is_not_guessed():
    doc = load_fixture("aurora")
    world = World.from_document(doc, [])
    u = understand("apague o artigo", world)  # the fixture has several articles
    assert u.decision != "executar" or u.best.cost >= 2.5


@pytest.fixture(scope="module")
def planner():
    with Builder() as b:
        yield b, Planner(b, load_domains(), load_model() if CACHE.exists() else learn(b))


def test_sample_end_to_end_judged_by_the_builder(planner):
    from experiments.m5_requests import default_node, nodes_of, replay  # the experiment's own plumbing
    from tests.gen.requests import realize

    b, pl = planner
    domains = load_domains()
    c = {"pedidos": 0, "certo": 0, "erro": 0}
    for si, s in enumerate(load_scenarios()):
        if si % 9:
            continue
        fixture = load_fixture(s.setup["fixture"])
        try:
            st = start(b, s, fixture)
        except Exception:  # noqa: BLE001
            continue
        items = b.call("goalDiff", state=st)["items"]
        if len(items) != 1:
            continue
        defaults = {items[0]["type"]: default_node(b, domains, items[0]["type"], s.setup["locale"])} \
            if items[0]["kind"] == "added" else {}
        st = start(b, s, fixture)
        doc = b.call("stateOf", state=st)
        goal_doc = b.call("goalDocument")["document"]
        layer = (s.setup["breakpoint"], s.setup["state"])
        text = realize(items[0], nodes_of(doc["document"]), nodes_of(goal_doc), layer, random.Random(si), defaults)
        if not text:
            continue
        c["pedidos"] += 1
        u = understand(text, World.from_document(doc["document"], doc["selection"], layer))
        if u.decision != "executar":
            continue
        r = pl.solve_constraints(st, u.best.constraints)
        end = replay(b, st, r.plan) if r.solved else None
        if end is not None and not b.call("stateOf", state=end)["mismatches"]:
            c["certo"] += 1
        elif r.solved:
            c["erro"] += 1
    print(f"\n{c}")
    assert c["pedidos"] > 30
    assert c["certo"] >= 0.8 * c["pedidos"] and c["erro"] <= 0.02 * c["pedidos"]


@pytest.mark.parametrize("text, expected", [
    # accents omitted (restored through MorphoBr), typing slips tolerated
    ("insira um titulo na secao Hero", {"kind": "added", "type": "heading", "parent": "n-hero"}),
    ("coloca o titlo Title a direita", {"kind": "style", "property": "text-align", "value": "right"}),
    ("poe o paragrafo Intro na esquerda", {"kind": "style", "property": "text-align", "value": "left"}),
    # values named in Portuguese (lexicon induced from MDN pt-BR), property chosen by the element
    ("deixe o título Title negrito", {"kind": "style", "property": "font-weight", "value": "bold"}),
    # possession: "o texto de X" names X; a value glued at the end of the naming phrase
    ("deixa o conteudo do titulo Title centralizado", {"kind": "style", "property": "text-align", "value": "center"}),
    ("deixe o texto do paragrafo Intro em negrito", {"kind": "style", "id": "n-intro", "property": "font-weight"}),
    # a meaningful word is still a literal when nothing else can use it (a new name)
    ("renomeie a seção Hero para Topo", {"kind": "field", "field": "name", "value": "Topo"}),
])
def test_general_mechanisms(aurora, text, expected):
    u = understand(text, World.from_document(load_fixture("aurora"), []))
    assert u.decision == "executar", u.message
    c = u.best.constraints[0]
    assert {k: c.get(k) for k in expected} == expected, (text, c)


@pytest.mark.parametrize("text, expected", [
    # verbs grounded in the builder's own command labels (pt-BR catalog + manifest)
    ("duplique o parágrafo Intro", {"kind": "command", "command": "element.duplicate", "id": "n-intro"}),
    ("oculte o parágrafo Intro", {"kind": "command", "command": "element.toggleHidden", "id": "n-intro"}),
    ("mova o parágrafo Intro para cima", {"kind": "command", "command": "element.moveUp", "id": "n-intro"}),
    # a verb whose participle names a value ("centralizado" -> text-align: center)
    ("centralize o título Title", {"kind": "style", "property": "text-align", "value": "center"}),
    # ... or the participle of the first verb a dictionary gives for the keyword ("underline" -> "sublinhar")
    ("sublinhe o título Title", {"kind": "style", "property": "text-decoration-line", "value": "underline"}),
    # an unquoted new text after "para"/"por", even when the tagger reads it as a verb
    ("mude o texto do parágrafo Intro para Comprar", {"kind": "field", "field": "text", "value": "Comprar"}),
    ("troque o texto do título Title por Café Serra", {"kind": "field", "field": "text", "value": "Café Serra"}),
    # the value's type tells which property of the family was meant
    ("mude a fonte do título Title para 32px", {"kind": "style", "property": "font-size", "value": "32px"}),
    # a color named in Portuguese, left at the end of the owner's phrase
    ("deixe o fundo da seção Hero azul", {"kind": "style", "id": "n-hero", "property": "background-color",
                                         "value": "blue"}),
])
def test_grounded_meanings(text, expected):
    u = understand(text, World.from_document(load_fixture("aurora"), []))
    assert u.decision == "executar", (text, u.message)
    c = u.best.constraints[0]
    assert {k: c.get(k) for k in expected} == expected, (text, c)


def test_definite_phrase_is_not_a_new_element():
    """ "o título" when a title exists presupposes that title (DRT): it is never silently read as inserting one."""
    u = understand("coloque o título Title em caixa alta", World.from_document(load_fixture("aurora"), []))
    assert not (u.decision == "executar" and u.best.constraints[0]["kind"] == "added"), u.message


def test_gapping_repeats_the_verb():
    from nucleo.lang.understand import gapped_clauses

    first, second = gapped_clauses("insira um título e um parágrafo na seção Hero")
    assert first == "insira um título" and second.startswith("insira um parágrafo")
    assert gapped_clauses('por favor, mude o texto do título Title para "A e B"') is None  # "e" inside quotes
