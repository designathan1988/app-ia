"""Frozen validation set for the understanding rebuild (docs/plano_compreensao.md §4).

Written before the rebuild and frozen by hash (``congelado.sha256``): it is measured at the gates only, never used
to tune. Each item is a text (a sentence, or a paragraph with several requests) and what it must mean, as a list of
expected changes in order; "perguntar" means the right answer is to ask (or say it did not understand), never to
act; "fato" means it states information, not a request.

Usage: python experiments/congelado.py [-v]
"""
from __future__ import annotations

import hashlib
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

NODES = {
    "pg": ("Página", "page", None, ["h", "s", "f"]),
    "h": ("Cabeçalho", "header", "pg", ["lg"]),
    "lg": ("Logo", "image", "h", []),
    "s": ("Topo", "section", "pg", ["t", "p", "b", "i", "c"]),
    "t": ("Café Aurora", "heading", "s", []),
    "p": ("Intro", "paragraph", "s", []),
    "b": ("Assinar", "button", "s", []),
    "i": ("Foto", "image", "s", []),
    "c": ("Cartão", "article", "s", ["ct", "cp"]),
    "ct": ("Título do cartão", "heading", "c", []),
    "cp": ("Texto do cartão", "paragraph", "c", []),
    "f": ("Rodapé", "footer", "pg", ["fp"]),
    "fp": ("Créditos", "paragraph", "f", []),
}

S = lambda prop, value, node: {"kind": "style", "property": prop, "value": value, "id": node}  # noqa: E731
C = lambda cmd, node: {"kind": "command", "command": cmd, "id": node}  # noqa: E731
ADD = lambda typ, parent=None: {"kind": "added", "type": typ, **({"parent": parent} if parent else {})}  # noqa: E731
RM = lambda node: {"kind": "removed", "id": node}  # noqa: E731
MV = lambda node, parent=None: {"kind": "moved", "id": node, **({"parent": parent} if parent else {})}  # noqa: E731
TXT = lambda node, value: {"kind": "field", "field": "text", "id": node, "value": value}  # noqa: E731
NAME = lambda node, value: {"kind": "field", "field": "name", "id": node, "value": value}  # noqa: E731

ITEMS = [
    # --- Portuguese: single requests, varied structure ---
    ("deixa o parágrafo Intro em negrito", [S("font-weight", "bold", "p")]),
    ("o botão Assinar tem que ficar verde", [S("color", "green", "b")]),
    ("quero a foto com 320px de largura", [S("width", "320px", "i")]),
    ("centraliza o título do cartão", [S("text-align", "center", "ct")]),
    ("põe o texto dos créditos em itálico", [S("font-style", "italic", "fp")]),
    ("a cor de fundo do rodapé vai ser preta", [S("background-color", "black", "f")]),
    ("o fundo do cabeçalho precisa ser cinza", [S("background-color", "gray", "h")]),
    ("muda o tamanho da fonte do parágrafo Intro para 18px", [S("font-size", "18px", "p")]),
    ("coloca 24px de margem embaixo da seção Topo", [S("margin-bottom", "24px", "s")]),
    ("alinha o texto do rodapé no centro", "perguntar"),
    ("sublinha o título Café Aurora", [S("text-decoration-line", "underline", "t")]),
    ("pinta o botão de laranja", [S("color", "orange", "b")]),
    ("apaga o logo", [RM("lg")]),
    ("remove o cartão inteiro", [RM("c")]),
    ("some com a foto", "perguntar"),
    ("esconde o rodapé", [C("element.toggleHidden", "f")]),
    ("duplica o cartão", [C("element.duplicate", "c")]),
    ("trava o cabeçalho", [C("element.toggleLock", "h")]),
    ("sobe a foto", [C("element.moveUp", "i")]),
    ("insere um botão no cabeçalho", [ADD("button", "h")]),
    ("cria um parágrafo novo dentro do cartão", [ADD("paragraph", "c")]),
    ("adiciona uma imagem antes do título Café Aurora", [ADD("image", "s")]),
    ("coloca um título no rodapé", [ADD("heading", "f")]),
    ('troca o texto do botão para "Quero assinar"', [TXT("b", "Quero assinar")]),
    ('o título do cartão deve dizer "Novidades"', [TXT("ct", "Novidades")]),
    ('escreve "Todos os direitos reservados" nos créditos', [TXT("fp", "Todos os direitos reservados")]),
    ("renomeia o cartão para Destaque", [NAME("c", "Destaque")]),
    ("muda o nome da foto pra Capa", [NAME("i", "Capa")]),
    ("move o botão para o rodapé", [MV("b", "f")]),
    ("leva a foto pro fim da seção Topo", [MV("i", "s")]),
    ("coloca o parágrafo Intro depois do botão", [MV("p", "s")]),
    ("deixa todos os parágrafos em negrito", [S("font-weight", "bold", "p"), S("font-weight", "bold", "cp"),
                                            S("font-weight", "bold", "fp")]),
    ("esconde todas as imagens", [C("element.toggleHidden", "lg"), C("element.toggleHidden", "i")]),
    ("apaga o último parágrafo", [RM("fp")]),
    ("pinta o primeiro título de azul", [S("color", "blue", "t")]),
    ("aumenta a fonte do título do cartão", "perguntar"),
    ("o título tá pequeno", "perguntar"),
    ("faz alguma coisa bonita", "perguntar"),
    ("apaga", "perguntar"),
    ("muda a cor", "perguntar"),
    ("xablau o botão", "perguntar"),
    # --- Portuguese: paragraphs with several requests ---
    ("Insere um parágrafo no rodapé. Depois deixa ele em itálico.",
     [ADD("paragraph", "f"), {"kind": "style", "property": "font-style", "value": "italic"}]),
    ("Deixa o título Café Aurora vermelho e o botão azul.", [S("color", "red", "t"), S("color", "blue", "b")]),
    ("Apaga o logo, depois esconde a foto.", [RM("lg"), C("element.toggleHidden", "i")]),
    ("Quero o fundo da seção Topo branco. O texto do Intro deve ficar preto.",
     [S("background-color", "white", "s"), S("color", "black", "p")]),
    ("Centraliza o título do cartão e coloca o texto do cartão em negrito.",
     [S("text-align", "center", "ct"), S("font-weight", "bold", "cp")]),
    ("Por favor, duplica o botão. Obrigado!", [C("element.duplicate", "b")]),
    # --- Portuguese: information, not requests ---
    ("o site é de uma cafeteria", "fato"),
    ("a cor da marca é marrom", "fato"),
    ("o botão Assinar é o mais importante da página", "fato"),
    # --- English: single requests ---
    ("make the Intro paragraph bold", [S("font-weight", "bold", "p")]),
    ("the Assinar button should be green", [S("color", "green", "b")]),
    ("i want the photo 320px wide", [S("width", "320px", "i")]),
    ("center the card title", [S("text-align", "center", "ct")]),
    ("put the credits text in italics", [S("font-style", "italic", "fp")]),
    ("the footer background color will be black", [S("background-color", "black", "f")]),
    ("set the font size of the Intro paragraph to 18px", [S("font-size", "18px", "p")]),
    ("add 24px of margin below the Topo section", [S("margin-bottom", "24px", "s")]),
    ("underline the Café Aurora heading", [S("text-decoration-line", "underline", "t")]),
    ("paint the button orange", [S("color", "orange", "b")]),
    ("delete the logo", [RM("lg")]),
    ("remove the whole card", [RM("c")]),
    ("hide the footer", [C("element.toggleHidden", "f")]),
    ("duplicate the card", [C("element.duplicate", "c")]),
    ("lock the header", [C("element.toggleLock", "h")]),
    ("move the photo up", [C("element.moveUp", "i")]),
    ("insert a button in the header", [ADD("button", "h")]),
    ("create a new paragraph inside the card", [ADD("paragraph", "c")]),
    ("add an image before the Café Aurora heading", [ADD("image", "s")]),
    ('change the button text to "Subscribe now"', [TXT("b", "Subscribe now")]),
    ('the card title should say "News"', [TXT("ct", "News")]),
    ("rename the card to Highlight", [NAME("c", "Highlight")]),
    ("move the button to the footer", [MV("b", "f")]),
    ("take the photo to the end of the Topo section", [MV("i", "s")]),
    ("make all paragraphs bold", [S("font-weight", "bold", "p"), S("font-weight", "bold", "cp"),
                                  S("font-weight", "bold", "fp")]),
    ("hide every image", [C("element.toggleHidden", "lg"), C("element.toggleHidden", "i")]),
    ("delete the last paragraph", [RM("fp")]),
    ("paint the first heading blue", [S("color", "blue", "t")]),
    ("make it pretty", "perguntar"),
    ("delete", "perguntar"),
    ("flurb the button", "perguntar"),
    # --- English: paragraphs ---
    ("Insert a paragraph in the footer. Then make it italic.",
     [ADD("paragraph", "f"), {"kind": "style", "property": "font-style", "value": "italic"}]),
    ("Make the Café Aurora heading red and the button blue.", [S("color", "red", "t"), S("color", "blue", "b")]),
    ("Delete the logo, then hide the photo.", [RM("lg"), C("element.toggleHidden", "i")]),
    ("I want the Topo section background white. The Intro text should be black.",
     [S("background-color", "white", "s"), S("color", "black", "p")]),
    ("Please duplicate the button. Thanks!", [C("element.duplicate", "b")]),
    # --- English: information ---
    ("the site is for a coffee shop", "fato"),
    ("the brand color is brown", "fato"),
]


def digest() -> str:
    text = "\n".join(f"{t!r}\t{e!r}" for t, e in ITEMS)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def world():
    from nucleo.lang.understand import World

    nodes = {nid: {"name": n, "type": t, "parent": par, "index": 0, "children": kids, "flags": {}, "styles": {}}
             for nid, (n, t, par, kids) in NODES.items()}
    for nid, (_, _, par, _) in NODES.items():
        if par:
            nodes[nid]["index"] = NODES[par][3].index(nid)
    return World(nodes, [])


def _match(got: list, expected: list) -> bool:
    if len(got) != len(expected):
        return False
    return all(all(g.get(k) == v for k, v in e.items()) for g, e in zip(got, expected))


def run_old(verbose: bool = False) -> dict:
    """The current engine: each clause understood on the same page (a paragraph's later clauses do not see the
    earlier ones' effects; 'ele' is resolved by the engine as it can)."""
    from nucleo.lang.understand import split_clauses, understand

    w = world()
    counts = {"certo": 0, "perguntou": 0, "ERRADO": 0}
    for text, expected in ITEMS:
        sentences = [s for part in text.replace("!", ".").split(".") for s in [part.strip()] if s]
        clauses = [c for s in sentences for c in split_clauses(s)]
        got, acted, refused = [], False, False
        for c in clauses:
            u = understand(c, w)
            if u.decision == "executar":
                acted = True
                got += u.best.constraints
            else:
                refused = True
        if expected in ("perguntar", "fato"):
            outcome = "certo" if not acted else "ERRADO"
        elif not refused and _match(got, expected):
            outcome = "certo"
        elif acted and not _match(got[:len(expected)], expected[:len(got)]):
            outcome = "ERRADO"
        else:
            outcome = "perguntou"
        counts[outcome] += 1
        if verbose and outcome != "certo":
            print(f"[{outcome}] {text}")
    return counts


def run_new(verbose: bool = False) -> dict:
    """The rebuilt engine (nucleo/lang/interpret.py): the whole text at once (sentences, clauses, discourse)."""
    from nucleo.lang.interpret import understand

    w = world()
    counts = {"certo": 0, "perguntou": 0, "ERRADO": 0}
    for text, expected in ITEMS:
        u = understand(text, w)
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

    stored = pathlib.Path(__file__).with_name("congelado.sha256")
    h = digest()
    if not stored.exists():
        stored.write_text(h, encoding="utf-8")
    assert stored.read_text(encoding="utf-8").strip() == h, "o conjunto congelado foi alterado"
    t = time.time()
    print("motor atual:", json.dumps(run_old("-v" in sys.argv)), f"de {len(ITEMS)} em {time.time() - t:.1f}s",
          f"(hash {h[:12]})")
    if "--novo" in sys.argv:
        t = time.time()
        print("motor novo:", json.dumps(run_new("-v" in sys.argv)), f"de {len(ITEMS)} em {time.time() - t:.1f}s")
