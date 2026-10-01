"""Round 12: a fresh development set for the general classes frozen v5 showed (docs/plano_compreensao.md,
"Congelado v5"), in other sentences, on a seventh page (a travel agency): ordinals and numbers over a class of names
("o segundo pacote", "package 3"), names with function or interrogative words ("Quem somos", "Destinos em alta",
"Onde estamos"), a name that is also a type word in the other language ("caption" for «Legenda»), new names that
contain the name of another element, comparatives on the dimension an element has set, padding and sides.

Written before it was measured. Scoring as round 9.

Usage: python experiments/rodada12.py [-v]
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
    "pg": ("Página", "page", None, ["tp", "ds", "qs", "oe", "ct", "rd"], None, {}),
    "tp": ("Topo", "header", "pg", ["mr", "lg"], None, {}),
    "mr": ("Marca", "image", "tp", [], None, {"height": "40px"}),
    "lg": ("Login", "link", "tp", [], "Entrar", {}),
    "ds": ("Destinos", "section", "pg", ["h1", "ps", "p1", "p2", "p3"], None, {}),
    "h1": ("Destinos em alta", "heading", "ds", [], "Destinos em alta", {}),
    "ps": ("Resumo", "paragraph", "ds", [], "Pacotes para todo o Brasil", {}),
    "p1": ("Pacote 1", "article", "ds", ["p1t"], None, {}),
    "p1t": ("Nordeste", "heading", "p1", [], "Nordeste", {}),
    "p2": ("Pacote 2", "article", "ds", ["p2t"], None, {}),
    "p2t": ("Sul", "heading", "p2", [], "Sul", {}),
    "p3": ("Pacote 3", "article", "ds", ["p3t"], None, {}),
    "p3t": ("Norte", "heading", "p3", [], "Norte", {}),
    "qs": ("Quem somos", "section", "pg", ["qh", "lgd"], None, {}),
    "qh": ("Nossa agência", "heading", "qs", [], "Nossa agência", {}),
    "lgd": ("Legenda", "paragraph", "qs", [], "Desde 2001", {"font-style": "italic"}),
    "oe": ("Onde estamos", "section", "pg", ["mp"], None, {}),
    "mp": ("Mapa", "image", "oe", [], None, {"height": "200px"}),
    "ct": ("Contato", "form", "pg", ["em", "bt"], None, {}),
    "em": ("Email", "input", "ct", [], None, {}),
    "bt": ("Enviar", "button", "ct", [], "Enviar", {}),
    "rd": ("Rodapé", "footer", "pg", ["cp"], None, {}),
    "cp": ("Copyright", "paragraph", "rd", [], "© Viagens Sol", {"font-size": "12px"}),
}

PAD = lambda v, n: [S(f"padding-{s}", v, n) for s in ("top", "right", "bottom", "left")]  # noqa: E731

REQUESTS = [
    # --- Portuguese ---
    ("apaga o segundo pacote", [RM("p2")]),
    ("duplica o pacote 3", [C("element.duplicate", "p3")]),
    ("deixa o título do pacote 1 em itálico", [S("font-style", "italic", "p1t")]),
    ("deixa o título Destinos em alta em negrito", [S("font-weight", "bold", "h1")]),
    ("muda a cor do título Nossa agência para azul", [S("color", "blue", "qh")]),
    ("renomeia o formulário Contato para Contato direto", [NAME("ct", "Contato direto")]),
    ("renomeia o resumo para Resumo da página", [NAME("ps", "Resumo da página")]),
    ("diminui a marca", [S("height", ANY, "mr")]),
    ("aumenta o mapa", [S("height", ANY, "mp")]),
    ("coloca 30px de padding na seção Onde estamos", PAD("30px", "oe")),
    ("põe uma margem de 10px em cima do título Nossa agência", [S("margin-top", "10px", "qh")]),
    ("coloca 20px de padding na seção Quem somos", PAD("20px", "qs")),
    ("esconde a seção Onde estamos", [C("element.toggleHidden", "oe")]),
    ("tira o itálico da legenda", [S("font-style", "normal", "lgd")]),
    ("Seleciona o pacote 2. Depois apaga ele.", [{"kind": "selected", "id": "p2"}, RM("p2")]),
    # --- English ---
    ("delete the second package", [RM("p2")]),
    ("duplicate package 3", [C("element.duplicate", "p3")]),
    ("make the package 1 heading italic", [S("font-style", "italic", "p1t")]),
    ("make the Destinos em alta heading bold", [S("font-weight", "bold", "h1")]),
    ("rename the Contato form to Direct contact", [NAME("ct", "Direct contact")]),
    ("make the Marca image smaller", [S("height", ANY, "mr")]),
    ("make the map bigger", [S("height", ANY, "mp")]),
    ("add 30px of padding to the Onde estamos section", PAD("30px", "oe")),
    ("put a 10px margin above the Nossa agência heading", [S("margin-top", "10px", "qh")]),
    ("hide the Onde estamos section", [C("element.toggleHidden", "oe")]),
    ("remove the italics from the caption", [S("font-style", "normal", "lgd")]),
    ("delete package 3", [RM("p3")]),
]

QUESTIONS = [
    ("quantos pacotes tem?", ["3"]),
    ("how many packages are there?", ["3"]),
    ("onde está o pacote 2?", ["Destinos", "4"]),
    ("where is package 2?", ["Destinos", "4"]),
    ("a legenda está em itálico?", ["Sim"]),
    ("is the caption italic?", ["Yes"]),
    ("qual a altura do mapa?", ["200px"]),
    ("what is the height of the map?", ["200px"]),
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
