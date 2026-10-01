"""The intermediate meaning representation (IR): the same for Portuguese and English, and independent of any
handler. An utterance means a Plan; a Plan is grounded against the ActionSchema and the current page, and only
then executed.

- ``Ref``: what an action is about — a node of the page (``node``), the current selection (``selected``), the
  entity the conversation is about (``context``: "isso", "ele", "it"), everything of a kind (``all``), or a new
  element (``new``, with its element type).
- ``Value``: a literal or keyword (``SET``), or a change relative to the current value (``ADD``, ``SUB``, ``MUL``)
  — "20 pixels mais largo" is ``Value("20px", "ADD")``.
- ``Action``: an operation of the ActionSchema with its arguments (by the schema's argument names), and negation.
- ``Plan``: a sequence of actions (coordination and "depois" are sequences); the empty plan means nothing to do.

``canonical`` gives one string per meaning, used to compare meanings and to test that paraphrases in Portuguese and
English converge.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

UNIT = re.compile(r"^(-?\d+(?:\.\d+)?)([a-z%]*)$")


@dataclass(frozen=True)
class Ref:
    kind: str = "node"  # node | selected | context | all | new
    node: str | None = None  # the grounded node id (kind node)
    type: str | None = None  # an element type (kind all / new)

    def canonical(self) -> str:
        if self.kind == "node":
            return f"@{self.node}"
        if self.kind in ("all", "new"):
            return f"{self.kind}:{self.type}"
        return self.kind


@dataclass(frozen=True)
class Value:
    data: object
    op: str = "SET"  # SET | ADD | SUB | MUL | DIV

    def canonical(self) -> str:
        return f"{self.op}({self.data})" if self.op != "SET" else str(self.data)


@dataclass(frozen=True)
class Action:
    op: str
    target: Ref | None = None
    args: tuple = ()  # ((name, Value | Ref | str), ...) sorted by name
    negated: bool = False

    def arg(self, name):
        return dict(self.args).get(name)

    def canonical(self) -> str:
        parts = [self.op]
        if self.target is not None:
            parts.append(self.target.canonical())
        for k, v in self.args:
            parts.append(f"{k}={v.canonical() if hasattr(v, 'canonical') else v}")
        s = " ".join(parts)
        return f"NOT({s})" if self.negated else s


def action(op: str, target: Ref | None = None, **args) -> Action:
    return Action(op, target, tuple(sorted((k, v if isinstance(v, (Value, Ref)) else Value(v)) for k, v in args.items())))


@dataclass(frozen=True)
class Plan:
    steps: tuple = ()

    def canonical(self) -> str:
        return " ; ".join(a.canonical() for a in self.steps) if self.steps else "NONE"


NONE = Plan(())


# -- relative values --------------------------------------------------------------------------------------------
def quantity(v) -> tuple[float, str] | None:
    m = UNIT.match(str(v).strip()) if v is not None else None
    return (float(m.group(1)), m.group(2)) if m else None


def fmt(n: float, unit: str) -> str:
    return f"{int(n) if float(n).is_integer() else round(n, 3)}{unit}"


def resolve_value(v: Value, current: str | None) -> str | None:
    """The concrete value a relative Value gives from the current one (None when it cannot)."""
    if v.op == "SET":
        return str(v.data)
    cur = quantity(current) if current is not None else None
    if v.op in ("ADD", "SUB"):
        amt = quantity(v.data)
        if amt is None:
            return None
        base = cur if cur is not None and (cur[1] == amt[1] or not cur[1]) else (0.0, amt[1])
        n = base[0] + amt[0] if v.op == "ADD" else base[0] - amt[0]
        return fmt(max(n, 0.0), amt[1] or base[1])
    if v.op in ("MUL", "DIV"):
        if cur is None:
            return None
        f = float(v.data)
        return fmt(cur[0] * f if v.op == "MUL" else cur[0] / f, cur[1])
    return None
