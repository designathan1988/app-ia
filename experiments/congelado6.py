"""Frozen validation set v6 (docs/plano_compreensao.md §4; v1 to v5 were each measured once and are spent).

Written before it was ever run, on a page the engine was never developed on (an online course's landing page),
with styles and texts set; some elements keep the editor's default names and are known by their text. Frozen by
hash (``congelado6.sha256``, written on the first run, before any result is seen). Measured at the gates only, never
used to tune. Scoring as v3.

Usage: python experiments/congelado6.py [-v]
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
    "pg": ("Página", "page", None, ["hd", "hero", "mods", "inst", "faq", "ft"], None, {}),
    "hd": ("Cabeçalho", "header", "pg", ["logo", "cta"], None, {}),
    "logo": ("Logo", "image", "hd", [], None, {"width": "120px"}),
    "cta": ("Botão", "button", "hd", [], "Inscreva-se", {"background-color": "#16a34a", "color": "white"}),
    "hero": ("Abertura", "section", "pg", ["ht", "hp", "hi"], None, {"background-color": "#0f172a"}),
    "ht": ("Título", "heading", "hero", [], "Aprenda Python do zero", {"color": "white", "font-size": "48px"}),
    "hp": ("Parágrafo", "paragraph", "hero", [], "Curso online com certificado", {"color": "#cbd5e1"}),
    "hi": ("Imagem", "image", "hero", [], None, {"height": "300px"}),
    "mods": ("Módulos", "section", "pg", ["mt", "m1", "m2", "m3"], None, {}),
    "mt": ("Título 2", "heading", "mods", [], "O que você vai aprender", {}),
    "m1": ("Módulo 1", "article", "mods", ["m1t"], None, {}),
    "m1t": ("Título 3", "heading", "m1", [], "Fundamentos", {}),
    "m2": ("Módulo 2", "article", "mods", ["m2t"], None, {}),
    "m2t": ("Título 4", "heading", "m2", [], "Funções", {}),
    "m3": ("Módulo 3", "article", "mods", ["m3t"], None, {}),
    "m3t": ("Título 5", "heading", "m3", [], "Projetos", {}),
    "inst": ("Instrutora", "section", "pg", ["ip", "iq"], None, {}),
    "ip": ("Foto da instrutora", "image", "inst", [], None, {"border-radius": "50%"}),
    "iq": ("Citação", "blockquote", "inst", [], "Ensino há 12 anos", {"font-style": "italic"}),
    "faq": ("Perguntas", "section", "pg", ["fq"], None, {}),
    "fq": ("Lista de perguntas", "list", "faq", [], None, {}),
    "ft": ("Rodapé", "footer", "pg", ["fc"], None, {"background-color": "#111827"}),
    "fc": ("Créditos", "paragraph", "ft", [], "Feito com carinho", {"font-size": "12px"}),
}

PAD = lambda v, n: [S(f"padding-{s}", v, n) for s in ("top", "right", "bottom", "left")]  # noqa: E731

REQUESTS = [
    # --- Portuguese ---
    ("deixa o título Aprenda Python do zero em negrito", [S("font-weight", "bold", "ht")]),
    ("muda a cor do título O que você vai aprender para azul", [S("color", "blue", "mt")]),
    ("diminui o título Aprenda Python do zero", [S("font-size", ANY, "ht")]),
    ("o fundo da seção Módulos tem que ser cinza claro", [S("background-color", "lightgray", "mods")]),
    ("centraliza o parágrafo Curso online com certificado", [S("text-align", "center", "hp")]),
    ("tira o itálico da citação", [S("font-style", "normal", "iq")]),
    ("apaga a foto da instrutora", [RM("ip")]),
    ("esconde a lista de perguntas", [C("element.toggleHidden", "fq")]),
    ("duplica o módulo 2", [C("element.duplicate", "m2")]),
    ("move o logo para o rodapé", [MV("logo", "ft")]),
    ('muda o texto do botão Inscreva-se para "Quero começar"', [TXT("cta", "Quero começar")]),
    ("renomeia a seção Instrutora para Sobre a instrutora", [NAME("inst", "Sobre a instrutora")]),
    ("insere um parágrafo na seção Perguntas", [ADD("paragraph", "faq")]),
    ("coloca um botão dentro do módulo 3", [ADD("button", "m3")]),
    ("deixa os créditos brancos e centralizados", [S("color", "white", "fc"), S("text-align", "center", "fc")]),
    ("aumenta a imagem da abertura", [S("height", ANY, "hi")]),
    ("coloca 40px de padding na seção Instrutora", PAD("40px", "inst")),
    ("põe uma margem de 20px embaixo do título O que você vai aprender", [S("margin-bottom", "20px", "mt")]),
    ("apaga o terceiro módulo", [RM("m3")]),
    ("deixa o título Fundamentos em itálico", [S("font-style", "italic", "m1t")]),
    ("muda", "perguntar"),
    ("deixa maior", "perguntar"),
    ("não apaga o módulo 1", "perguntar"),
    ("o curso é muito bom", "fato"),
    ("pode esconder a imagem da abertura?", [C("element.toggleHidden", "hi")]),
    ("Insere um título no rodapé. Depois deixa ele branco.",
     [ADD("heading", "ft"), {"kind": "style", "property": "color", "value": "white"}]),
    ("Cria um parágrafo na seção Perguntas e chama ele de Resposta 1.",
     [ADD("paragraph", "faq"), {"kind": "field", "field": "name", "value": "Resposta 1"}]),
    ("Esconde o logo e depois apaga a citação.", [C("element.toggleHidden", "logo"), RM("iq")]),
    ("O título Projetos está pequeno. Aumenta ele.", [S("font-size", ANY, "m3t")]),
    ("Valeu! Agora sublinha os créditos.", [S("text-decoration-line", "underline", "fc")]),
    # --- English ---
    ("make the Aprenda Python do zero heading bold", [S("font-weight", "bold", "ht")]),
    ("change the O que você vai aprender heading color to blue", [S("color", "blue", "mt")]),
    ("make the Aprenda Python do zero heading smaller", [S("font-size", ANY, "ht")]),
    ("the Módulos section background should be light gray", [S("background-color", "lightgray", "mods")]),
    ("center the Curso online com certificado paragraph", [S("text-align", "center", "hp")]),
    ("remove the italics from the quote", [S("font-style", "normal", "iq")]),
    ("delete the instructor photo", [RM("ip")]),
    ("hide the question list", [C("element.toggleHidden", "fq")]),
    ("duplicate module 2", [C("element.duplicate", "m2")]),
    ("move the logo to the footer", [MV("logo", "ft")]),
    ("change the Inscreva-se button text to 'Start now'", [TXT("cta", "Start now")]),
    ("add a paragraph to the Perguntas section", [ADD("paragraph", "faq")]),
    ("make the credits white and centered", [S("color", "white", "fc"), S("text-align", "center", "fc")]),
    ("add 40px of padding to the Instrutora section", PAD("40px", "inst")),
    ("put a 20px margin below the O que você vai aprender heading", [S("margin-bottom", "20px", "mt")]),
    ("delete the third module", [RM("m3")]),
    ("make the Fundamentos heading italic", [S("font-style", "italic", "m1t")]),
    ("change", "perguntar"),
    ("make it bigger", "perguntar"),
    ("don't delete module 1", "perguntar"),
    ("this course is great", "fato"),
    ("Add a heading to the footer. Then make it white.",
     [ADD("heading", "ft"), {"kind": "style", "property": "color", "value": "white"}]),
    ("Hide the logo and then delete the quote.", [C("element.toggleHidden", "logo"), RM("iq")]),
    ("Thanks! Now underline the credits.", [S("text-decoration-line", "underline", "fc")]),
]

QUESTIONS = [
    ("qual é a cor do título Aprenda Python do zero?", ["white"]),
    ("qual o tamanho da fonte dos créditos?", ["12px"]),
    ("qual é o fundo do rodapé?", ["#111827"]),
    ("qual o texto do botão do cabeçalho?", ["Inscreva-se"]),
    ("a citação está em itálico?", ["Sim"]),
    ("o parágrafo Curso online com certificado está centralizado?", ["Não"]),
    ("onde está o módulo 2?", ["Módulos", "3"]),
    ("o que tem na seção Instrutora?", ["Foto da instrutora", "Citação"]),
    ("quantos módulos tem?", ["3"]),
    ("tem rodapé?", ["Sim"]),
    ("what color is the Aprenda Python do zero heading?", ["white"]),
    ("what is the text of the header button?", ["Inscreva-se"]),
    ("is the quote italic?", ["Yes"]),
    ("where is module 2?", ["Módulos", "3"]),
    ("how many modules are there?", ["3"]),
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

    stored = pathlib.Path(__file__).with_name("congelado6.sha256")
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
