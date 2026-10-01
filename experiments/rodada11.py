"""Round 11: a fresh development set for the general classes frozen v4 showed (docs/plano_compreensao.md,
"Congelado v4"), in other sentences, on a sixth page (a bakery): coordinated values in English, removing a value
("remove the italics from"), sides ("embaixo de", "acima de", "below", "above"), English names before the type word
with function words inside the name, "the X button text to 'Y'", "N px tall/wide", texts.

Written before it was measured. Scoring as round 9.

Usage: python experiments/rodada11.py [-v]
"""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from congelado3 import ADD, ANY, C, MV, NAME, RM, S, TXT, _match  # noqa: E402,F401  (helpers only)
from rodada10 import run_questions as _rq, run_requests as _rr  # noqa: E402

NODES = {
    "pg": ("Página", "page", None, ["tp", "sb", "pr", "fm", "rd"], None, {}),
    "tp": ("Topo", "header", "pg", ["lg", "ct"], None, {}),
    "lg": ("Logotipo", "image", "tp", [], None, {}),
    "ct": ("Fale conosco", "link", "tp", [], "Fale conosco", {}),
    "sb": ("Sobre nós", "section", "pg", ["t1", "p1", "im"], None, {}),
    "t1": ("Nossa história", "heading", "sb", [], "Nossa história", {"font-weight": "bold", "color": "brown"}),
    "p1": ("Origem", "paragraph", "sb", [], "Desde 1985", {"text-decoration-line": "underline"}),
    "im": ("Fachada", "image", "sb", [], None, {"height": "240px"}),
    "pr": ("Produtos", "section", "pg", ["k1", "k2"], None, {}),
    "k1": ("Pães", "article", "pr", ["k1t"], None, {}),
    "k1t": ("Pães artesanais", "heading", "k1", [], "Pães artesanais", {}),
    "k2": ("Doces", "article", "pr", ["k2t"], None, {}),
    "k2t": ("Doces finos", "heading", "k2", [], "Doces finos", {}),
    "fm": ("Encomendas", "form", "pg", ["i1", "b1"], None, {}),
    "i1": ("Seu nome", "input", "fm", [], None, {}),
    "b1": ("Fazer pedido", "button", "fm", [], "Fazer pedido", {}),
    "rd": ("Rodapé", "footer", "pg", ["nt", "lk"], None, {}),
    "nt": ("Nota", "paragraph", "rd", [], "Aberto todos os dias", {"font-style": "italic"}),
    "lk": ("Mapa", "link", "rd", [], "Mapa", {}),
}

REQUESTS = [
    # --- English ---
    ("make the note red and bold", [S("color", "red", "nt"), S("font-weight", "bold", "nt")]),
    ("make the Nossa história heading blue and italic", [S("color", "blue", "t1"), S("font-style", "italic", "t1")]),
    ("make the Sobre nós section background yellow", [S("background-color", "yellow", "sb")]),
    ("change the Fale conosco link color to green", [S("color", "green", "ct")]),
    ("remove the underline from the Origem paragraph", [S("text-decoration-line", "none", "p1")]),
    ("remove the bold from the Nossa história heading", [S("font-weight", "normal", "t1")]),
    ("remove the italics from the note", [S("font-style", "normal", "nt")]),
    ("change the Fazer pedido button text to 'Order now'", [TXT("b1", "Order now")]),
    ("set the Fazer pedido button's text to 'Buy'", [TXT("b1", "Buy")]),
    ("make the Fachada image 300px tall", [S("height", "300px", "im")]),
    ("make the Fachada image 500px wide", [S("width", "500px", "im")]),
    ("put a 10px margin below the Nossa história heading", [S("margin-bottom", "10px", "t1")]),
    ("add a 12px margin above the Origem paragraph", [S("margin-top", "12px", "p1")]),
    ("move the Fachada image above the Nossa história heading", [MV("im", "sb")]),
    ("delete the first article", [RM("k1")]),
    ("duplicate the second article", [C("element.duplicate", "k2")]),
    ("Add a heading to the Encomendas form. Then make it green.",
     [ADD("heading", "fm"), {"kind": "style", "property": "color", "value": "green"}]),
    ("Hide the map link and make the note bold.", [C("element.toggleHidden", "lk"), S("font-weight", "bold", "nt")]),
    # --- Portuguese ---
    ("deixa a nota vermelha e em negrito", [S("color", "red", "nt"), S("font-weight", "bold", "nt")]),
    ("deixa o título Nossa história azul e itálico", [S("color", "blue", "t1"), S("font-style", "italic", "t1")]),
    ("tira o sublinhado do parágrafo Origem", [S("text-decoration-line", "none", "p1")]),
    ("tira o itálico da nota", [S("font-style", "normal", "nt")]),
    ('muda o texto do botão Fazer pedido para "Encomendar"', [TXT("b1", "Encomendar")]),
    ("deixa a imagem Fachada com 300px de altura", [S("height", "300px", "im")]),
    ("coloca uma margem de 10px embaixo do título Nossa história", [S("margin-bottom", "10px", "t1")]),
    ("põe uma margem de 12px acima do parágrafo Origem", [S("margin-top", "12px", "p1")]),
    ("move a imagem Fachada para antes do título Nossa história", [MV("im", "sb")]),
    ("apaga o primeiro artigo", [RM("k1")]),
    ("duplica o segundo artigo", [C("element.duplicate", "k2")]),
    ("Insere um título no formulário Encomendas. Depois deixa ele verde.",
     [ADD("heading", "fm"), {"kind": "style", "property": "color", "value": "green"}]),
    ("Esconde o link Mapa e deixa a nota em negrito.", [C("element.toggleHidden", "lk"), S("font-weight", "bold", "nt")]),
    ("muda a cor do link Fale conosco para verde", [S("color", "green", "ct")]),
    ("deixa o fundo da seção Sobre nós amarelo", [S("background-color", "yellow", "sb")]),
]

QUESTIONS = [
    ("a nota está em itálico?", ["Sim"]),
    ("is the note italic?", ["Yes"]),
    ("qual a altura da imagem Fachada?", ["240px"]),
    ("what is the height of the Fachada image?", ["240px"]),
    ("o parágrafo Origem está sublinhado?", ["Sim"]),
    ("what is in the Produtos section?", ["Pães", "Doces"]),
    ("o título Nossa história está em negrito?", ["Sim"]),
    ("is the Nossa história heading brown?", ["Yes"]),
]


def document() -> dict:
    def node(nid):
        name, typ, _, kids, text, styles = NODES[nid]
        n = {"id": nid, "type": typ, "name": name, "children": [node(k) for k in kids]}
        if text is not None:
            n["text"] = text
        if styles:
            n["styles"] = {"desktop": {"base": dict(styles)}}
        return n

    return {"pages": [{"tree": node("pg")}]}


def world():
    from nucleo.lang.base import World

    return World.from_document(document(), [])


def _with_this_page(fn, items_name, items, verbose):
    import rodada10

    saved = (rodada10.NODES, getattr(rodada10, items_name))
    rodada10.NODES = NODES
    setattr(rodada10, items_name, items)
    try:
        return fn(verbose)
    finally:
        rodada10.NODES, _ = saved[0], setattr(rodada10, items_name, saved[1])


if __name__ == "__main__":
    import json

    t = time.time()
    print("pedidos:", json.dumps(_with_this_page(_rr, "REQUESTS", REQUESTS, "-v" in sys.argv)),
          f"de {len(REQUESTS)} em {time.time() - t:.1f}s")
    t = time.time()
    print("perguntas:", json.dumps(_with_this_page(_rq, "QUESTIONS", QUESTIONS, "-v" in sys.argv)),
          f"de {len(QUESTIONS)} em {time.time() - t:.1f}s")
