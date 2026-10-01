"""Fast check of free Portuguese requests at the understanding level (seconds, no planner): what each one should mean.

The sentences vary verbs (synonyms, regional and informal forms), word order, missing accents, values said in words,
and elements named by type or name. Each has its expected meaning; "perguntar" means the right behavior is to ask
(the request is ambiguous or missing something), never to act. Reported: right, asked, not understood, WRONG (acted
with another meaning: the error that matters).

Usage: python experiments/m5_livre.py [-v]
"""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from nucleo.lang.understand import World, understand  # noqa: E402

NODES = {
    "pg": ("Página", "page", None, ["s"]),
    "s": ("Topo", "section", "pg", ["t", "p", "b", "i"]),
    "t": ("Café Aurora", "heading", "s", []),
    "p": ("Intro", "paragraph", "s", []),
    "b": ("Assinar", "button", "s", []),
    "i": ("Foto", "image", "s", []),
}

S = lambda prop, value, node=None: {"kind": "style", "property": prop, "value": value, **({"id": node} if node else {})}  # noqa: E731
C = lambda cmd, node: {"kind": "command", "command": cmd, "id": node}  # noqa: E731

CASES = [
    # alignment
    ("coloque o titulo a direita", S("text-align", "right", "t")),
    ("alinhe o parágrafo à esquerda", S("text-align", "left", "p")),
    ("centraliza o título", S("text-align", "center", "t")),
    ("deixa o texto do parágrafo centralizado", S("text-align", "center", "p")),
    ("joga o título pra direita", S("text-align", "right", "t")),
    # weight, style, decoration
    ("deixe o título em negrito", S("font-weight", "bold", "t")),
    ("bota o parágrafo em itálico", S("font-style", "italic", "p")),
    ("sublinhe o título", S("text-decoration-line", "underline", "t")),
    ("grife o parágrafo", S("text-decoration-line", "underline", "p")),
    ("coloca o botão em negrito", S("font-weight", "bold", "b")),
    # colors
    ("pinte o título de vermelho", S("color", "red", "t")),
    ("tinja o parágrafo de azul", S("color", "blue", "p")),
    ("pinte a seção de amarelo", S("background-color", "yellow", "s")),
    ("deixe o fundo da seção preto", S("background-color", "black", "s")),
    ("muda a cor do texto do botão para branco", S("color", "white", "b")),
    ("deixe o título verde", S("color", "green", "t")),
    ("coloque o fundo do botão cinza", S("background-color", "gray", "b")),
    ("mude a cor do título para #ff0000", S("color", "#ff0000", "t")),
    # sizes and spacing
    ("mude a fonte do título para 32px", S("font-size", "32px", "t")),
    ("aumente o tamanho da fonte do parágrafo para 20px", S("font-size", "20px", "p")),
    ("defina a margem superior da seção como 24px", S("margin-top", "24px", "s")),
    ("coloque 16px de padding na seção", "perguntar"),
    ("deixe a largura da imagem em 300px", S("width", "300px", "i")),
    # commands
    ("duplique o botão", C("element.duplicate", "b")),
    ("esconda o parágrafo", C("element.toggleHidden", "p")),
    ("oculte a imagem", C("element.toggleHidden", "i")),
    ("camufle o botão", C("element.toggleHidden", "b")),
    ("bloqueie o título", C("element.toggleLock", "t")),
    ("trave o botão", C("element.toggleLock", "b")),
    ("mova o parágrafo para cima", C("element.moveUp", "p")),
    ("desce o título", "perguntar"),
    # removal
    ("apague o botão", {"kind": "removed", "id": "b"}),
    ("remova a imagem", {"kind": "removed", "id": "i"}),
    ("exclua o parágrafo", {"kind": "removed", "id": "p"}),
    ("delete o título", {"kind": "removed", "id": "t"}),
    ("elimine a foto", {"kind": "removed", "id": "i"}),
    ("tira o botão", {"kind": "removed", "id": "b"}),
    # insertion
    ("insira um botão na seção", {"kind": "added", "type": "button", "parent": "s"}),
    ("adicione um parágrafo depois do título", {"kind": "added", "type": "paragraph", "parent": "s"}),
    ("crie uma imagem no fim da seção", {"kind": "added", "type": "image", "parent": "s"}),
    ("põe um título na seção", {"kind": "added", "type": "heading", "parent": "s"}),
    ("acrescente um rodapé", {"kind": "added", "type": "footer"}),
    ("coloque uma figura na seção", {"kind": "added", "type": "figure", "parent": "s"}),
    # text and names
    ('mude o texto do botão para "Comprar"', {"kind": "field", "field": "text", "value": "Comprar"}),
    ("troque o texto do título por Café Serra", {"kind": "field", "field": "text", "value": "Café Serra"}),
    ("renomeie a seção para Destaque", {"kind": "field", "field": "name", "value": "Destaque"}),
    ("escreva Olá no parágrafo", {"kind": "field", "field": "text", "value": "Olá"}),
    # move
    ("coloque o botão antes do parágrafo", {"kind": "moved", "id": "b"}),
    ("mova o título para o fim da seção", {"kind": "moved", "id": "t"}),
    ("passe a imagem para o início da seção", {"kind": "moved", "id": "i"}),
    # names instead of types
    ("pinte o Assinar de vermelho", S("color", "red", "b")),
    ("apague o Intro", {"kind": "removed", "id": "p"}),
    # must ask or refuse, never act
    ("blorfe o botão", "perguntar"),
    ("pinte", "perguntar"),
    ("deixe bonito", "perguntar"),
    ("apague", "perguntar"),
]


# written after the fixes above, and run once before any change: the honest measure
VALIDATION = [
    ("alinha o botão no centro", S("text-align", "center", "b")),
    ("põe o parágrafo em negrito, por favor", S("font-weight", "bold", "p")),
    ("quero o título sublinhado", S("text-decoration-line", "underline", "t")),
    ("pode deixar o parágrafo em itálico?", S("font-style", "italic", "p")),
    ("muda o fundo do botão pra azul", S("background-color", "blue", "b")),
    ("pinta o botão de preto", S("color", "black", "b")),
    ("colore o título de laranja", S("color", "orange", "t")),
    ("deixa a seção com fundo branco", S("background-color", "white", "s")),
    ("o título tem que ficar vermelho", S("color", "red", "t")),
    ("coloca a cor do parágrafo como #333333", S("color", "#333333", "p")),
    ("aumenta a fonte do título pra 40px", S("font-size", "40px", "t")),
    ("diminui o tamanho da fonte do parágrafo para 12px", S("font-size", "12px", "p")),
    ("define a altura da imagem como 200px", S("height", "200px", "i")),
    ("some com o botão", {"kind": "removed", "id": "b"}),
    ("joga fora a imagem", {"kind": "removed", "id": "i"}),
    ("deleta o parágrafo", {"kind": "removed", "id": "p"}),
    ("faz uma cópia do botão", C("element.duplicate", "b")),
    ("duplica a imagem", C("element.duplicate", "i")),
    ("esconde o título", C("element.toggleHidden", "t")),
    ("tranca a seção", C("element.toggleLock", "s")),
    ("sobe o botão", C("element.moveUp", "b")),
    ("adiciona um botão depois do parágrafo", {"kind": "added", "type": "button", "parent": "s"}),
    ("cria um parágrafo no início da seção", {"kind": "added", "type": "paragraph", "parent": "s"}),
    ("insere uma imagem antes do botão", {"kind": "added", "type": "image", "parent": "s"}),
    ("coloca um cabeçalho na página", {"kind": "added", "type": "header"}),
    ('muda o texto do parágrafo para "Bem-vindo"', {"kind": "field", "field": "text", "value": "Bem-vindo"}),
    ("escreve Promoção no botão", {"kind": "field", "field": "text", "value": "Promoção"}),
    ("troca o nome da seção para Hero", {"kind": "field", "field": "name", "value": "Hero"}),
    ("passa o botão para depois da imagem", {"kind": "moved", "id": "b"}),
    ("leva o título para o fim da seção", {"kind": "moved", "id": "t"}),
    ("deixa o Assinar em negrito", S("font-weight", "bold", "b")),
    ("centraliza o Intro", S("text-align", "center", "p")),
    ("arruma isso", "perguntar"),
    ("faz alguma coisa", "perguntar"),
    ("muda a cor", "perguntar"),
    ("coloca um", "perguntar"),
]


# English: the same page and meanings, said in English (same engine; only the parser, lexicon and function words
# of the language change)
ENGLISH = [
    ("align the title to the right", S("text-align", "right", "t")),
    ("center the paragraph", S("text-align", "center", "p")),
    ("make the title bold", S("font-weight", "bold", "t")),
    ("put the paragraph in italic", S("font-style", "italic", "p")),
    ("underline the title", S("text-decoration-line", "underline", "t")),
    ("make the title red", S("color", "red", "t")),
    ("paint the section yellow", S("background-color", "yellow", "s")),
    ("set the background of the section to black", S("background-color", "black", "s")),
    ("change the font size of the title to 32px", S("font-size", "32px", "t")),
    ("set the top margin of the section to 24px", S("margin-top", "24px", "s")),
    ("duplicate the button", C("element.duplicate", "b")),
    ("hide the paragraph", C("element.toggleHidden", "p")),
    ("lock the title", C("element.toggleLock", "t")),
    ("move the paragraph up", C("element.moveUp", "p")),
    ("delete the button", {"kind": "removed", "id": "b"}),
    ("remove the image", {"kind": "removed", "id": "i"}),
    ("insert a button in the section", {"kind": "added", "type": "button", "parent": "s"}),
    ("add a paragraph after the title", {"kind": "added", "type": "paragraph", "parent": "s"}),
    ("create an image at the end of the section", {"kind": "added", "type": "image", "parent": "s"}),
    ('change the text of the button to "Buy"', {"kind": "field", "field": "text", "value": "Buy"}),
    ("rename the section to Hero", {"kind": "field", "field": "name", "value": "Hero"}),
    ("move the title to the end of the section", {"kind": "moved", "id": "t"}),
    ("put the button before the paragraph", {"kind": "moved", "id": "b"}),
    ("blorf the button", "perguntar"),
    ("make it nice", "perguntar"),
]


ENGLISH_VALIDATION = [
    ("could you make the paragraph italic?", S("font-style", "italic", "p")),
    ("please center the title", S("text-align", "center", "t")),
    ("left align the button", S("text-align", "left", "b")),
    ("color the title blue", S("color", "blue", "t")),
    ("give the section a white background", S("background-color", "white", "s")),
    ("change the background color of the button to gray", S("background-color", "gray", "b")),
    ("increase the font size of the paragraph to 20px", S("font-size", "20px", "p")),
    ("set the width of the image to 300px", S("width", "300px", "i")),
    ("conceal the image", C("element.toggleHidden", "i")),
    ("make a copy of the button", C("element.duplicate", "b")),
    ("erase the paragraph", {"kind": "removed", "id": "p"}),
    ("get rid of the image", {"kind": "removed", "id": "i"}),
    ("add a heading at the beginning of the section", {"kind": "added", "type": "heading", "parent": "s"}),
    ("put an image after the button", {"kind": "added", "type": "image", "parent": "s"}),
    ("insert a footer", {"kind": "added", "type": "footer"}),
    ('set the text of the paragraph to "Hello"', {"kind": "field", "field": "text", "value": "Hello"}),
    ("call the section Intro", {"kind": "field", "field": "name", "value": "Intro"}),
    ("move the image to the beginning of the section", {"kind": "moved", "id": "i"}),
    ("the title should be bold", S("font-weight", "bold", "t")),
    ("do something", "perguntar"),
]


def matches(c: dict, expected: dict) -> bool:
    return all(c.get(k) == v for k, v in expected.items())


def run(verbose: bool = False, cases=None) -> dict:
    nodes = {nid: {"name": n, "type": t, "parent": par, "index": 0, "children": kids, "flags": {}}
             for nid, (n, t, par, kids) in NODES.items()}
    for nid, (_, _, par, _) in NODES.items():
        if par:
            nodes[nid]["index"] = NODES[par][3].index(nid)
    world = World(nodes, [])
    counts = {"certo": 0, "perguntou": 0, "nao_entendeu": 0, "ERRADO": 0}
    for text, expected in (CASES if cases is None else cases):
        u = understand(text, world)
        if expected == "perguntar":
            outcome = "certo" if u.decision != "executar" else "ERRADO"
        elif u.decision == "executar":
            outcome = "certo" if matches(u.best.constraints[0], expected) else "ERRADO"
        else:
            outcome = "perguntou" if u.decision == "perguntar" else "nao_entendeu"
        counts[outcome] += 1
        if verbose or outcome != "certo":
            print(f"[{outcome}] {text}\n    -> {u.decision}: {u.message[:150]}")
    return counts


if __name__ == "__main__":
    t = time.time()
    c = run("-v" in sys.argv)
    print("ajuste:", c, f"de {len(CASES)} em {time.time() - t:.1f}s")
    t = time.time()
    c = run("-v" in sys.argv, VALIDATION)
    print("validação:", c, f"de {len(VALIDATION)} em {time.time() - t:.1f}s")
    t = time.time()
    c = run("-v" in sys.argv or "-en" in sys.argv, ENGLISH)
    print("inglês:", c, f"de {len(ENGLISH)} em {time.time() - t:.1f}s")
    t = time.time()
    c = run("-v" in sys.argv or "-en" in sys.argv, ENGLISH_VALIDATION)
    print("inglês, validação:", c, f"de {len(ENGLISH_VALIDATION)} em {time.time() - t:.1f}s")
