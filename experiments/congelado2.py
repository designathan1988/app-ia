"""Frozen validation set v2 (docs/plano_compreensao.md §4; v1 was measured once and is partly seen).

Written before it was ever run, on a page the engine was never developed on (other names, other structure), and
frozen by hash (``congelado2.sha256``). Measured at the gates only, never used to tune. Same scoring as v1: a
list of expected changes in order; "perguntar" = must not act (ask or say it did not understand); "fato" = it
states information, must not act.

Usage: python experiments/congelado2.py [-v]
"""
from __future__ import annotations

import hashlib
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

NODES = {
    "pg": ("Página", "page", None, ["br", "pr", "bs"]),
    "br": ("Barra", "header", "pg", ["mc", "en"]),
    "mc": ("Marca", "image", "br", []),
    "en": ("Entrar", "button", "br", []),
    "pr": ("Principal", "section", "pg", ["bv", "rs", "bn", "of"]),
    "bv": ("Bem-vindo", "heading", "pr", []),
    "rs": ("Resumo", "paragraph", "pr", []),
    "bn": ("Banner", "image", "pr", []),
    "of": ("Oferta", "article", "pr", ["ot", "od", "oc"]),
    "ot": ("Título da oferta", "heading", "of", []),
    "od": ("Detalhes", "paragraph", "of", []),
    "oc": ("Comprar", "button", "of", []),
    "bs": ("Base", "footer", "pg", ["ct", "sl"]),
    "ct": ("Contato", "paragraph", "bs", []),
    "sl": ("Selo", "image", "bs", []),
}

S = lambda prop, value, node: {"kind": "style", "property": prop, "value": value, "id": node}  # noqa: E731
C = lambda cmd, node: {"kind": "command", "command": cmd, "id": node}  # noqa: E731
ADD = lambda typ, parent=None: {"kind": "added", "type": typ, **({"parent": parent} if parent else {})}  # noqa: E731
RM = lambda node: {"kind": "removed", "id": node}  # noqa: E731
MV = lambda node, parent=None: {"kind": "moved", "id": node, **({"parent": parent} if parent else {})}  # noqa: E731
TXT = lambda node, value: {"kind": "field", "field": "text", "id": node, "value": value}  # noqa: E731
NAME = lambda node, value: {"kind": "field", "field": "name", "id": node, "value": value}  # noqa: E731

ITEMS = [
    # --- Portuguese: single requests ---
    ("deixa o parágrafo Resumo em itálico", [S("font-style", "italic", "rs")]),
    ("o botão Entrar tem que ficar vermelho", [S("color", "red", "en")]),
    ("quero o banner com 600px de largura", [S("width", "600px", "bn")]),
    ("centraliza o título da oferta", [S("text-align", "center", "ot")]),
    ("põe o texto do contato em negrito", [S("font-weight", "bold", "ct")]),
    ("a cor de fundo da base vai ser cinza", [S("background-color", "gray", "bs")]),
    ("o fundo da barra precisa ser branco", [S("background-color", "white", "br")]),
    ("muda o tamanho da fonte do parágrafo Detalhes para 14px", [S("font-size", "14px", "od")]),
    ("coloca 32px de margem embaixo da seção Principal", [S("margin-bottom", "32px", "pr")]),
    ("sublinha o título Bem-vindo", [S("text-decoration-line", "underline", "bv")]),
    ("pinta o botão Comprar de verde", [S("color", "green", "oc")]),
    ("apaga o selo", [RM("sl")]),
    ("remove a oferta inteira", [RM("of")]),
    ("esconde a barra", [C("element.toggleHidden", "br")]),
    ("duplica o banner", [C("element.duplicate", "bn")]),
    ("trava a base", [C("element.toggleLock", "bs")]),
    ("sobe o banner", [C("element.moveUp", "bn")]),
    ("insere um parágrafo na barra", [ADD("paragraph", "br")]),
    ("cria uma imagem nova dentro da oferta", [ADD("image", "of")]),
    ("coloca um botão no rodapé", [ADD("button", "bs")]),
    ('troca o texto do botão Comprar para "Garantir"', [TXT("oc", "Garantir")]),
    ('o título da oferta deve dizer "Só hoje"', [TXT("ot", "Só hoje")]),
    ('escreve "Fale conosco" no parágrafo Contato', [TXT("ct", "Fale conosco")]),
    ("renomeia a oferta para Promoção", [NAME("of", "Promoção")]),
    ("muda o nome do banner pra Capa", [NAME("bn", "Capa")]),
    ("move o botão Entrar para a base", [MV("en", "bs")]),
    ("leva o selo pro fim da seção Principal", [MV("sl", "pr")]),
    ("deixa todos os botões em negrito", [S("font-weight", "bold", "en"), S("font-weight", "bold", "oc")]),
    ("esconde todas as imagens", [C("element.toggleHidden", "mc"), C("element.toggleHidden", "bn"),
                                  C("element.toggleHidden", "sl")]),
    ("apaga o último parágrafo", [RM("ct")]),
    ("pinta o primeiro título de laranja", [S("color", "orange", "bv")]),
    # --- Portuguese: ask ---
    ("aumenta o tamanho do botão", "perguntar"),
    ("deixa a página mais moderna", "perguntar"),
    ("tira a cor", "perguntar"),
    ("blimpa o banner", "perguntar"),
    ("pinta o botão", "perguntar"),
    # --- Portuguese: paragraphs ---
    ("Cria um parágrafo na base. Depois deixa ele em negrito.",
     [ADD("paragraph", "bs"), {"kind": "style", "property": "font-weight", "value": "bold"}]),
    ("Deixa o título Bem-vindo azul e o botão Entrar preto.", [S("color", "blue", "bv"), S("color", "black", "en")]),
    ("Apaga o selo, depois duplica o banner.", [RM("sl"), C("element.duplicate", "bn")]),
    ("Quero o fundo da barra preto. O texto do Resumo deve ficar cinza.",
     [S("background-color", "black", "br"), S("color", "gray", "rs")]),
    ("Por favor, esconde a oferta. Obrigado!", [C("element.toggleHidden", "of")]),
    # --- Portuguese: information ---
    ("a loja vende livros", "fato"),
    ("o banner é a imagem mais importante", "fato"),
    # --- English: single requests ---
    ("make the Resumo paragraph italic", [S("font-style", "italic", "rs")]),
    ("the Entrar button should be red", [S("color", "red", "en")]),
    ("i want the banner 600px wide", [S("width", "600px", "bn")]),
    ("center the offer title", [S("text-align", "center", "ot")]),
    ("put the contact text in bold", [S("font-weight", "bold", "ct")]),
    ("the footer background color will be gray", [S("background-color", "gray", "bs")]),
    ("set the font size of the Detalhes paragraph to 14px", [S("font-size", "14px", "od")]),
    ("underline the Bem-vindo heading", [S("text-decoration-line", "underline", "bv")]),
    ("paint the Comprar button green", [S("color", "green", "oc")]),
    ("delete the seal", [RM("sl")]),
    ("hide the header", [C("element.toggleHidden", "br")]),
    ("duplicate the banner", [C("element.duplicate", "bn")]),
    ("lock the footer", [C("element.toggleLock", "bs")]),
    ("move the banner up", [C("element.moveUp", "bn")]),
    ("insert a paragraph in the header", [ADD("paragraph", "br")]),
    ('change the Comprar button text to "Get it"', [TXT("oc", "Get it")]),
    ("rename the offer to Deal", [NAME("of", "Deal")]),
    ("move the Entrar button to the footer", [MV("en", "bs")]),
    ("make all buttons bold", [S("font-weight", "bold", "en"), S("font-weight", "bold", "oc")]),
    ("delete the last paragraph", [RM("ct")]),
    # --- English: ask ---
    ("make it better", "perguntar"),
    ("change the size", "perguntar"),
    ("blorp the banner", "perguntar"),
    # --- English: paragraphs ---
    ("Create a paragraph in the footer. Then make it bold.",
     [ADD("paragraph", "bs"), {"kind": "style", "property": "font-weight", "value": "bold"}]),
    ("Make the Bem-vindo heading blue and the Entrar button black.",
     [S("color", "blue", "bv"), S("color", "black", "en")]),
    ("Delete the seal, then duplicate the banner.", [RM("sl"), C("element.duplicate", "bn")]),
    ("Please hide the offer. Thanks!", [C("element.toggleHidden", "of")]),
    # --- English: information ---
    ("the store sells books", "fato"),
]


def digest() -> str:
    text = "\n".join(f"{t!r}\t{e!r}" for t, e in ITEMS) + "\n" + repr(NODES)
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


def run(engine: str, verbose: bool = False) -> dict:
    from nucleo.lang.interpret import understand as new
    from nucleo.lang.understand import understand as old

    w = world()
    counts = {"certo": 0, "perguntou": 0, "ERRADO": 0}
    for text, expected in ITEMS:
        if engine == "novo":
            u = new(text, w)
            acted = u.decision == "executar"
            got = u.best.constraints if acted and u.best else []
            refused = not acted
        else:
            from nucleo.lang.understand import split_clauses

            sentences = [s for part in text.replace("!", ".").split(".") for s in [part.strip()] if s]
            got, acted, refused = [], False, False
            for c in [c for s in sentences for c in split_clauses(s)]:
                u = old(c, w)
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
            print(f"[{engine}:{outcome}] {text}")
    return counts


if __name__ == "__main__":
    import json

    stored = pathlib.Path(__file__).with_name("congelado2.sha256")
    h = digest()
    if not stored.exists():
        stored.write_text(h, encoding="utf-8")
    assert stored.read_text(encoding="utf-8").strip() == h, "o conjunto congelado v2 foi alterado"
    if "--hash" in sys.argv:
        print(h)
        sys.exit(0)
    for eng in ("antigo", "novo"):
        t = time.time()
        print(f"motor {eng}:", json.dumps(run(eng, "-v" in sys.argv)), f"de {len(ITEMS)} em {time.time() - t:.1f}s",
              f"(hash {h[:12]})")
