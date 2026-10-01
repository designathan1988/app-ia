"""Round 10: a fresh development set for the general classes frozen v3 showed (docs/plano_compreensao.md,
"Congelado v3"), in other sentences, on a fifth page (a bookstore): language detection with names of the other
language, colors of two words, names with numbers, naming a created element ("chama ele de X"), "e depois" with a
removal, padding on every side, references by a plural of a name, English variety.

Written before it was measured. Scoring as round 9.

Usage: python experiments/rodada10.py [-v]
"""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from congelado3 import ADD, ANY, C, MV, NAME, RM, S, TXT, _match  # noqa: E402,F401  (helpers only)

NODES = {
    "pg": ("Página", "page", None, ["cb", "dq", "lv", "nw", "rd"], None, {}),
    "cb": ("Cabeçalho", "header", "pg", ["lg", "bs"], None, {}),
    "lg": ("Emblema", "image", "cb", [], None, {}),
    "bs": ("Busca", "input", "cb", [], None, {}),
    "dq": ("Destaques", "section", "pg", ["t", "d", "cp"], None, {}),
    "t": ("Lançamentos do mês", "heading", "dq", [], "Lançamentos do mês", {"color": "#7c2d12"}),
    "d": ("Descrição", "paragraph", "dq", [], "Novos títulos toda semana", {"font-style": "italic"}),
    "cp": ("Capa", "image", "dq", [], None, {}),
    "lv": ("Livros", "section", "pg", ["k1", "k2"], None, {}),
    "k1": ("Livro Um", "article", "lv", ["k1t", "k1a"], None, {}),
    "k1t": ("Dom Casmurro", "heading", "k1", [], "Dom Casmurro", {}),
    "k1a": ("Autor um", "paragraph", "k1", [], "Machado de Assis", {}),
    "k2": ("Livro Dois", "article", "lv", ["k2t", "k2a"], None, {}),
    "k2t": ("Vidas Secas", "heading", "k2", [], "Vidas Secas", {}),
    "k2a": ("Autor dois", "paragraph", "k2", [], "Graciliano Ramos", {}),
    "nw": ("Newsletter", "form", "pg", ["ne", "nb"], None, {}),
    "ne": ("Seu e-mail", "input", "nw", [], None, {}),
    "nb": ("Assinar", "button", "nw", [], "Assinar", {}),
    "rd": ("Rodapé", "footer", "pg", ["ri"], None, {"background-color": "#1f2937"}),
    "ri": ("Informações", "paragraph", "rd", [], "Livraria Aurora, desde 1990", {}),
}

PAD = lambda v, n: [S(f"padding-{s}", v, n) for s in ("top", "right", "bottom", "left")]  # noqa: E731

REQUESTS = [
    # --- Portuguese ---
    ("deixa o fundo dos Destaques azul claro", [S("background-color", "lightblue", "dq")]),
    ("pinta o rodapé de verde escuro", [S("background-color", "darkgreen", "rd")]),
    ("renomeia o livro Um para Livro 3", [NAME("k1", "Livro 3")]),
    ("muda o nome da capa para Capa 2", [NAME("cp", "Capa 2")]),
    ("Insere um parágrafo no rodapé e chama ele de Endereço.",
     [ADD("paragraph", "rd"), {"kind": "field", "field": "name", "value": "Endereço"}]),
    ("Adiciona uma seção na página. Depois chama ela de Eventos.",
     [ADD("section", "pg"), {"kind": "field", "field": "name", "value": "Eventos"}]),
    ("Esconde o emblema e depois apaga a busca.", [C("element.toggleHidden", "lg"), RM("bs")]),
    ("Duplica a descrição e depois esconde a capa.", [C("element.duplicate", "d"), C("element.toggleHidden", "cp")]),
    ("O título dos destaques está grande demais. Diminui ele.", [S("font-size", ANY, "t")]),
    ("coloca 12px de espaçamento interno no formulário", PAD("12px", "nw")),
    ("deixa o autor um em itálico", [S("font-style", "italic", "k1a")]),
    ("o título Dom Casmurro precisa ficar vermelho", [S("color", "red", "k1t")]),
    ("centraliza o título Lançamentos do mês", [S("text-align", "center", "t")]),
    ("apaga o segundo livro", [RM("k2")]),
    ("move a capa para dentro do livro Dois", [MV("cp", "k2")]),
    ("deixa o rodapé com texto branco", [S("color", "white", "rd")]),
    ("não esconde o rodapé", "perguntar"),
    ("a livraria é antiga", "fato"),
    ("Obrigada! Agora deixa a descrição em negrito.", [S("font-weight", "bold", "d")]),
    # --- English ---
    ("make the Destaques background light blue", [S("background-color", "lightblue", "dq")]),
    ("paint the footer dark green", [S("background-color", "darkgreen", "rd")]),
    ("rename the Livro Um article to Book 3", [NAME("k1", "Book 3")]),
    ("Add a section to the page. Then call it Events.",
     [ADD("section", "pg"), {"kind": "field", "field": "name", "value": "Events"}]),
    ("Insert a paragraph in the footer and name it Address.",
     [ADD("paragraph", "rd"), {"kind": "field", "field": "name", "value": "Address"}]),
    ("Hide the emblem and then delete the search field.", [C("element.toggleHidden", "lg"), RM("bs")]),
    ("The Lançamentos do mês heading is too big. Make it smaller.", [S("font-size", ANY, "t")]),
    ("put 12px of padding inside the form", PAD("12px", "nw")),
    ("make the Dom Casmurro heading red", [S("color", "red", "k1t")]),
    ("center the Lançamentos do mês heading", [S("text-align", "center", "t")]),
    ("delete the second book", [RM("k2")]),
    ("move the cover into the Livro Dois article", [MV("cp", "k2")]),
    ("make the Autor um paragraph italic", [S("font-style", "italic", "k1a")]),
    ("don't hide the footer", "perguntar"),
    ("the bookstore is old", "fato"),
    ("Thanks! Now make the description bold.", [S("font-weight", "bold", "d")]),
    ("set the Vidas Secas heading font size to 28px", [S("font-size", "28px", "k2t")]),
    ("give the Newsletter form a white background", [S("background-color", "white", "nw")]),
]

QUESTIONS = [
    ("qual a cor do título Lançamentos do mês?", ["#7c2d12"]),
    ("a descrição está em itálico?", ["Sim"]),
    ("quantos livros tem?", ["2"]),
    ("o que tem no livro Um?", ["Dom Casmurro", "Autor um"]),
    ("what color is the Lançamentos do mês heading?", ["#7c2d12"]),
    ("is the description italic?", ["Yes"]),
    ("what is the background of the footer?", ["#1f2937"]),
    ("where is the cover?", ["Destaques", "3"]),
    ("how many books are there?", ["2"]),
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


def run_requests(verbose: bool = False) -> dict:
    from nucleo.lang.interpret import understand_request

    w = world()
    counts = {"certo": 0, "perguntou": 0, "ERRADO": 0}
    for text, expected in REQUESTS:
        u = understand_request(text, w)
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
            print(f"[{outcome}] {text}\n    -> {u.decision}: {u.message[:200]}")
    return counts


def run_questions(verbose: bool = False) -> dict:
    from nucleo.lang.questions import answer

    w, doc = world(), document()
    counts = {"certo": 0, "sem resposta": 0, "ERRADO": 0}
    for text, must in QUESTIONS:
        a = answer(text, w, doc)
        if must is None:
            outcome = "certo" if a is None else "ERRADO"
        elif a is None:
            outcome = "sem resposta"
        else:
            outcome = "certo" if all(m.lower() in a.text.lower() for m in must) else "ERRADO"
        counts[outcome] += 1
        if verbose and outcome != "certo":
            print(f"[{outcome}] {text}\n    -> {a.text if a else None}")
    return counts


if __name__ == "__main__":
    import json

    t = time.time()
    print("pedidos:", json.dumps(run_requests("-v" in sys.argv)), f"de {len(REQUESTS)} em {time.time() - t:.1f}s")
    t = time.time()
    print("perguntas:", json.dumps(run_questions("-v" in sys.argv)), f"de {len(QUESTIONS)} em {time.time() - t:.1f}s")
