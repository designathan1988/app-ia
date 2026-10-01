"""Frozen validation set v5 (docs/plano_compreensao.md §4; v1 to v4 were each measured once and are spent).

Written before it was ever run, on a page the engine was never developed on (a photographer's portfolio), with
styles and texts set. Frozen by hash (``congelado5.sha256``, written on the first run, before any result is seen).
Measured at the gates only, never used to tune. Scoring as v3.

Usage: python experiments/congelado5.py [-v]
"""
from __future__ import annotations

import hashlib
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from congelado3 import ADD, ANY, C, MV, NAME, RM, S, TXT, _match  # noqa: E402,F401  (helpers only)
from congelado4 import run_questions as _rq, run_requests as _rr  # noqa: E402

NODES = {
    "pg": ("Página", "page", None, ["mn", "cp", "gl", "sb", "ct", "rd"], None, {}),
    "mn": ("Menu principal", "header", "pg", ["as", "lk"], None, {}),
    "as": ("Assinatura", "image", "mn", [], None, {"height": "48px"}),
    "lk": ("Instagram", "link", "mn", [], "Instagram", {}),
    "cp": ("Capa", "section", "pg", ["tt", "st", "fd"], None, {"background-color": "#111111"}),
    "tt": ("Luz e sombra", "heading", "cp", [], "Luz e sombra", {"color": "white", "font-size": "56px"}),
    "st": ("Subtítulo", "paragraph", "cp", [], "Fotografia de retrato", {"color": "#d4d4d4"}),
    "fd": ("Fundo", "image", "cp", [], None, {}),
    "gl": ("Galeria", "section", "pg", ["g1", "g2", "g3", "g4"], None, {}),
    "g1": ("Foto 1", "image", "gl", [], None, {"width": "300px"}),
    "g2": ("Foto 2", "image", "gl", [], None, {"width": "300px"}),
    "g3": ("Foto 3", "image", "gl", [], None, {"width": "300px"}),
    "g4": ("Legenda", "paragraph", "gl", [], "Ensaios de 2026", {"font-style": "italic"}),
    "sb": ("Sobre", "section", "pg", ["sh", "sp"], None, {}),
    "sh": ("Quem sou", "heading", "sb", [], "Quem sou", {}),
    "sp": ("Biografia", "paragraph", "sb", [], "Fotógrafa há dez anos", {"text-align": "justify"}),
    "ct": ("Contato", "form", "pg", ["ce", "cm", "cb"], None, {}),
    "ce": ("E-mail", "input", "ct", [], None, {}),
    "cm": ("Mensagem", "textarea", "ct", [], None, {}),
    "cb": ("Enviar", "button", "ct", [], "Enviar", {}),
    "rd": ("Rodapé", "footer", "pg", ["dr"], None, {}),
    "dr": ("Direitos", "paragraph", "rd", [], "Todos os direitos reservados", {"font-size": "12px"}),
}

PAD = lambda v, n, prop="padding": [S(f"{prop}-{s}", v, n) for s in ("top", "right", "bottom", "left")]  # noqa: E731

REQUESTS = [
    # --- Portuguese ---
    ("deixa o título Luz e sombra em itálico", [S("font-style", "italic", "tt")]),
    ("muda a cor do subtítulo para branco", [S("color", "white", "st")]),
    ("aumenta o título Quem sou", [S("font-size", ANY, "sh")]),
    ("o fundo da galeria tem que ser cinza escuro", [S("background-color", "darkgray", "gl")]),
    ("centraliza a biografia", [S("text-align", "center", "sp")]),
    ("tira o itálico da legenda", [S("font-style", "normal", "g4")]),
    ("apaga a foto 3", [RM("g3")]),
    ("esconde o link Instagram", [C("element.toggleHidden", "lk")]),
    ("duplica a foto 2", [C("element.duplicate", "g2")]),
    ("move a assinatura para o rodapé", [MV("as", "rd")]),
    ('muda o texto do botão Enviar para "Mandar mensagem"', [TXT("cb", "Mandar mensagem")]),
    ("renomeia a seção Sobre para Biografia completa", [NAME("sb", "Biografia completa")]),
    ("insere uma imagem na galeria", [ADD("image", "gl")]),
    ("coloca um parágrafo dentro da seção Sobre", [ADD("paragraph", "sb")]),
    ("deixa os direitos em negrito e cinza", [S("font-weight", "bold", "dr"), S("color", "gray", "dr")]),
    ("deixa a foto 1 com 400px de largura", [S("width", "400px", "g1")]),
    ("diminui a assinatura", [S("height", ANY, "as")]),
    ("coloca 24px de padding na galeria", PAD("24px", "gl")),
    ("põe uma margem de 16px em cima do título Quem sou", [S("margin-top", "16px", "sh")]),
    ("apaga a segunda foto", [RM("g2")]),
    ("sublinha o título Quem sou", [S("text-decoration-line", "underline", "sh")]),
    ("tira", "perguntar"),
    ("muda o tamanho do título", "perguntar"),
    ("não esconde a galeria", "perguntar"),
    ("as fotos ficaram lindas", "fato"),
    ("pode apagar o campo E-mail?", [RM("ce")]),
    ("Insere um título na galeria. Depois deixa ele vermelho.",
     [ADD("heading", "gl"), {"kind": "style", "property": "color", "value": "red"}]),
    ("Cria uma seção na página e chama ela de Prêmios.",
     [ADD("section", "pg"), {"kind": "field", "field": "name", "value": "Prêmios"}]),
    ("Esconde a assinatura e depois apaga o link Instagram.", [C("element.toggleHidden", "as"), RM("lk")]),
    ("O título da capa está grande demais. Diminui ele.", [S("font-size", ANY, "tt")]),
    ("Obrigado! Agora sublinha a legenda.", [S("text-decoration-line", "underline", "g4")]),
    # --- English ---
    ("make the Luz e sombra heading italic", [S("font-style", "italic", "tt")]),
    ("change the subtitle color to white", [S("color", "white", "st")]),
    ("make the Quem sou heading bigger", [S("font-size", ANY, "sh")]),
    ("the gallery background should be dark gray", [S("background-color", "darkgray", "gl")]),
    ("center the biography", [S("text-align", "center", "sp")]),
    ("remove the italics from the caption", [S("font-style", "normal", "g4")]),
    ("delete photo 3", [RM("g3")]),
    ("hide the Instagram link", [C("element.toggleHidden", "lk")]),
    ("duplicate photo 2", [C("element.duplicate", "g2")]),
    ("move the signature to the footer", [MV("as", "rd")]),
    ("change the Enviar button text to 'Send message'", [TXT("cb", "Send message")]),
    ("add an image to the gallery", [ADD("image", "gl")]),
    ("make the rights paragraph bold and gray", [S("font-weight", "bold", "dr"), S("color", "gray", "dr")]),
    ("make photo 1 400px wide", [S("width", "400px", "g1")]),
    ("add 24px of padding to the gallery", PAD("24px", "gl")),
    ("put a 16px margin above the Quem sou heading", [S("margin-top", "16px", "sh")]),
    ("delete the second photo", [RM("g2")]),
    ("underline the Quem sou heading", [S("text-decoration-line", "underline", "sh")]),
    ("remove", "perguntar"),
    ("change the heading size", "perguntar"),
    ("don't hide the gallery", "perguntar"),
    ("the photos look great", "fato"),
    ("Add a heading to the gallery. Then make it red.",
     [ADD("heading", "gl"), {"kind": "style", "property": "color", "value": "red"}]),
    ("Hide the signature and then delete the Instagram link.", [C("element.toggleHidden", "as"), RM("lk")]),
    ("Thanks! Now underline the caption.", [S("text-decoration-line", "underline", "g4")]),
]

QUESTIONS = [
    ("qual é a cor do título Luz e sombra?", ["white"]),
    ("qual o tamanho da fonte dos direitos?", ["12px"]),
    ("qual é o fundo da capa?", ["#111111"]),
    ("qual o texto do subtítulo?", ["Fotografia de retrato"]),
    ("a legenda está em itálico?", ["Sim"]),
    ("a biografia está centralizada?", ["Não"]),
    ("onde está a foto 2?", ["Galeria", "2"]),
    ("o que tem no formulário?", ["E-mail", "Mensagem", "Enviar"]),
    ("quantas imagens tem na página?", ["5"]),
    ("tem rodapé?", ["Sim"]),
    ("what color is the Luz e sombra heading?", ["white"]),
    ("what is the text of the subtitle?", ["Fotografia de retrato"]),
    ("is the caption italic?", ["Yes"]),
    ("where is photo 2?", ["Galeria", "2"]),
    ("how many images are there?", ["5"]),
    ("where is validateDocument defined?", None),
]


def digest() -> str:
    text = repr(NODES) + "\n" + "\n".join(f"{t!r}\t{e!r}" for t, e in REQUESTS) + "\n" + \
        "\n".join(f"{t!r}\t{e!r}" for t, e in QUESTIONS)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


if __name__ == "__main__":
    import json

    stored = pathlib.Path(__file__).with_name("congelado5.sha256")
    h = digest()
    if not stored.exists():
        stored.write_text(h, encoding="utf-8")
    assert stored.read_text(encoding="utf-8").strip() == h, "o conjunto congelado foi alterado"
    t = time.time()
    print("pedidos:", json.dumps(_on_this_page(_rr, "REQUESTS", REQUESTS, "-v" in sys.argv)),
          f"de {len(REQUESTS)} em {time.time() - t:.1f}s", f"(hash {h[:12]})")
    t = time.time()
    print("perguntas:", json.dumps(_on_this_page(_rq, "QUESTIONS", QUESTIONS, "-v" in sys.argv)),
          f"de {len(QUESTIONS)} em {time.time() - t:.1f}s")
