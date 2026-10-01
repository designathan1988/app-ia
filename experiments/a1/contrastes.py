"""A1 contrast pairs against false hits: utterances close in their words but different in meaning. A pair counts
only if *both* are right, so a ranker that picks by word overlap fails it.

Pairs the plan asked for and how they are made with the operations the builder has:
- width vs margin, move vs margin, hide vs delete, select the parent vs move out of the parent: as asked;
- "duplicate vs copy style": the builder has no one-step copy of a style (clipboard.pasteStyle needs a copy made
  before, outside the history), so the pair is duplicate vs lock (element.toggleLock), another operation on the
  same element;
- "put below vs send backward": "send backward" needs a z-index value the utterance does not say; the pair is
  move down (element.moveDown, the order) vs a top margin (the spacing).
"""
from __future__ import annotations

from nucleo.lang.ir import Ref, action

from acoes import D, DUP, H, S


def A(op, node):
    return action(op, Ref("node", node))


PAIRS = [
    (("pt", "L", "aumenta a largura do banner em 20px", [S("ban", "width", "20px", "ADD")], "contraste", None),
     ("pt", "L", "aumenta a margem esquerda do banner em 20px", [S("ban", "margin-left", "20px", "ADD")],
      "contraste", None)),
    (("en", "E", "increase the image width by 20px", [S("im", "width", "20px", "ADD")], "contraste", None),
     ("en", "E", "increase the image left margin by 20px", [S("im", "margin-left", "20px", "ADD")],
      "contraste", None)),
    (("pt", "L", "move o banner para cima", [A("element.moveUp", "ban")], "contraste", None),
     ("pt", "L", "aumenta a margem superior do banner em 10px", [S("ban", "margin-top", "10px", "ADD")],
      "contraste", None)),
    (("en", "E", "move the image up", [A("element.moveUp", "im")], "contraste", None),
     ("en", "E", "increase the image top margin by 10px", [S("im", "margin-top", "10px", "ADD")],
      "contraste", None)),
    (("pt", "L", "esconde o contato", [H("rtx")], "contraste", None),
     ("pt", "L", "exclui o contato", [D("rtx")], "contraste", None)),
    (("en", "E", "hide the copyright", [H("cp")], "contraste", None),
     ("en", "E", "delete the copyright", [D("cp")], "contraste", None)),
    (("pt", "L", "duplica o painel", [DUP("pai")], "contraste", None),
     ("pt", "L", "bloqueia o painel", [A("element.toggleLock", "pai")], "contraste", None)),
    (("en", "E", "duplicate the sidebar", [DUP("side")], "contraste", None),
     ("en", "E", "lock the sidebar", [A("element.toggleLock", "side")], "contraste", None)),
    (("pt", "L", "seleciona o pai do botão Comprar agora", [A("selection.walkParent", "bt1")], "contraste", None),
     ("pt", "L", "tira o botão Comprar agora de dentro do pai", [A("element.promote", "bt1")], "contraste", None)),
    (("en", "E", "select the parent of the Get started button", [A("selection.walkParent", "b1")], "contraste",
      None),
     ("en", "E", "move the Get started button out of its parent", [A("element.promote", "b1")], "contraste",
      None)),
    (("pt", "L", "move o subtítulo para baixo", [A("element.moveDown", "sub")], "contraste", None),
     ("pt", "L", "coloca 10px de margem no topo do subtítulo", [S("sub", "margin-top", "10px")], "contraste",
      None)),
]
