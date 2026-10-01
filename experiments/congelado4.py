"""Frozen validation set v4 (docs/plano_compreensao.md §4; v1, v2 and v3 were each measured once and are spent).

Written before it was ever run, on a page the engine was never developed on (a veterinary clinic's site), with
styles and texts set. Frozen by hash (``congelado4.sha256``, written on the first run, before any result is seen).
Measured at the gates only, never used to tune. Scoring as v3.

Usage: python experiments/congelado4.py [-v]
"""
from __future__ import annotations

import hashlib
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from congelado3 import ADD, ANY, C, MV, NAME, RM, S, TXT, _match  # noqa: E402,F401  (helpers only)

NODES = {
    "pg": ("Página", "page", None, ["hd", "hr", "sv", "eq", "ag", "ft"], None, {}),
    "hd": ("Cabeçalho", "header", "pg", ["lo", "nv", "tl"], None, {"background-color": "#ecfeff"}),
    "lo": ("Logo", "image", "hd", [], None, {}),
    "nv": ("Menu", "nav", "hd", [], None, {}),
    "tl": ("Telefone", "link", "hd", [], "(11) 4000-1234", {}),
    "hr": ("Boas-vindas", "section", "pg", ["h1", "p1", "ft1", "bt"], None, {}),
    "h1": ("Cuidamos do seu pet", "heading", "hr", [], "Cuidamos do seu pet", {"font-size": "44px", "color": "#0f766e"}),
    "p1": ("Apresentação", "paragraph", "hr", [], "Clínica veterinária 24 horas", {"text-align": "center"}),
    "ft1": ("Cachorro", "image", "hr", [], None, {"width": "320px"}),
    "bt": ("Agendar", "button", "hr", [], "Agendar consulta", {}),
    "sv": ("Serviços", "section", "pg", ["h2", "v1", "v2", "v3"], None, {}),
    "h2": ("O que fazemos", "heading", "sv", [], "O que fazemos", {}),
    "v1": ("Vacinação", "article", "sv", ["v1t", "v1p"], None, {}),
    "v1t": ("Título vacinação", "heading", "v1", [], "Vacinas", {}),
    "v1p": ("Texto vacinação", "paragraph", "v1", [], "Calendário completo", {}),
    "v2": ("Cirurgia", "article", "sv", ["v2t", "v2p"], None, {}),
    "v2t": ("Título cirurgia", "heading", "v2", [], "Cirurgias", {}),
    "v2p": ("Texto cirurgia", "paragraph", "v2", [], "Centro cirúrgico equipado", {}),
    "v3": ("Banho", "article", "sv", ["v3t", "v3p"], None, {}),
    "v3t": ("Título banho", "heading", "v3", [], "Banho e tosa", {}),
    "v3p": ("Texto banho", "paragraph", "v3", [], "Com hora marcada", {}),
    "eq": ("Equipe", "section", "pg", ["h3", "q1"], None, {"background-color": "#f0fdf4"}),
    "h3": ("Nossa equipe", "heading", "eq", [], "Nossa equipe", {}),
    "q1": ("Citação", "blockquote", "eq", [], "Amamos animais", {"font-style": "italic"}),
    "ag": ("Agendamento", "form", "pg", ["f1", "f2", "f3", "f4"], None, {}),
    "f1": ("Nome do tutor", "input", "ag", [], None, {}),
    "f2": ("Nome do pet", "input", "ag", [], None, {}),
    "f3": ("Observações", "textarea", "ag", [], None, {}),
    "f4": ("Confirmar", "button", "ag", [], "Confirmar", {}),
    "ft": ("Rodapé", "footer", "pg", ["en", "cp"], None, {}),
    "en": ("Endereço", "paragraph", "ft", [], "Av. Paulista, 100", {}),
    "cp": ("Copyright", "paragraph", "ft", [], "© 2026 VetBem", {"font-size": "12px"}),
}

PAD = lambda v, n, prop="padding": [S(f"{prop}-{s}", v, n) for s in ("top", "right", "bottom", "left")]  # noqa: E731

REQUESTS = [
    # --- Portuguese ---
    ("deixa o título Cuidamos do seu pet em negrito", [S("font-weight", "bold", "h1")]),
    ("muda a cor do título O que fazemos para laranja", [S("color", "orange", "h2")]),
    ("diminui o título Cuidamos do seu pet", [S("font-size", ANY, "h1")]),
    ("o fundo da seção Serviços tem que ser bege", [S("background-color", "beige", "sv")]),
    ("alinha o endereço ao centro", [S("text-align", "center", "en")]),
    ("tira o itálico da citação", [S("font-style", "normal", "q1")]),
    ("apaga a imagem Cachorro", [RM("ft1")]),
    ("esconde o telefone", [C("element.toggleHidden", "tl")]),
    ("duplica o artigo Banho", [C("element.duplicate", "v3")]),
    ("move o logo para o rodapé", [MV("lo", "ft")]),
    ('muda o texto do botão Confirmar para "Enviar pedido"', [TXT("f4", "Enviar pedido")]),
    ("renomeia a seção Equipe para Time", [NAME("eq", "Time")]),
    ("insere um parágrafo na seção Equipe", [ADD("paragraph", "eq")]),
    ("coloca uma imagem dentro do artigo Cirurgia", [ADD("image", "v2")]),
    ("sublinha o parágrafo Apresentação", [S("text-decoration-line", "underline", "p1")]),
    ("deixa o copyright cinza e em itálico", [S("color", "gray", "cp"), S("font-style", "italic", "cp")]),
    ("deixa a imagem Cachorro com 200px de largura", [S("width", "200px", "ft1")]),
    ("aumenta a imagem Cachorro", [S("width", ANY, "ft1")]),
    ("coloca 20px de padding na seção Equipe", PAD("20px", "eq")),
    ("põe uma margem de 8px embaixo do título Nossa equipe", [S("margin-bottom", "8px", "h3")]),
    ("apaga o terceiro artigo", [RM("v3")]),
    ("deixa o fundo do cabeçalho verde claro", [S("background-color", "lightgreen", "hd")]),
    ("esconde", "perguntar"),
    ("muda a fonte", "perguntar"),
    ("não apaga a citação", "perguntar"),
    ("eu adorei a página", "fato"),
    ("a clínica abre aos domingos", "fato"),
    ("pode duplicar o campo Nome do pet?", [C("element.duplicate", "f2")]),
    ("Insere um botão no rodapé. Depois chama ele de Contato.",
     [ADD("button", "ft"), {"kind": "field", "field": "name", "value": "Contato"}]),
    ("Esconde o menu e depois apaga o telefone.", [C("element.toggleHidden", "nv"), RM("tl")]),
    ("O título da equipe está pequeno. Aumenta ele.", [S("font-size", ANY, "h3")]),
    ("Valeu! Agora centraliza o título O que fazemos.", [S("text-align", "center", "h2")]),
    ("Coloca um título no rodapé e deixa ele vermelho.",
     [ADD("heading", "ft"), {"kind": "style", "property": "color", "value": "red"}]),
    # --- English ---
    ("make the Cuidamos do seu pet heading bold", [S("font-weight", "bold", "h1")]),
    ("change the O que fazemos heading color to orange", [S("color", "orange", "h2")]),
    ("make the Cuidamos do seu pet heading smaller", [S("font-size", ANY, "h1")]),
    ("the Serviços section background should be beige", [S("background-color", "beige", "sv")]),
    ("center the address", [S("text-align", "center", "en")]),
    ("remove the italics from the quote", [S("font-style", "normal", "q1")]),
    ("delete the Cachorro image", [RM("ft1")]),
    ("hide the phone link", [C("element.toggleHidden", "tl")]),
    ("duplicate the Banho article", [C("element.duplicate", "v3")]),
    ("move the logo to the footer", [MV("lo", "ft")]),
    ("change the Confirmar button text to 'Send request'", [TXT("f4", "Send request")]),
    ("rename the Equipe section to Team", [NAME("eq", "Team")]),
    ("add a paragraph to the Equipe section", [ADD("paragraph", "eq")]),
    ("underline the Apresentação paragraph", [S("text-decoration-line", "underline", "p1")]),
    ("make the copyright gray and italic", [S("color", "gray", "cp"), S("font-style", "italic", "cp")]),
    ("make the Cachorro image 200px wide", [S("width", "200px", "ft1")]),
    ("add 20px of padding to the Equipe section", PAD("20px", "eq")),
    ("delete the third article", [RM("v3")]),
    ("make the header background light green", [S("background-color", "lightgreen", "hd")]),
    ("hide", "perguntar"),
    ("change the font", "perguntar"),
    ("don't delete the quote", "perguntar"),
    ("I love this page", "fato"),
    ("Add a button to the footer. Then call it Contact.",
     [ADD("button", "ft"), {"kind": "field", "field": "name", "value": "Contact"}]),
    ("Hide the menu and then delete the phone link.", [C("element.toggleHidden", "nv"), RM("tl")]),
    ("Thanks! Now center the O que fazemos heading.", [S("text-align", "center", "h2")]),
]

QUESTIONS = [
    ("qual é a cor do título Cuidamos do seu pet?", ["#0f766e"]),
    ("qual o tamanho da fonte do copyright?", ["12px"]),
    ("qual é o fundo da seção Equipe?", ["#f0fdf4"]),
    ("qual o texto do botão Agendar?", ["Agendar consulta"]),
    ("a citação está em itálico?", ["Sim"]),
    ("o endereço está centralizado?", ["Não"]),
    ("onde está o botão Agendar?", ["Boas-vindas", "4"]),
    ("o que tem no formulário?", ["Nome do tutor", "Nome do pet", "Observações", "Confirmar"]),
    ("quantos artigos tem?", ["3"]),
    ("tem rodapé?", ["Sim"]),
    ("what color is the Cuidamos do seu pet heading?", ["#0f766e"]),
    ("what is the text of the Agendar button?", ["Agendar consulta"]),
    ("is the quote italic?", ["Yes"]),
    ("where is the Agendar button?", ["Boas-vindas", "4"]),
    ("how many articles are there?", ["3"]),
    ("onde está definido createStore?", None),
]


def digest() -> str:
    text = repr(NODES) + "\n" + "\n".join(f"{t!r}\t{e!r}" for t, e in REQUESTS) + "\n" + \
        "\n".join(f"{t!r}\t{e!r}" for t, e in QUESTIONS)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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

    stored = pathlib.Path(__file__).with_name("congelado4.sha256")
    h = digest()
    if not stored.exists():
        stored.write_text(h, encoding="utf-8")
    assert stored.read_text(encoding="utf-8").strip() == h, "o conjunto congelado foi alterado"
    t = time.time()
    print("pedidos:", json.dumps(run_requests("-v" in sys.argv)), f"de {len(REQUESTS)} em {time.time() - t:.1f}s",
          f"(hash {h[:12]})")
    t = time.time()
    print("perguntas:", json.dumps(run_questions("-v" in sys.argv)), f"de {len(QUESTIONS)} em {time.time() - t:.1f}s")
