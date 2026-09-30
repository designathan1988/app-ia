"""A working session with builder-6: Portuguese requests in, edits of the real document out.

Each request is understood against the current document. When the decision is "executar", the planner finds the
commands and the session moves to the resulting state. Every state is validated by the builder itself. A request
that is asked about or not understood leaves the document untouched.
"""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass

from .builder.client import Builder
from .builder.effects import CACHE, learn, load_model
from .builder.knowledge import load_domains
from .builder.planner import Planner
from .lang.understand import World, understand


def low_priority() -> None:
    """Run below normal priority (children inherit it): the user's machine must stay usable."""
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)


@dataclass
class Answer:
    request: str
    decision: str
    message: str
    commands: list
    ok: bool


class Session:
    def __init__(self, builder: Builder, document: dict | None = None, locale: str = "pt-BR") -> None:
        self.b = builder
        self.planner = Planner(builder, load_domains(), load_model() if CACHE.exists() else learn(builder))
        self.state = builder.call("setup", document=document, selection=[], locale=locale)["state"]
        self.history: list[Answer] = []

    def document(self) -> dict:
        return self.b.call("stateOf", state=self.state)

    def ask(self, text: str) -> Answer:
        doc = self.document()
        u = understand(text, World.from_document(doc["document"], doc["selection"]))
        if u.decision == "aprendido":
            a = Answer(text, u.decision, u.message, [], True)
            self.history.append(a)
            return a
        if u.decision != "executar":
            a = Answer(text, u.decision, u.message, [], False)
            self.history.append(a)
            return a
        r = self.planner.solve_constraints(self.state, u.best.constraints)
        if not r.solved:
            a = Answer(text, "sem_plano", f"Entendi «{u.message}», mas não achei comandos que façam isso.", [], False)
            self.history.append(a)
            return a
        st = self.state
        for action in r.plan:
            res = self.b.call("try", state=st, candidates=[action], keep=True)["results"][0]
            st = res["state"]
        problems = self.b.validate(self.b.call("stateOf", state=st)["document"])
        cmds = [a["command"] for c in r.plan for a in c.get("sequence", [c])]
        if problems:
            a = Answer(text, "recusado", f"O builder rejeitou o resultado: {problems[:1]}", cmds, False)
        else:
            self.state = st
            a = Answer(text, "executado", u.message, cmds, True)
        self.history.append(a)
        return a

    def export(self) -> list[dict]:
        return self.b.export(self.document()["document"])
