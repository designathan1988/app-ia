"""Round 13: a fresh development set for the classes frozen v6 left asked (docs/plano_compreensao.md, "Congelado
v6"), in other sentences, on an eighth page as the editor builds it: elements with the editor's default names
("Título", "Parágrafo 2", "Botão 2") known by the text they show, texts with hyphens, numbers and place words;
shades in English; removing a value in English; courtesy then a request in English.

Written before it was measured. Scoring as round 9.

Usage: python experiments/rodada13.py [-v]
"""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from congelado3 import ADD, ANY, C, MV, NAME, RM, S, TXT, _match  # noqa: E402,F401  (helpers only)
from congelado4 import run_questions as _rq, run_requests as _rr  # noqa: E402

NODES = {
    "pg": ("Página", "page", None, ["s1", "s2", "ft"], None, {}),
    "s1": ("Seção", "section", "pg", ["h", "p", "b", "i"], None, {}),
    "h": ("Título", "heading", "s1", [], "Bem-vindo à loja", {}),
    "p": ("Parágrafo", "paragraph", "s1", [], "Frete grátis acima de R$ 99", {}),
    "b": ("Botão", "button", "s1", [], "Compre já", {}),
    "i": ("Imagem", "image", "s1", [], None, {}),
    "s2": ("Seção 2", "section", "pg", ["h2", "p2", "b2"], None, {}),
    "h2": ("Título 2", "heading", "s2", [], "Mais vendidos", {}),
    "p2": ("Parágrafo 2", "paragraph", "s2", [], "Confira os favoritos", {"font-style": "italic"}),
    "b2": ("Botão 2", "button", "s2", [], "Ver todos", {}),
    "ft": ("Rodapé", "footer", "pg", ["p3"], None, {}),
    "p3": ("Parágrafo 3", "paragraph", "ft", [], "Loja Exemplo", {}),
}

REQUESTS = [
    # --- Portuguese ---
    ("deixa o título Bem-vindo à loja em negrito", [S("font-weight", "bold", "h")]),
    ("muda a cor do título Mais vendidos para vermelho", [S("color", "red", "h2")]),
    ("centraliza o parágrafo Frete grátis acima de R$ 99", [S("text-align", "center", "p")]),
    ('muda o texto do botão Compre já para "Comprar agora"', [TXT("b", "Comprar agora")]),
    ("apaga o botão Ver todos", [RM("b2")]),
    ("tira o itálico do parágrafo Confira os favoritos", [S("font-style", "normal", "p2")]),
    ("esconde a imagem", [C("element.toggleHidden", "i")]),
    ("duplica a segunda seção", [C("element.duplicate", "s2")]),
    ("deixa o texto Loja Exemplo cinza", [S("color", "gray", "p3")]),
    ("Obrigado! Agora sublinha o título Mais vendidos.", [S("text-decoration-line", "underline", "h2")]),
    # --- English ---
    ("make the Bem-vindo à loja heading bold", [S("font-weight", "bold", "h")]),
    ("change the Mais vendidos heading color to red", [S("color", "red", "h2")]),
    ("change the Compre já button text to 'Buy now'", [TXT("b", "Buy now")]),
    ("delete the Ver todos button", [RM("b2")]),
    ("remove the italics from the Confira os favoritos paragraph", [S("font-style", "normal", "p2")]),
    ("remove the italic from the second paragraph", [S("font-style", "normal", "p2")]),
    ("the second section background should be light gray", [S("background-color", "lightgray", "s2")]),
    ("make the Loja Exemplo text gray", [S("color", "gray", "p3")]),
    ("Thanks! Now underline the Mais vendidos heading.", [S("text-decoration-line", "underline", "h2")]),
    ("hide the image", [C("element.toggleHidden", "i")]),
]

QUESTIONS = [
    ("qual o texto do segundo botão?", ["Ver todos"]),
    ("what is the text of the first button?", ["Compre já"]),
    ("o parágrafo Confira os favoritos está em itálico?", ["Sim"]),
    ("is the Confira os favoritos paragraph italic?", ["Yes"]),
]


def _on_this_page(fn, name, items, verbose):
    import congelado4

    saved = (congelado4.NODES, getattr(congelado4, name))
    congelado4.NODES = NODES
    setattr(congelado4, name, items)
    try:
        return fn(verbose)
    finally:
        congelado4.NODES = saved[0]
        setattr(congelado4, name, saved[1])


def world():
    import congelado4

    saved = congelado4.NODES
    congelado4.NODES = NODES
    try:
        return congelado4.world()
    finally:
        congelado4.NODES = saved


if __name__ == "__main__":
    import json

    t = time.time()
    print("pedidos:", json.dumps(_on_this_page(_rr, "REQUESTS", REQUESTS, "-v" in sys.argv)),
          f"de {len(REQUESTS)} em {time.time() - t:.1f}s")
    t = time.time()
    print("perguntas:", json.dumps(_on_this_page(_rq, "QUESTIONS", QUESTIONS, "-v" in sys.argv)),
          f"de {len(QUESTIONS)} em {time.time() - t:.1f}s")
