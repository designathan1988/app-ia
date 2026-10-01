"""Frozen validation set v3 (docs/plano_compreensao.md §4; v1 and v2 were each measured once and are spent).

Written before it was ever run, on a page the engine was never developed on (a gym's site, other names, other
structure, styles and texts set so that questions have something to find). Frozen by hash (``congelado3.sha256``,
written on the first run, before any result is seen). Measured at the gates only, never used to tune.

Requests: a list of expected changes in order (ANY: a value the engine computes, only property and element are
checked); "perguntar" = must not act; "fato" = information, must not act. Questions: words the answer must contain,
or None when it is not a question about the page.

Usage: python experiments/congelado3.py [-v]
"""
from __future__ import annotations

import hashlib
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# id: (name, type, parent, children, text, styles at desktop/base)
NODES = {
    "pg": ("Página", "page", None, ["tp", "sv", "pl", "dp", "ct", "rp"], None, {}),
    "tp": ("Topo", "header", "pg", ["lg", "mn", "bt"], None, {}),
    "lg": ("Marca", "image", "tp", [], None, {}),
    "mn": ("Navegação", "nav", "tp", [], None, {}),
    "bt": ("Matricule-se", "button", "tp", [], "Matricule-se", {"background-color": "orange", "color": "white"}),
    "sv": ("Serviços", "section", "pg", ["h1", "s1", "s2", "im"], None, {"background-color": "#f8fafc"}),
    "h1": ("Nossos serviços", "heading", "sv", [], "Nossos serviços", {"color": "#1d4ed8", "font-size": "40px"}),
    "s1": ("Musculação", "paragraph", "sv", [], "Treino com acompanhamento", {"font-weight": "bold"}),
    "s2": ("Natação", "paragraph", "sv", [], "Piscina aquecida", {}),
    "im": ("Piscina", "image", "sv", [], None, {}),
    "pl": ("Planos", "section", "pg", ["h2", "c1", "c2"], None, {}),
    "h2": ("Planos e preços", "heading", "pl", [], "Planos e preços", {}),
    "c1": ("Plano Básico", "article", "pl", ["c1t", "c1p"], None, {}),
    "c1t": ("Básico", "heading", "c1", [], "Básico", {}),
    "c1p": ("Preço básico", "paragraph", "c1", [], "R$ 99", {}),
    "c2": ("Plano Completo", "article", "pl", ["c2t", "c2p"], None, {}),
    "c2t": ("Completo", "heading", "c2", [], "Completo", {}),
    "c2p": ("Preço completo", "paragraph", "c2", [], "R$ 149", {}),
    "dp": ("Depoimentos", "section", "pg", ["q1"], None, {}),
    "q1": ("Depoimento da Ana", "blockquote", "dp", [], "Mudou minha vida", {}),
    "ct": ("Contato", "form", "pg", ["nm", "em", "ms", "ev"], None, {}),
    "nm": ("Nome", "input", "ct", [], None, {}),
    "em": ("E-mail", "input", "ct", [], None, {}),
    "ms": ("Mensagem", "textarea", "ct", [], None, {}),
    "ev": ("Enviar", "button", "ct", [], "Enviar", {}),
    "rp": ("Rodapé", "footer", "pg", ["cr", "ld"], None, {"background-color": "#111827"}),
    "cr": ("Direitos", "paragraph", "rp", [], "© 2026 Academia Forte", {"text-align": "center"}),
    "ld": ("Instagram", "link", "rp", [], "Instagram", {}),
}

ANY = None
S = lambda prop, value, node: {"kind": "style", "property": prop, "value": value, "id": node}  # noqa: E731
C = lambda cmd, node: {"kind": "command", "command": cmd, "id": node}  # noqa: E731
ADD = lambda typ, parent=None: {"kind": "added", "type": typ, **({"parent": parent} if parent else {})}  # noqa: E731
RM = lambda node: {"kind": "removed", "id": node}  # noqa: E731
MV = lambda node, parent=None: {"kind": "moved", "id": node, **({"parent": parent} if parent else {})}  # noqa: E731
TXT = lambda node, value: {"kind": "field", "field": "text", "id": node, "value": value}  # noqa: E731
NAME = lambda node, value: {"kind": "field", "field": "name", "id": node, "value": value}  # noqa: E731

REQUESTS = [
    # --- Portuguese ---
    ("deixa o título Nossos serviços em itálico", [S("font-style", "italic", "h1")]),
    ("muda a cor do título Planos e preços para verde", [S("color", "green", "h2")]),
    ("aumenta o título Nossos serviços", [S("font-size", ANY, "h1")]),
    ("o fundo da seção Planos tem que ser cinza claro", [S("background-color", "lightgray", "pl")]),
    ("centraliza o parágrafo Natação", [S("text-align", "center", "s2")]),
    ("tira o negrito da Musculação", [S("font-weight", "normal", "s1")]),
    ("coloca 24px de espaço interno na seção Depoimentos",
     [S("padding-top", "24px", "dp"), S("padding-right", "24px", "dp"), S("padding-bottom", "24px", "dp"),
      S("padding-left", "24px", "dp")]),
    ("apaga a imagem Piscina", [RM("im")]),
    ("esconde o link Instagram", [C("element.toggleHidden", "ld")]),
    ("duplica o plano Completo", [C("element.duplicate", "c2")]),
    ("move a marca para o rodapé", [MV("lg", "rp")]),
    ('muda o texto do botão Enviar para "Quero treinar"', [TXT("ev", "Quero treinar")]),
    ("renomeia o depoimento da Ana para Depoimento 1", [NAME("q1", "Depoimento 1")]),
    ("insere um parágrafo na seção Depoimentos", [ADD("paragraph", "dp")]),
    ("adiciona uma imagem dentro do plano Básico", [ADD("image", "c1")]),
    ("sublinha o link Instagram", [S("text-decoration-line", "underline", "ld")]),
    ("deixa o preço básico em negrito e vermelho", [S("font-weight", "bold", "c1p"), S("color", "red", "c1p")]),
    ("alinha o título Planos e preços à esquerda", [S("text-align", "left", "h2")]),
    ("deixa a imagem Piscina com 300px de largura", [S("width", "300px", "im")]),
    ("apaga", "perguntar"),
    ("muda o tamanho", "perguntar"),
    ("não duplica o plano Básico", "perguntar"),
    ("eu acho o rodapé muito escuro", "fato"),
    ("o site está ficando bonito", "fato"),
    ("pode apagar o campo Nome?", [RM("nm")]),
    ("Insere um título no rodapé. Depois deixa ele branco.",
     [ADD("heading", "rp"), {"kind": "style", "property": "color", "value": "white"}]),
    ("Cria uma seção nova na página e chama ela de Galeria.",
     [ADD("section", "pg"), {"kind": "field", "field": "name", "value": "Galeria"}]),
    ("Esconde a navegação e depois apaga a marca.", [C("element.toggleHidden", "mn"), RM("lg")]),
    ("O título dos planos está pequeno. Aumenta ele.", [S("font-size", ANY, "h2")]),
    ("Valeu! Agora sublinha o parágrafo Natação.", [S("text-decoration-line", "underline", "s2")]),
    ("Seleciona o plano Completo. Depois duplica ele.", [{"kind": "selected", "id": "c2"},
                                                         C("element.duplicate", "c2")]),
    # --- English ---
    ("make the Nossos serviços heading italic", [S("font-style", "italic", "h1")]),
    ("change the Planos e preços heading color to green", [S("color", "green", "h2")]),
    ("make the Nossos serviços heading bigger", [S("font-size", ANY, "h1")]),
    ("the Planos section background must be light gray", [S("background-color", "lightgray", "pl")]),
    ("center the Natação paragraph", [S("text-align", "center", "s2")]),
    ("remove the bold from Musculação", [S("font-weight", "normal", "s1")]),
    ("delete the Piscina image", [RM("im")]),
    ("hide the Instagram link", [C("element.toggleHidden", "ld")]),
    ("duplicate the Completo plan", [C("element.duplicate", "c2")]),
    ("move the logo to the footer", [MV("lg", "rp")]),
    ("change the text of the Enviar button to 'Join now'", [TXT("ev", "Join now")]),
    ("add a paragraph to the Depoimentos section", [ADD("paragraph", "dp")]),
    ("underline the Instagram link", [S("text-decoration-line", "underline", "ld")]),
    ("make the basic price bold and red", [S("font-weight", "bold", "c1p"), S("color", "red", "c1p")]),
    ("align the Planos e preços heading to the left", [S("text-align", "left", "h2")]),
    ("make the Piscina image 300px wide", [S("width", "300px", "im")]),
    ("delete", "perguntar"),
    ("change the size", "perguntar"),
    ("don't duplicate the Básico plan", "perguntar"),
    ("I think the footer is too dark", "fato"),
    ("could you delete the Nome field?", [RM("nm")]),
    ("Add a heading to the footer. Then make it white.",
     [ADD("heading", "rp"), {"kind": "style", "property": "color", "value": "white"}]),
    ("Create a new section on the page and call it Gallery.",
     [ADD("section", "pg"), {"kind": "field", "field": "name", "value": "Gallery"}]),
    ("Hide the navigation and then delete the logo.", [C("element.toggleHidden", "mn"), RM("lg")]),
    ("The plans heading is small. Make it bigger.", [S("font-size", ANY, "h2")]),
    ("Thanks! Now underline the Natação paragraph.", [S("text-decoration-line", "underline", "s2")]),
]

QUESTIONS = [
    ("qual é a cor do título Nossos serviços?", ["#1d4ed8"]),
    ("qual o tamanho da fonte do título Nossos serviços?", ["40px"]),
    ("qual é o fundo do rodapé?", ["#111827"]),
    ("qual o texto do parágrafo Natação?", ["Piscina aquecida"]),
    ("a Musculação está em negrito?", ["Sim"]),
    ("o parágrafo Direitos está centralizado?", ["Sim"]),
    ("o parágrafo Natação está centralizado?", ["Não"]),
    ("onde está a imagem Piscina?", ["Serviços", "4"]),
    ("o que tem no plano Básico?", ["Básico", "Preço básico"]),
    ("quantos planos tem?", ["2"]),
    ("tem formulário na página?", ["Sim"]),
    ("tem tabela na página?", ["Não"]),
    ("what color is the Nossos serviços heading?", ["#1d4ed8"]),
    ("what is the text of the Natação paragraph?", ["Piscina aquecida"]),
    ("is Musculação bold?", ["Yes"]),
    ("is the Natação paragraph centered?", ["No"]),
    ("where is the Piscina image?", ["Serviços", "4"]),
    ("what is in the form?", ["Nome", "E-mail", "Mensagem", "Enviar"]),
    ("how many headings are there?", ["4"]),
    ("where is validateDocument defined?", None),
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


def _match(got: list, expected: list) -> bool:
    if len(got) != len(expected):
        return False
    return all(all(g.get(k) == v for k, v in e.items() if v is not ANY) for g, e in zip(got, expected))


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

    stored = pathlib.Path(__file__).with_name("congelado3.sha256")
    h = digest()
    if not stored.exists():
        stored.write_text(h, encoding="utf-8")
    assert stored.read_text(encoding="utf-8").strip() == h, "o conjunto congelado foi alterado"
    t = time.time()
    print("pedidos:", json.dumps(run_requests("-v" in sys.argv)), f"de {len(REQUESTS)} em {time.time() - t:.1f}s",
          f"(hash {h[:12]})")
    t = time.time()
    print("perguntas:", json.dumps(run_questions("-v" in sys.argv)), f"de {len(QUESTIONS)} em {time.time() - t:.1f}s")
