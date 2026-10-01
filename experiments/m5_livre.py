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
    # (CSS: "padding: 16px" is the four sides; this was "perguntar" while the engine could not expand a shorthand)
    ("coloque 16px de padding na seção", [S(f"padding-{x}", "16px", "s") for x in ("top", "right", "bottom", "left")]),
    ("deixe a largura da imagem em 300px", S("width", "300px", "i")),
    # commands
    ("duplique o botão", C("element.duplicate", "b")),
    ("esconda o parágrafo", C("element.toggleHidden", "p")),
    ("oculte a imagem", C("element.toggleHidden", "i")),
    ("camufle o botão", C("element.toggleHidden", "b")),
    ("bloqueie o título", C("element.toggleLock", "t")),
    ("trave o botão", C("element.toggleLock", "b")),
    ("mova o parágrafo para cima", C("element.moveUp", "p")),
    ("desce o título", C("element.moveDown", "t")),
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


# third round, written after everything above and run once before any change
FRESH = [
    ("muda o alinhamento do parágrafo para a direita", S("text-align", "right", "p")),
    ("faz o título ficar em negrito", S("font-weight", "bold", "t")),
    ("eu quero o botão azul", S("color", "blue", "b")),
    ("deixe o parágrafo com a fonte maior, tipo 22px", S("font-size", "22px", "p")),
    ("tira o negrito do título", S("font-weight", "normal", "t")),
    ("põe uma margem de 10px em cima do botão", S("margin-top", "10px", "b")),
    ("muda o fundo da página inteira para cinza", S("background-color", "gray", "pg")),
    ("apaga essa imagem", {"kind": "removed", "id": "i"}),
    ("remove o botão Assinar", {"kind": "removed", "id": "b"}),
    ("faz o parágrafo sumir", C("element.toggleHidden", "p")),
    ("duplica o título", C("element.duplicate", "t")),
    ("coloca outro botão embaixo do parágrafo", {"kind": "added", "type": "button", "parent": "s"}),
    ("adiciona um título novo no topo da seção", {"kind": "added", "type": "heading", "parent": "s"}),
    ('troca o texto do botão para "Saiba mais"', {"kind": "field", "field": "text", "value": "Saiba mais"}),
    ("muda o nome da imagem para Capa", {"kind": "field", "field": "name", "value": "Capa"}),
    ("joga o botão pro começo da seção", {"kind": "moved", "id": "b"}),
    ("deixa todas as imagens escondidas", C("element.toggleHidden", "i")),
    ("make the button text white", S("color", "white", "b")),
    ("turn the title green", S("color", "green", "t")),
    ("increase the title font size to 48px", S("font-size", "48px", "t")),
    ("align everything in the section to the center", "perguntar"),
    ("delete that image", {"kind": "removed", "id": "i"}),
    ("throw away the button", {"kind": "removed", "id": "b"}),
    ("clone the paragraph", C("element.duplicate", "p")),
    ("put a new button at the end of the section", {"kind": "added", "type": "button", "parent": "s"}),
    ("rename the image to Cover", {"kind": "field", "field": "name", "value": "Cover"}),
    ("move the button to the top of the section", {"kind": "moved", "id": "b"}),
    ("make the paragraph text italic", S("font-style", "italic", "p")),
    ("can you hide the button please?", C("element.toggleHidden", "b")),
    ("asdf the qwer", "perguntar"),
]


# fourth round, written after the third round's fixes and run once before any change
FOURTH = [
    ("bota o título em itálico e sublinhado", S("font-style", "italic", "t")),  # and underline (coordination)
    ("quero que o parágrafo fique centralizado", S("text-align", "center", "p")),
    ("o botão precisa ficar vermelho", S("color", "red", "b")),
    ("seria possível deixar a seção com fundo preto?", S("background-color", "black", "s")),
    ("aumenta o espaçamento entre as letras do título para 2px", S("letter-spacing", "2px", "t")),
    ("deixa a imagem com 400px de largura", S("width", "400px", "i")),
    ("tira o botão da seção", {"kind": "removed", "id": "b"}),
    ("exclui a foto", {"kind": "removed", "id": "i"}),
    ("esconde a foto", C("element.toggleHidden", "i")),
    ("duplica a seção", C("element.duplicate", "s")),
    ("põe um parágrafo novo antes do botão", {"kind": "added", "type": "paragraph", "parent": "s"}),
    ("insere uma imagem logo depois do título", {"kind": "added", "type": "image", "parent": "s"}),
    ('escreve "Bem-vindo" no título', {"kind": "field", "field": "text", "value": "Bem-vindo"}),
    ("passa o título para depois do parágrafo", {"kind": "moved", "id": "t"}),
    ("sobe o parágrafo", C("element.moveUp", "p")),
    ("desce o botão", C("element.moveDown", "b")),
    ("deixa o texto do botão branco", S("color", "white", "b")),
    ("muda a cor de fundo da seção pra #222222", S("background-color", "#222222", "s")),
    ("make the paragraph bold and red", S("font-weight", "bold", "p")),  # and red (coordination)
    ("i want the title centered", S("text-align", "center", "t")),
    ("the button should be blue", S("color", "blue", "b")),
    ("set the letter spacing of the title to 2px", S("letter-spacing", "2px", "t")),
    ("make the image 400px wide", S("width", "400px", "i")),
    ("remove the button from the section", {"kind": "removed", "id": "b"}),
    ("duplicate the section", C("element.duplicate", "s")),
    ("add a new paragraph before the button", {"kind": "added", "type": "paragraph", "parent": "s"}),
    ('write "Welcome" in the title', {"kind": "field", "field": "text", "value": "Welcome"}),
    ("move the title below the paragraph", {"kind": "moved", "id": "t"}),
    ("move the button down", C("element.moveDown", "b")),
    ("make the button text white", S("color", "white", "b")),
]


# fifth round, written after the fourth round's fixes and run once before any change
FIFTH = [
    ("da pra deixar o título azul?", S("color", "blue", "t")),
    ("me faz um favor, centraliza o parágrafo", S("text-align", "center", "p")),
    ("o título tá muito pequeno, coloca 36px", S("font-size", "36px", "t")),
    ("muda a cor das letras do botão para amarelo", S("color", "yellow", "b")),
    ("arruma o alinhamento do título pra esquerda", S("text-align", "left", "t")),
    ("deixa o fundo do parágrafo cinza claro", S("background-color", "lightgray", "p")),
    ("bota negrito no parágrafo", S("font-weight", "bold", "p")),
    ("coloca itálico no título", S("font-style", "italic", "t")),
    ("deleta o título", {"kind": "removed", "id": "t"}),
    ("some com a imagem", "perguntar"),
    ("cria mais um parágrafo no final", {"kind": "added", "type": "paragraph"}),
    ("adiciona uma imagem na seção", {"kind": "added", "type": "image", "parent": "s"}),
    ("faz uma cópia da imagem", C("element.duplicate", "i")),
    ("oculta o título", C("element.toggleHidden", "t")),
    ("trava a imagem", C("element.toggleLock", "i")),
    ('o texto do botão vai ser "Comprar agora"', {"kind": "field", "field": "text", "value": "Comprar agora"}),
    ("chama a imagem de Banner", {"kind": "field", "field": "name", "value": "Banner"}),
    ("coloca o parágrafo antes do título", {"kind": "moved", "id": "p"}),
    ("could you please make the paragraph centered?", S("text-align", "center", "p")),
    ("i'd like the title in bold", S("font-weight", "bold", "t")),
    ("change the button's color to green", S("color", "green", "b")),
    ("give the title a font size of 30px", S("font-size", "30px", "t")),
    ("get rid of the paragraph", {"kind": "removed", "id": "p"}),
    ("make a duplicate of the image", C("element.duplicate", "i")),
    ("lock the image", C("element.toggleLock", "i")),
    ("add another paragraph at the end of the section", {"kind": "added", "type": "paragraph", "parent": "s"}),
    ('the button should say "Buy now"', {"kind": "field", "field": "text", "value": "Buy now"}),
    ("put the paragraph above the title", {"kind": "moved", "id": "p"}),
    ("align the image to the right", S("text-align", "right", "i")),
    ("hmm make it nicer", "perguntar"),
]


# sixth round, written after the fifth round's fixes and run once before any change
SIXTH = [
    ("pode colocar o botão em negrito?", S("font-weight", "bold", "b")),
    ("preciso que o título fique maior", "perguntar"),
    ("muda o texto do parágrafo pra Olá mundo", {"kind": "field", "field": "text", "value": "Olá mundo"}),
    ("a cor do título tem que ser vermelha", S("color", "red", "t")),
    ("deixa o título vermelho e o botão azul", S("color", "red", "t")),  # and the button blue (coordination)
    ("põe o título em negrito e itálico", S("font-weight", "bold", "t")),  # and italic (coordination)
    ("alinha tudo à esquerda", "perguntar"),
    ("apaga o primeiro parágrafo", {"kind": "removed", "id": "p"}),
    ("apaga a última imagem", {"kind": "removed", "id": "i"}),
    ("esconde todos os botões", C("element.toggleHidden", "b")),
    ("duplica o último botão", C("element.duplicate", "b")),
    ("coloca uma imagem entre o título e o parágrafo", {"kind": "added", "type": "image", "parent": "s"}),
    ("move a imagem pra cima", C("element.moveUp", "i")),
    ("leva o botão pra baixo", C("element.moveDown", "b")),
    ("deixa a fonte do parágrafo com 18px", S("font-size", "18px", "p")),
    ("o fundo da seção deve ser branco", S("background-color", "white", "s")),
    ("bota um título escrito Promoções na seção", {"kind": "added", "type": "heading", "parent": "s"}),
    ("renomeia o botão pra CTA", {"kind": "field", "field": "name", "value": "CTA"}),
    ("can you put the title in italics?", S("font-style", "italic", "t")),
    ("i need the paragraph to be centered", S("text-align", "center", "p")),
    ("the section background should be white", S("background-color", "white", "s")),
    ("make the first paragraph bold", S("font-weight", "bold", "p")),
    ("delete the last image", {"kind": "removed", "id": "i"}),
    ("hide all the buttons", C("element.toggleHidden", "b")),
    ("insert an image between the title and the paragraph", {"kind": "added", "type": "image", "parent": "s"}),
    ("move the image up", C("element.moveUp", "i")),
    ("set the paragraph font to 18px", S("font-size", "18px", "p")),
    ('add a heading that says "Sale" to the section', {"kind": "added", "type": "heading", "parent": "s"}),
    ("rename the button CTA", {"kind": "field", "field": "name", "value": "CTA"}),
    ("whatever", "perguntar"),
]


NOVO = "--novo" in sys.argv  # the rebuilt engine (nucleo/lang/interpret.py, plan C3)


def interpret_understand(text, world):
    from nucleo.lang.interpret import understand as new

    return new(text, world)


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
        u = (interpret_understand if NOVO else understand)(text, world)
        if expected == "perguntar":
            outcome = "certo" if u.decision != "executar" else "ERRADO"
        elif u.decision == "executar" and isinstance(expected, list):
            # (several changes expected: all of them, in order)
            got = u.best.constraints
            outcome = "certo" if len(got) == len(expected) and all(map(matches, got, expected)) else "ERRADO"
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
    t = time.time()
    c = run(True, FRESH)
    print("terceira rodada:", c, f"de {len(FRESH)} em {time.time() - t:.1f}s")
    t = time.time()
    c = run(True, FOURTH)
    print("quarta rodada:", c, f"de {len(FOURTH)} em {time.time() - t:.1f}s")
    t = time.time()
    c = run(True, FIFTH)
    print("quinta rodada:", c, f"de {len(FIFTH)} em {time.time() - t:.1f}s")
    t = time.time()
    c = run(True, SIXTH)
    print("sexta rodada:", c, f"de {len(SIXTH)} em {time.time() - t:.1f}s")
