"""Round 8: a fresh development set aimed at wrong executions (docs/plano_compreensao.md, "Falta").

Written before it was measured, on a third page (not the frozen sets' pages). Its point is what must NOT be done
as well as what must: negations, questions, ambiguous references, values without an amount, vague requests,
plus value removal, quantities, reference by text, discourse. Development set: measured clean first, then corrected
by class.

Usage: python experiments/rodada8.py [-v]
"""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from congelado import ADD, C, MV, NAME, RM, S, TXT, _match  # noqa: E402  (helpers only)

NODES = {
    "pg": ("Página", "page", None, ["ca", "cn", "rd"]),
    "ca": ("Cabeçalho", "header", "pg", ["lg", "bt"]),
    "lg": ("Logotipo", "image", "ca", []),
    "bt": ("Login", "button", "ca", []),
    "cn": ("Conteúdo", "section", "pg", ["h1", "ps", "im", "b2"]),
    "h1": ("Ofertas da semana", "heading", "cn", []),
    "ps": ("Descrição", "paragraph", "cn", []),
    "im": ("Imagem", "image", "cn", []),
    "b2": ("Ver mais", "button", "cn", []),
    "rd": ("Rodapé", "footer", "pg", ["cp"]),
    "cp": ("Copyright", "paragraph", "rd", []),
}

ITEMS = [
    # --- Portuguese ---
    ("não apague o título", "perguntar"),
    ("qual é a cor do botão Login?", "perguntar"),
    ("apaga o botão", "perguntar"),
    ("apaga o botão Login", [RM("bt")]),
    ("deixa o botão Ver mais em negrito", [S("font-weight", "bold", "b2")]),
    ("o texto da descrição precisa ficar cinza", [S("color", "gray", "ps")]),
    ("aumenta a fonte do título para 40px", [S("font-size", "40px", "h1")]),
    ("coloca uma borda no logotipo", "perguntar"),
    ("deixa a imagem com 50% de largura", [S("width", "50%", "im")]),
    ("move a imagem para depois do botão Ver mais", [MV("im", "cn")]),
    ("esconde o cabeçalho e o rodapé", [C("element.toggleHidden", "ca"), C("element.toggleHidden", "rd")]),
    ('troca "Ofertas da semana" por "Promoções"', [TXT("h1", "Promoções")]),
    ("duplica a descrição", [C("element.duplicate", "ps")]),
    ("coloca o logotipo no rodapé", [MV("lg", "rd")]),
    ("insere dois botões no rodapé", [ADD("button", "rd"), ADD("button", "rd")]),
    ("o site precisa de mais cor", "perguntar"),
    ("deixa tudo em negrito", "perguntar"),
    ("centraliza o texto de todos os parágrafos", [S("text-align", "center", "ps"), S("text-align", "center", "cp")]),
    ("Insere um título no rodapé. Depois muda a cor dele para vermelho.",
     [ADD("heading", "rd"), {"kind": "style", "property": "color", "value": "red"}]),
    ("o rodapé tem fundo escuro", "fato"),
    ("eu gosto do título", "fato"),
    ("você pode deixar o botão Login maior?", "perguntar"),
    ("remove o negrito do título", [S("font-weight", "normal", "h1")]),
    # --- English ---
    ("don't delete the heading", "perguntar"),
    ("what color is the Login button?", "perguntar"),
    ("delete the button", "perguntar"),
    ("delete the Login button", [RM("bt")]),
    ("make the Ver mais button bold", [S("font-weight", "bold", "b2")]),
    ("the description text should be gray", [S("color", "gray", "ps")]),
    ("set the heading font size to 40px", [S("font-size", "40px", "h1")]),
    ("make the image 50% wide", [S("width", "50%", "im")]),
    ("hide the header and the footer", [C("element.toggleHidden", "ca"), C("element.toggleHidden", "rd")]),
    ("duplicate the description", [C("element.duplicate", "ps")]),
    ("move the logo to the footer", [MV("lg", "rd")]),
    ("make everything bold", "perguntar"),
    ("center the text of every paragraph", [S("text-align", "center", "ps"), S("text-align", "center", "cp")]),
    ("Add a heading to the footer. Then change its color to red.",
     [ADD("heading", "rd"), {"kind": "style", "property": "color", "value": "red"}]),
    ("the footer has a dark background", "fato"),
    ("I like the heading", "fato"),
    ("remove the bold from the heading", [S("font-weight", "normal", "h1")]),
    ("can you make the Login button bigger?", "perguntar"),
    ("rename the image to Hero", [NAME("im", "Hero")]),
    ("put the Copyright text in italics", [S("font-style", "italic", "cp")]),
]


def world():
    from nucleo.lang.understand import World

    nodes = {nid: {"name": n, "type": t, "parent": par, "index": 0, "children": kids, "flags": {}, "styles": {}}
             for nid, (n, t, par, kids) in NODES.items()}
    for nid, (_, _, par, _) in NODES.items():
        if par:
            nodes[nid]["index"] = NODES[par][3].index(nid)
    return World(nodes, [])


def run(engine: str = "novo", verbose: bool = False) -> dict:
    from nucleo.lang.interpret import understand_request as new
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
