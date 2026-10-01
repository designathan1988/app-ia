"""A1 dialogues: whole conversations, turn by turn. The context of each turn is the discourse state after the
previous turns were carried out (avaliar.py runs them twice: with the gold history, and with the system's own
interpretations executed — the real conversation). A target "$new" is the element the previous turn created.
"""
from __future__ import annotations

from nucleo.lang.ir import Ref, Value, action

from acoes import H, INS, N, S, SEL, T, UNDO


def NEW_S(prop, value, op="SET"):
    return action("style.set", Ref("node", "$new"), property=prop, value=Value(value, op))


def NEW_N(name):
    return action("element.rename", Ref("node", "$new"), name=name)


def NEW_T(text):
    return action("text.set", Ref("node", "$new"), content=text)


DIALOGS = [
    ("pt", "L", [
        ("seleciona o segundo cartão", [SEL("c2")]),
        ("deixa ele mais largo", [S("c2", "width", "1.25", "MUL")]),
        ("agora aumenta o espaçamento interno do topo em 8px", [S("c2", "padding-top", "8px", "ADD")]),
        ("faz o mesmo no primeiro", [S("c1", "padding-top", "8px", "ADD")]),
        ("desfaz isso", [UNDO()]),
    ]),
    ("en", "E", [
        ("select the second button", [SEL("b2")]),
        ("make it wider", [S("b2", "width", "1.25", "MUL")]),
        ("now increase its top padding by 8px", [S("b2", "padding-top", "8px", "ADD")]),
        ("do the same to the first one", [S("b1", "padding-top", "8px", "ADD")]),
        ("undo that", [UNDO()]),
    ]),
    ("pt", "L", [
        ("adiciona um botão no rodapé", [INS("button", "rod", 1)]),
        ("deixa ele vermelho", [NEW_S("color", "red")]),
        ("renomeia ele para Contato", [NEW_N("Contato")]),
    ]),
    ("en", "E", [
        ("add a paragraph at the end of the sidebar", [INS("paragraph", "side", 2)]),
        ("write Hello there in it", [NEW_T("Hello there")]),
        ("make it italic", [NEW_S("font-style", "italic")]),
    ]),
    ("pt", "A", [
        ("esconde o terceiro cartão", [H("n-card-c")]),
        ("e o segundo também", [H("n-card-b")]),
        ("agora mostra o terceiro de novo", [H("n-card-c")]),
    ]),
    ("en", "A", [
        ("hide the third card", [H("n-card-c")]),
        ("and the second one too", [H("n-card-b")]),
        ("now show the third one again", [H("n-card-c")]),
    ]),
    ("pt", "E", [
        ("seleciona a barra lateral", [SEL("side")]),
        ("pinta o fundo dela de cinza", [S("side", "background-color", "gray")]),
        ("agora o cabeçalho", [S("hd", "background-color", "gray")]),
        ("renomeia ele para Topo", [N("hd", "Topo")]),
    ]),
    ("en", "L", [
        ("select the panel", [SEL("pai")]),
        ("make its background gray", [S("pai", "background-color", "gray")]),
        ("now the footer", [S("rod", "background-color", "gray")]),
        ("rename it to Base", [N("rod", "Base")]),
    ]),
]
