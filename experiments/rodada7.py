"""Round 7: a fresh development set (docs/plano_compreensao.md, "Portões medidos em 2026-10-01").

Written after the frozen set v1 failed its gate and before any correction made for this round. Same page and the
same kinds of material as the frozen set (requests in pt and en, paragraphs with several requests, discourse,
information, vague or unknown requests that must be asked), with new sentences. It is a development set: it is
measured clean first, then corrected by class (never sentence by sentence).

Usage: python experiments/rodada7.py [-v]
"""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from congelado import ADD, C, MV, NAME, RM, S, TXT, _match, world  # noqa: E402  (the page and helpers only)

ITEMS = [
    # --- Portuguese: requests ---
    ("põe o botão Assinar em negrito", [S("font-weight", "bold", "b")]),
    ("o parágrafo Intro precisa ficar azul", [S("color", "blue", "p")]),
    ("deixa a foto com 200px de altura", [S("height", "200px", "i")]),
    ("alinha à direita o texto dos créditos", [S("text-align", "right", "fp")]),
    ("o fundo do cartão tem que ser cinza", [S("background-color", "gray", "c")]),
    ("muda o tamanho da fonte do título do cartão para 20px", [S("font-size", "20px", "ct")]),
    ("coloca 16px de margem em cima do botão", [S("margin-top", "16px", "b")]),
    ("tira o logo", [RM("lg")]),
    ("exclui o parágrafo dos créditos", [RM("fp")]),
    ("esconde o cartão", [C("element.toggleHidden", "c")]),
    ("duplica a foto", [C("element.duplicate", "i")]),
    ("desce o botão", [C("element.moveDown", "b")]),
    ("insere uma imagem no rodapé", [ADD("image", "f")]),
    ("cria um botão novo dentro do cabeçalho", [ADD("button", "h")]),
    ('muda o texto do título do cartão para "Promoção"', [TXT("ct", "Promoção")]),
    ("renomeia a foto para Banner", [NAME("i", "Banner")]),
    ("move o logo para o rodapé", [MV("lg", "f")]),
    ("deixa todos os títulos em itálico", [S("font-style", "italic", "t"), S("font-style", "italic", "ct")]),
    ("apaga a primeira imagem", [RM("lg")]),
    ("pinta o último parágrafo de verde", [S("color", "green", "fp")]),
    ("sublinha o texto do cartão", [S("text-decoration-line", "underline", "cp")]),
    # --- Portuguese: vague or unknown: ask ---
    ("aumenta o texto", "perguntar"),
    ("deixa bonito", "perguntar"),
    ("muda o fundo", "perguntar"),
    ("glorpa a foto", "perguntar"),
    # --- Portuguese: information ---
    ("o rodapé está escuro", "fato"),
    ("o cliente é uma padaria", "fato"),
    # --- Portuguese: paragraphs ---
    ("Cria um botão no rodapé. Depois pinta ele de vermelho.",
     [ADD("button", "f"), {"kind": "style", "property": "color", "value": "red"}]),
    ("Esconde o logo e duplica o cartão.", [C("element.toggleHidden", "lg"), C("element.duplicate", "c")]),
    ("Deixa o parágrafo Intro em negrito e o texto dos créditos em itálico.",
     [S("font-weight", "bold", "p"), S("font-style", "italic", "fp")]),
    ("Por favor, centraliza o título Café Aurora. Valeu!", [S("text-align", "center", "t")]),
    ("O fundo do rodapé deve ser preto. O texto dos créditos tem que ficar branco.",
     [S("background-color", "black", "f"), S("color", "white", "fp")]),
    # --- English: requests ---
    ("make the Assinar button italic", [S("font-style", "italic", "b")]),
    ("the Intro paragraph should be red", [S("color", "red", "p")]),
    ("set the photo height to 200px", [S("height", "200px", "i")]),
    ("align the credits text to the right", [S("text-align", "right", "fp")]),
    ("the card background must be gray", [S("background-color", "gray", "c")]),
    ("remove the logo", [RM("lg")]),
    ("hide the card", [C("element.toggleHidden", "c")]),
    ("duplicate the photo", [C("element.duplicate", "i")]),
    ("move the button down", [C("element.moveDown", "b")]),
    ("insert an image in the footer", [ADD("image", "f")]),
    ('change the card title text to "Sale"', [TXT("ct", "Sale")]),
    ("rename the photo to Banner", [NAME("i", "Banner")]),
    ("move the logo to the footer", [MV("lg", "f")]),
    ("make every heading bold", [S("font-weight", "bold", "t"), S("font-weight", "bold", "ct")]),
    ("delete the first image", [RM("lg")]),
    ("underline the card text", [S("text-decoration-line", "underline", "cp")]),
    # --- English: vague or unknown: ask ---
    ("make it nicer", "perguntar"),
    ("change the color", "perguntar"),
    ("zorp the button", "perguntar"),
    # --- English: information ---
    ("the footer is too dark", "fato"),
    # --- English: paragraphs ---
    ("Add a button to the footer. Then paint it red.",
     [ADD("button", "f"), {"kind": "style", "property": "color", "value": "red"}]),
    ("Hide the logo and duplicate the card.", [C("element.toggleHidden", "lg"), C("element.duplicate", "c")]),
    ("Please center the Café Aurora heading. Thanks!", [S("text-align", "center", "t")]),
    ("The footer background should be black. The credits text must be white.",
     [S("background-color", "black", "f"), S("color", "white", "fp")]),
]


def run(engine: str = "novo", verbose: bool = False) -> dict:
    from nucleo.lang.interpret import understand as new
    from nucleo.lang.understand import understand as old

    w = world()
    counts = {"certo": 0, "perguntou": 0, "ERRADO": 0}
    for text, expected in ITEMS:
        u = (new if engine == "novo" else old)(text, w)
        acted = u.decision == "executar"
        got = u.best.constraints if acted and u.best else []
        if expected in ("perguntar", "fato"):
            outcome = "certo" if not acted else "ERRADO"
        elif acted and _match(got, expected):
            outcome = "certo"
        elif acted:
            outcome = "ERRADO"
        else:
            outcome = "perguntou"
        counts[outcome] += 1
        if verbose and outcome != "certo":
            print(f"[{outcome}] {text}\n    -> {u.decision}: {u.message[:160]}")
    return counts


if __name__ == "__main__":
    import json

    for eng in ("antigo", "novo"):
        t = time.time()
        print(f"motor {eng}:", json.dumps(run(eng, "-v" in sys.argv)), f"de {len(ITEMS)} em {time.time() - t:.1f}s")
