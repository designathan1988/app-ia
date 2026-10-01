"""A1 compositional holdout: every item combines concepts that occur in TRAIN only apart.

Each item's combinations (operation x entity type, property x entity type, value operation x property,
property x value, position x destination type, reference kind x operation, operation pairs) are computed from its
gold by avaliar.combos(); avaliar.py verifies that at least one of them never occurs in TRAIN and reports which
kinds are new. An item that fails the check is reported and not counted as holdout.
"""
from __future__ import annotations

from acoes import D, DUP, H, INS, MOV, N, S, SEL, T

HOLDOUT = [
    # operation x entity
    ("pt", "L", "esconde o cabeçalho", [H("cab")], "holdout", None),
    ("en", "E", "hide the header", [H("hd")], "holdout", None),
    ("pt", "L", "duplica o botão Comprar agora", [DUP("bt1")], "holdout", None),
    ("en", "E", "duplicate the Get started button", [DUP("b1")], "holdout", None),
    ("pt", "L", "renomeia o primeiro cartão para Destaque 1", [N("c1", "Destaque 1")], "holdout", None),
    ("en", "E", "rename the second button to Ghost", [N("b2", "Ghost")], "holdout", None),
    ("pt", "L", "seleciona o banner", [SEL("ban")], "holdout", None),
    ("en", "E", "select the image", [SEL("im")], "holdout", None),
    # property x entity
    ("pt", "L", "muda a altura do painel para 500px", [S("pai", "height", "500px")], "holdout", None),
    ("en", "E", "set the sidebar height to 500px", [S("side", "height", "500px")], "holdout", None),
    ("pt", "L", "deixa o fundo do botão Comprar agora verde", [S("bt1", "background-color", "green")], "holdout",
     None),
    ("en", "E", "give the Get started button a green background", [S("b1", "background-color", "green")],
     "holdout", None),
    ("pt", "L", "coloca margem esquerda de 30px no banner", [S("ban", "margin-left", "30px")], "holdout", None),
    ("en", "E", "add a left margin of 30px to the image", [S("im", "margin-left", "30px")], "holdout", None),
    # value operation x property (and entity)
    ("pt", "L", "faz esse painel ficar mais largo", [S("pai", "width", "1.25", "MUL")], "holdout contexto",
     {"sel": ["pai"], "ref": "pai"}),
    ("pt", "L", "aumenta um pouco a largura dele", [S("pai", "width", "1.25", "MUL")], "holdout pronome contexto",
     {"ref": "pai"}),
    ("en", "L", "widen this panel a little", [S("pai", "width", "1.25", "MUL")], "holdout contexto",
     {"sel": ["pai"], "ref": "pai"}),
    ("en", "L", "make the selected panel slightly wider", [S("pai", "width", "1.25", "MUL")], "holdout contexto",
     {"sel": ["pai"]}),
    ("pt", "L", "deixa esse painel vinte pixels mais largo", [S("pai", "width", "20px", "ADD")],
     "holdout contexto", {"sel": ["pai"], "ref": "pai"}),
    ("en", "L", "make this panel twenty pixels wider", [S("pai", "width", "20px", "ADD")], "holdout contexto",
     {"sel": ["pai"], "ref": "pai"}),
    ("pt", "L", "aumenta a altura do banner em 50px", [S("ban", "height", "50px", "ADD")], "holdout", None),
    ("en", "E", "increase the image height by 50px", [S("im", "height", "50px", "ADD")], "holdout", None),
    ("pt", "L", "diminui a margem esquerda do primeiro cartão em 4px", [S("c1", "margin-left", "4px", "SUB")],
     "holdout", None),
    ("en", "E", "decrease the headline font size by 6px", [S("ht", "font-size", "6px", "SUB")], "holdout", None),
    # property x value
    ("pt", "L", "alinha o título à esquerda", [S("tit", "text-align", "left")], "holdout", None),
    ("en", "E", "align the headline to the left", [S("ht", "text-align", "left")], "holdout", None),
    ("pt", "L", "deixa o subtítulo em minúsculas", [S("sub", "text-transform", "lowercase")], "holdout", None),
    ("en", "E", "make the lead lowercase", [S("hp", "text-transform", "lowercase")], "holdout", None),
    ("pt", "L", "pinta o título de laranja", [S("tit", "color", "orange")], "holdout", None),
    ("en", "E", "make the headline orange", [S("ht", "color", "orange")], "holdout", None),
    ("pt", "L", "deixa o banner com posição absoluta", [S("ban", "position", "absolute")], "holdout", None),
    ("en", "E", "make the image position absolute", [S("im", "position", "absolute")], "holdout", None),
    ("en", "E", "set the sidebar display to none", [S("side", "display", "none")], "holdout", None),
    ("pt", "L", "coloca uma borda sólida no topo do botão Comprar agora", [S("bt1", "border-top-style", "solid")],
     "holdout", None),
    ("en", "E", "give the Get started button a solid top border", [S("b1", "border-top-style", "solid")],
     "holdout", None),
    ("pt", "L", "deixa o título com 3em de fonte", [S("tit", "font-size", "3em")], "holdout", None),
    # position x destination
    ("pt", "L", "insere um parágrafo no início do rodapé", [INS("paragraph", "rod", 0)], "holdout", None),
    ("en", "E", "insert a paragraph at the start of the footer", [INS("paragraph", "ft", 0)], "holdout", None),
    ("pt", "L", "adiciona um botão depois do subtítulo", [INS("button", "dest", 2)], "holdout", None),
    ("en", "E", "add a button after the lead", [INS("button", "hero", 2)], "holdout", None),
    ("en", "E", "insert a paragraph before the headline", [INS("paragraph", "hero", 0)], "holdout", None),
    ("pt", "L", "move o banner para o painel", [MOV("ban", "pai", 2)], "holdout", None),
    ("en", "E", "move the image into the sidebar", [MOV("im", "side", 2)], "holdout", None),
    # reference kind x operation
    ("pt", "L", "esconde ele", [H("ban")], "holdout pronome contexto", {"ref": "ban"}),
    ("en", "E", "duplicate this", [DUP("side")], "holdout pronome contexto", {"ref": "side", "sel": ["side"]}),
    ("pt", "L", "renomeia ele para Vitrine", [N("dest", "Vitrine")], "holdout pronome contexto", {"ref": "dest"}),
    ("en", "E", "rename it to Hero copy", [N("hero", "Hero copy")], "holdout pronome contexto", {"ref": "hero"}),
    # operation pairs
    ("pt", "L", "esconde o banner e duplica o painel", [H("ban"), DUP("pai")], "holdout composto", None),
    ("en", "E", "hide the image and duplicate the sidebar", [H("im"), DUP("side")], "holdout composto", None),
    ("pt", "L", "renomeia o painel para Filtros e apaga o banner", [N("pai", "Filtros"), D("ban")],
     "holdout composto", None),
    ("en", "E", "rename the sidebar to Filters and delete the image", [N("side", "Filters"), D("im")],
     "holdout composto", None),
]

# Construction observed mainly in one language in TRAIN ("dá pra ...?" polite question as a request in pt), asked for
# in the other.
CRUZADO = [
    ("en", "E", "can you make the copyright bold?", [S("cp", "font-weight", "bold")], "cruzado", None),
    ("pt", "L", "você pode deixar o contato em itálico?", [S("rtx", "font-style", "italic")], "cruzado", None),
    ("en", "E", "the footer background has to be white", [S("ft", "background-color", "white")], "cruzado", None),
    ("pt", "L", "o fundo do painel tem que ser branco", [S("pai", "background-color", "white")], "cruzado", None),
]
