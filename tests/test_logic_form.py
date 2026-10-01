"""C1 (docs/plano_compreensao.md): the logical form composed from the UD tree, with robustness by alternatives.

Each development sentence (not from the frozen set) has the predicate-argument structure it means, written by
hand from UD conventions. The test asks that this structure is among the analyses within two local edits
(re-categorization or re-attachment): choosing among them is the grounding's job (C2-C3).
"""

from __future__ import annotations

import pytest

from nucleo.lang import alternatives, langs
from nucleo.lang import logic_form as lf
from nucleo.lang.syntax import MODELS

pytestmark = pytest.mark.skipif(not (MODELS / "parser.json").exists(), reason="modelos sintáticos não treinados")

PT = [
    ("centraliza o título", "centralizar(obj=titulo)"),
    ("deixe o título em negrito", "deixar(obj=titulo,obl:em=negrito)"),
    ("deixe o título verde", "deixar(obj=titulo,result=verde)"),
    ("pinte o título de vermelho", "pintar(obj=titulo,obl:de=vermelho)"),
    ("delete o título", "delete(obj=titulo)"),
    ("insira um botão na seção", "inserir(obj=botao,obl:em=secao)"),
    ("mova o parágrafo para cima", "mover(obj=paragrafo,obl:para=cima)"),
    ("renomeie a seção para Destaque", "renomear(obj=secao,obl:para=destaque)"),
    ("escreva Olá no parágrafo", "escrever(obj=ola,obl:em=paragrafo)"),
    ("mude a cor do título para azul", "mudar(obj=cor,obl:para=azul)"),
    ("o título tem que ficar azul", "ficar(result=azul,subj=titulo)"),
    ("quero o parágrafo sublinhado", "querer(obj=paragrafo,result=sublinhado)"),
    ("tire a imagem do cartão", "tirar(obj=imagem,obl:de=cartao)"),
    ("bota a legenda embaixo da foto", "botar(adv=embaixo,obj=legenda)"),
]

EN = [
    ("center the paragraph", "center(obj=paragraph)"),
    ("make the title bold", "make(obj=title,result=bold)"),
    ("make the title red", "make(obj=title,result=red)"),
    ("underline the title", "underline(obj=title)"),
    ("paint the section yellow", "paint(obj=section,result=yellow)"),
    ("move the paragraph up", "move(adv=up,obj=paragraph)"),
    ("insert a button in the section", "insert(obj=button,obl:in=section)"),
    ("put the paragraph in italic", "put(obj=paragraph,obl:in=italic)"),
    ("rename the section to Hero", "rename(obj=section,obl:to=hero)"),
    ("left align the button", "align(adv=left,obj=button)"),
    ("color the title blue", "color(obj=title,result=blue)"),
    ("hide the image in the card", "hide(obj=image)"),
    ("drag the logo into the footer", "drag(obj=logo,obl:into=footer)"),
]


def _signatures(text: str, lang: str, max_cost: float = 2.0) -> list[str]:
    with langs.use(lang):
        return [lf.signature(p) for a in alternatives.analyses(text) if a.cost <= max_cost
                for p in lf.build(a.tokens).predicates[:1]]


@pytest.mark.parametrize("text,expected", PT)
def test_portuguese_structure_is_among_the_analyses(text, expected):
    assert expected in _signatures(text, "pt")


@pytest.mark.parametrize("text,expected", EN)
def test_english_structure_is_among_the_analyses(text, expected):
    assert expected in _signatures(text, "en")


def test_the_greedy_analysis_comes_first_and_costs_nothing():
    a = alternatives.analyses("centraliza o título")
    assert a[0].cost == 0 and not a[0].edits
    assert all(x.cost >= 1 for x in a[1:])


def test_coordination_gives_two_predicates_sharing_the_act():
    with langs.use("pt"):
        s = lf.build(alternatives.analyses("apague o logo e esconda a foto")[0].tokens)
    assert [p.lemma for p in s.predicates][:2] == ["apagar", "esconder"]
    assert {p.act for p in s.predicates} == {"request"}


def test_an_assertion_is_not_a_request():
    with langs.use("pt"):
        s = lf.build(alternatives.analyses("o site é de uma cafeteria")[0].tokens)
    assert s.predicates[0].act == "assertion"


def test_negation_and_wish():
    with langs.use("pt"):
        neg = lf.build(alternatives.analyses("não apague o título")[0].tokens).predicates[0]
        wish = lf.build(alternatives.analyses("quero apagar o título")[0].tokens).predicates[0]
    assert neg.negated and neg.lemma == "apagar"
    assert wish.act == "wish" and wish.lemma == "apagar"
