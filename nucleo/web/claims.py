"""Claims from the web, and when they may become knowledge ("aprovar antes de aprender").

A claim is a fact with its source. Every claim first enters the context ``web_nao_verificada``, which only views
that inherit from it can see. It becomes knowledge (context ``conhecimento``) in two steps:

1. **Verification, by rules** (``VERIFICATION``):
   - a claim from a structured source (a registry answer) is verified when a second, fresh retrieval reproduces it;
   - any other claim needs two sources from independent sites.
2. **Approval by the user.** Verified claims wait in a queue (``pending``). Only an approval (``approve``) promotes
   them to ``conhecimento``, with the source, the verification and the approval recorded in the transaction note.
   Nothing is learned silently.

The only suggestions the system may make are packages whose existence is knowledge (``can_suggest``), so it never
suggests a package that does not exist.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from ..kb.syntax import PredKey, Text, parse_program
from ..logic.engine import evaluate
from ..store.db import Store
from ..code.resolve import _q

VERIFICATION = """
pred alegacao/1 fechado. pred fonte/2 fechado. pred estruturada/1 fechado. pred reproduzida/1 fechado.
pred sitio/2 fechado. pred verificada/1 fechado.
verificada(C) :- alegacao(C), estruturada(C), reproduzida(C).
verificada(C) :- alegacao(C), fonte(C, S1), fonte(C, S2), sitio(S1, D1), sitio(S2, D2), D1 != D2.
"""

WEB = "web_nao_verificada"
KNOWN = "conhecimento"


def _site(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


class Claims:
    def __init__(self, store: Store) -> None:
        self.store = store
        kb = store.contexts()
        with store.transaction("nucleo", "contextos de conhecimento e web") as tx:
            if KNOWN not in kb:
                tx.define(KNOWN)
            if WEB not in kb:
                tx.define(WEB, [KNOWN])
        self._evidence: dict[str, dict] = {}  # claim text -> {"sources": set, "structured": bool, "reproduced": bool}

    def record(self, fact: str, source: str, structured: bool) -> None:
        """A claim `fact` (one Datalog fact) seen at `source`."""
        with self.store.transaction("web", f"alegação de {source}") as tx:
            tx.assert_(WEB, fact, fonte=source)
        ev = self._evidence.setdefault(fact, {"sources": set(), "structured": structured, "reproduced": False})
        if source in ev["sources"] and structured:
            ev["reproduced"] = True
        ev["sources"].add(source)

    def verified(self) -> dict[str, dict]:
        lines = [VERIFICATION]
        for i, (fact, ev) in enumerate(self._evidence.items()):
            lines.append(f"alegacao({i}).")
            if ev["structured"]:
                lines.append(f"estruturada({i}).")
            if ev["reproduced"]:
                lines.append(f"reproduzida({i}).")
            for s in ev["sources"]:
                lines.append(f"fonte({i}, {_q(s)}).")
                lines.append(f"sitio({_q(s)}, {_q(_site(s))}).")
        m = evaluate(parse_program("\n".join(lines)))
        ok = {a.args[0] for a in m.atoms(PredKey("verificada", 1))}
        facts = list(self._evidence)
        return {facts[i]: self._evidence[facts[i]] for i in ok}

    def pending(self) -> list[str]:
        known = self.store.contexts().view(KNOWN).program.facts
        known_text = {f"{f}." for f in known}
        return sorted(f for f in self.verified() if parse_program(f).facts[0].__str__() + "." not in known_text)

    def approve(self, facts: list[str], by: str) -> None:
        verified = self.verified()
        for fact in facts:
            if fact not in verified:
                raise ValueError(f"não verificada, não pode ser aprovada: {fact}")
        with self.store.transaction(by, "aprovação de conhecimento vindo da web") as tx:
            for fact in facts:
                ev = verified[fact]
                note = json.dumps({"fontes": sorted(ev["sources"]), "estruturada": ev["structured"],
                                   "reproduzida": ev["reproduced"], "aprovado_por": by}, ensure_ascii=False)
                tx.assert_(KNOWN, fact, fonte=note)

    def can_suggest(self, ecosystem: str, name: str) -> bool:
        program = self.store.contexts().view(KNOWN).program
        return any(f.pred.name == "pacote_existe" and f.args == (Text(ecosystem), Text(name)) for f in program.facts)
