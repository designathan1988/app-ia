"""Round 9: a fresh development set for questions, conversation, texts with discourse and English variety
(docs/plano_compreensao.md, "Depois de C6").

Written before it was measured, on a fourth page (a restaurant's site, with styles and texts set, so that questions
have something to find). Requests are checked as in the earlier rounds (the constraints executed, or that nothing
was executed when it must be asked or noted). Questions are checked on the answer the assistant gives from the
document: the words the answer must contain (the value, yes/no), or that it is not answered as a page question
(None: it is about something else, e.g. the code).

Usage: python experiments/rodada9.py [-v]
"""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from congelado import ADD, C, MV, NAME, RM, S, TXT, _match  # noqa: E402  (helpers only)

# id: (name, type, parent, children, text, styles at desktop/base)
NODES = {
    "pg": ("Página", "page", None, ["cb", "hr", "cd", "fm", "rd"], None, {}),
    "cb": ("Cabeçalho", "header", "pg", ["lg", "mn"], None, {}),
    "lg": ("Logo", "image", "cb", [], None, {}),
    "mn": ("Menu", "nav", "cb", [], None, {}),
    "hr": ("Destaque", "section", "pg", ["t1", "p1", "f1"], None, {"background-color": "#fff7ed"}),
    "t1": ("Massas frescas", "heading", "hr", [], "Massas frescas", {"color": "#b91c1c", "font-size": "48px"}),
    "p1": ("Chamada", "paragraph", "hr", [], "Feitas todos os dias", {"text-align": "center"}),
    "f1": ("Foto", "image", "hr", [], None, {}),
    "cd": ("Cardápio", "section", "pg", ["l1", "b1"], None, {}),
    "l1": ("Pratos", "list", "cd", [], None, {}),
    "b1": ("Reservar", "button", "cd", [], "Reservar mesa", {"background-color": "red", "font-weight": "bold"}),
    "fm": ("Contato", "form", "pg", ["i1", "i2", "b2"], None, {}),
    "i1": ("Email", "input", "fm", [], None, {}),
    "i2": ("Mensagem", "textarea", "fm", [], None, {}),
    "b2": ("Enviar", "button", "fm", [], "Enviar", {}),
    "rd": ("Rodapé", "footer", "pg", ["p2"], None, {}),
    "p2": ("Endereço", "paragraph", "rd", [], "Rua das Flores, 10", {}),
}

ANY = None  # (a value the engine computes: only the property and the element are checked)

REQUESTS = [
    # --- Portuguese: varied requests ---
    ("deixa o título Massas frescas menor", [S("font-size", ANY, "t1")]),
    ("muda o fundo do cardápio para bege", [S("background-color", "beige", "cd")]),
    ("tira o negrito do botão Reservar", [S("font-weight", "normal", "b1")]),
    ("o botão Enviar tem que ficar verde", [S("background-color", "green", "b2")]),
    ("põe a foto antes do título", [MV("f1", "hr")]),
    ("apaga o campo Email", [RM("i1")]),
    ("esconde a navegação", [C("element.toggleHidden", "mn")]),
    ('troca o texto do botão Enviar para "Mandar"', [TXT("b2", "Mandar")]),
    ("renomeia a seção Destaque para Abertura", [NAME("hr", "Abertura")]),
    ("insere um parágrafo no rodapé", [ADD("paragraph", "rd")]),
    ("alinha o endereço à direita", [S("text-align", "right", "p2")]),
    ("deixa o parágrafo Chamada em itálico e sublinhado",
     [S("font-style", "italic", "p1"), S("text-decoration-line", "underline", "p1")]),
    ("aumenta o espaçamento entre as letras do título", "perguntar"),
    ("muda a cor", "perguntar"),
    ("apaga tudo", "perguntar"),
    ("não esconde o logo", "perguntar"),
    ("o cardápio está ótimo", "fato"),
    # --- Portuguese: texts with discourse ---
    ("Coloca uma imagem no rodapé. Depois deixa ela com 120px de largura.",
     [ADD("image", "rd"), {"kind": "style", "property": "width", "value": "120px"}]),
    ("Insere um botão no formulário e chama ele de Limpar.",
     [ADD("button", "fm"), {"kind": "field", "field": "name", "value": "Limpar"}]),
    ("O título está muito grande. Diminui ele.", [S("font-size", ANY, "t1")]),
    ("Seleciona o botão Reservar. Agora deixa ele azul.", [S("background-color", "blue", "b1")]),
    ("Primeiro esconde o logo, depois duplica o botão Enviar.",
     [C("element.toggleHidden", "lg"), C("element.duplicate", "b2")]),
    ("Obrigado! Agora centraliza o endereço.", [S("text-align", "center", "p2")]),
    # --- English: varied requests ---
    ("make the Massas frescas heading smaller", [S("font-size", ANY, "t1")]),
    ("change the menu section background to beige", [S("background-color", "beige", "cd")]),
    ("remove the bold from the Reservar button", [S("font-weight", "normal", "b1")]),
    ("the Enviar button needs to be green", [S("background-color", "green", "b2")]),
    ("put the photo before the heading", [MV("f1", "hr")]),
    ("delete the Email field", [RM("i1")]),
    ("hide the navigation", [C("element.toggleHidden", "mn")]),
    ("change the Enviar button's text to 'Send'", [TXT("b2", "Send")]),
    ("rename the Destaque section to Opening", [NAME("hr", "Opening")]),
    ("add a paragraph to the footer", [ADD("paragraph", "rd")]),
    ("align the address paragraph to the right", [S("text-align", "right", "p2")]),
    ("make the Chamada paragraph italic and underlined",
     [S("font-style", "italic", "p1"), S("text-decoration-line", "underline", "p1")]),
    ("change the color", "perguntar"),
    ("delete everything", "perguntar"),
    ("please don't hide the logo", "perguntar"),
    ("the menu looks great", "fato"),
    ("Put an image in the footer. Then make it 120px wide.",
     [ADD("image", "rd"), {"kind": "style", "property": "width", "value": "120px"}]),
    ("Add a button to the form and name it Clear.",
     [ADD("button", "fm"), {"kind": "field", "field": "name", "value": "Clear"}]),
    ("The heading is too big. Shrink it.", [S("font-size", ANY, "t1")]),
    ("First hide the logo, then duplicate the Enviar button.",
     [C("element.toggleHidden", "lg"), C("element.duplicate", "b2")]),
    ("Thanks! Now center the address.", [S("text-align", "center", "p2")]),
]

# (question, words the answer must contain; or None: not a question about the page)
QUESTIONS = [
    ("qual é a cor do título?", ["#b91c1c"]),
    ("qual o tamanho da fonte do título Massas frescas?", ["48px"]),
    ("qual é o fundo da seção Destaque?", ["#fff7ed"]),
    ("qual o texto do botão Reservar?", ["Reservar mesa"]),
    ("o botão Reservar está em negrito?", ["Sim"]),
    ("o parágrafo Chamada está centralizado?", ["Sim"]),
    ("o endereço está centralizado?", ["Não"]),
    ("o título é azul?", ["Não", "#b91c1c"]),
    ("onde está a foto?", ["Destaque", "3"]),
    ("o que tem no formulário?", ["Email", "Mensagem", "Enviar"]),
    ("quantos botões tem na página?", ["2"]),
    ("tem rodapé?", ["Sim"]),
    ("tem vídeo na página?", ["Não"]),
    ("onde está definido createStore?", None),
    ("what color is the heading?", ["#b91c1c"]),
    ("what is the font size of the Massas frescas heading?", ["48px"]),
    ("what is the text of the Reservar button?", ["Reservar mesa"]),
    ("is the Reservar button bold?", ["Yes"]),
    ("is the address centered?", ["No"]),
    ("where is the photo?", ["Destaque", "3"]),
    ("what is in the form?", ["Email", "Mensagem", "Enviar"]),
    ("how many buttons are there?", ["2"]),
    ("is there a video on the page?", ["no"]),
    ("where is createStore defined?", None),
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
        elif acted and _match(got, [{k: v for k, v in e.items() if v is not ANY} for e in expected]):
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
            low = a.text.lower()
            outcome = "certo" if all(m.lower() in low for m in must) else "ERRADO"
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
