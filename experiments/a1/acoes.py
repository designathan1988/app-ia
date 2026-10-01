"""Gold actions of the A1 corpus, written in the IR (nucleo/lang/ir.py) over ActionSchema operations."""
from __future__ import annotations

from nucleo.lang.ir import Ref, Value, action


def S(node, prop, value, op="SET"):
    """style.set: the node's property becomes value (or changes by it: ADD, SUB, MUL, DIV)."""
    return action("style.set", Ref("node", node), property=prop, value=Value(value, op))


def T(node, text):
    return action("text.set", Ref("node", node), content=text)


def N(node, name):
    return action("element.rename", Ref("node", node), name=name)


def D(node):
    return action("element.delete", Ref("node", node))


def H(node):
    return action("element.toggleHidden", Ref("node", node))


def DUP(node):
    return action("element.duplicate", Ref("node", node))


def SEL(node):
    return action("selection.select", Ref("node", node))


def INS(etype, parent, index):
    return action("element.insert", Ref("new", type=etype), parent=Ref("node", parent), index=Value(index))


def MOV(node, parent, index):
    return action("element.moveTo", Ref("node", node), parent=Ref("node", parent), index=Value(index))


def UNDO():
    return action("history.undo")
