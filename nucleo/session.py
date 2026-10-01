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
from types import SimpleNamespace

from .lang import dialogue, langs, learned
from .lang.understand import FRAMES, World, gapped_clauses, split_clauses, understand


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
        self.last_reading: tuple | None = None  # (verb, frame) of the last executed request
        self.dialog = dialogue.State()  # the open question, and the last thing done (for "o mesmo no botão")

    def document(self) -> dict:
        return self.b.call("stateOf", state=self.state)

    def ask(self, text: str) -> Answer:
        """One request, or several joined by "e (depois)": then all of them or none (atomic). A reply to the
        system's own question, or an elliptical follow-up of the last action, is read as such first."""
        reply = self._continue_dialogue(text)
        if reply is not None:
            self.history.append(reply)
            return reply
        clauses = split_clauses(text)
        if len(clauses) <= 1:
            gapped = gapped_clauses(text)
            if not gapped or self._understood(text):
                return self._ask_one(text)
            if not all(self._understood(c) for c in gapped):
                return self._ask_one(text)
            clauses = gapped  # "X e Y" read as "verbo X e verbo Y", since the whole was not understood as one
        start = self.state
        done = []
        for c in clauses:
            a = self._ask_one(c)
            self.history.pop()
            if not a.ok:
                self.state = start
                ans = Answer(text, a.decision, f"Nada foi feito: na parte «{c}»: {a.message}", [], False)
                self.history.append(ans)
                return ans
            done.append(a)
        ans = Answer(text, "executado", " Depois: ".join(a.message for a in done),
                     [c for a in done for c in a.commands], True)
        self.history.append(ans)
        return ans

    def _understood(self, text: str) -> bool:
        doc = self.document()
        return understand(text, World.from_document(doc["document"], doc["selection"])).decision == "executar"

    def _world(self) -> World:
        doc = self.document()
        return World.from_document(doc["document"], doc["selection"])

    def _continue_dialogue(self, text: str) -> Answer | None:
        p, self.dialog.pending = self.dialog.pending, None
        if p is not None:
            choice = dialogue.choose(p, text)
            if choice == "nao":
                return Answer(text, "comando", langs.msg("nothing_done", langs.detect(text)), [], True)
            if choice is not None:
                a = self._execute(text, choice, choice.paraphrase)
                self.history.pop()
                if a.ok and choice.verb:
                    self._induce(choice.verb, choice.frame, p.text)
                return a
            if p.verb:
                # the reply to "what does «x» do?" shows it: do that, and learn the verb's class from it
                u = understand(text, self._world())
                if u.decision == "executar":
                    a = self._execute(text, u.best, u.message)
                    self.history.pop()
                    if a.ok:
                        a.message += " " + self._learn_from_example(p.verb, u.best, f"{p.text} = {text}")
                    return a
        # an elliptical follow-up repeats the last action on another element: only an action on an element can be
        # repeated that way, and only on an element it did not already touch
        if self.dialog.last_nodes and dialogue.is_ellipsis(text) and not self._understood(text):
            with langs.use(langs.detect(text)):  # its words are matched in the language they were said in
                node = dialogue.ellipsis_target(text, self._world())
            if node is not None and node not in self.dialog.last_nodes:
                cons = dialogue.repeat_on(self.dialog.last_constraints, self.dialog.last_nodes, node)
                from .lang.understand import paraphrase

                with langs.use(langs.detect(text)):
                    said = paraphrase(cons, self._world())
                    message = langs.msg("same_again", what=said)
                r = SimpleNamespace(constraints=cons, verb="", frame="elipse", paraphrase=said, assumptions=[])
                a = self._execute(text, r, message)
                self.history.pop()
                return a
        return None

    def _learn_from_example(self, verb: str, reading, sentence: str) -> str:
        """What an unknown verb means, from the request the user gave as its example: the change it made, said in
        the core language and without its element ("definir o peso da fonte como bold"), so the verb then works on
        any element. Generated from the constraints, not copied from the reply."""
        from .lang.understand import _label, _regular_infinitives

        inf = (_regular_infinitives(verb) or [verb])[0]
        c = reading.constraints[0] if len(reading.constraints) == 1 else None
        body = None
        if c and c["kind"] == "style":
            body = f"definir o {_label('propriedade', c['property']).lower()} como {c['value']}"
        elif c and c["kind"] == "command":
            body = c["label"].lower()
        if body:
            learned.add_verb(inf, body, sentence, "usuario")
            return f"Aprendi: «{inf}» = «{body}»."
        if self._induce(inf, reading.frame, sentence):
            return f"Aprendi: «{inf}» age como «{reading.verb}»."
        return ""

    def _induce(self, verb: str, frame: str, sentence: str) -> bool:
        """A verb confirmed in a frame's meaning joins that frame's class (induction from one confirmed use)."""
        if any(f["id"] == frame for f in FRAMES["quadros"]) and not any(verb in f["verbos"] for f in FRAMES["quadros"]):
            learned.add_to_class(verb, frame, sentence, "usuario")
            return True
        return False

    def _ask_one(self, text: str) -> Answer:
        world = self._world()
        u = understand(text, world)
        if u.decision == "aprendido":
            a = Answer(text, u.decision, u.message, [], True)
            self.history.append(a)
            return a
        if u.decision != "executar":
            self.dialog.pending = dialogue.options_from(u, world)
            a = Answer(text, u.decision, u.message, [], False)
            self.history.append(a)
            return a
        return self._execute(text, u.best, u.message)

    def _execute(self, text: str, reading, message: str) -> Answer:
        """Carry out one reading (its constraints) on the document; on success it becomes the last thing done."""
        u = SimpleNamespace(best=reading, message=message)
        a = self._carry_out(text, u)
        if a.ok and a.decision == "executado":
            self.dialog.last_constraints = reading.constraints
            self.dialog.last_reading = reading
            self.dialog.last_nodes = [c["id"] for c in reading.constraints if isinstance(c.get("id"), str)]
        return a

    def _carry_out(self, text: str, u) -> Answer:
        if any(str(c.get("type", "")).startswith("estrutura:") for c in u.best.constraints):
            return self._build_structure(text, u)
        if any(c["kind"] == "command" for c in u.best.constraints):
            return self._run_command(text, u)
        r = self.planner.solve_constraints(self.state, u.best.constraints)
        if not r.solved:
            a = Answer(text, "sem_plano", langs.msg("no_plan", getattr(u, "lang", None) or langs.detect(text),
                                                    what=u.message), [], False)
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
            from .lang import preferences

            self.last_reading = (u.best.verb, u.best.frame)
            preferences.kept(*self.last_reading)
        self.history.append(a)
        return a

    def _run_command(self, text: str, u) -> Answer:
        """A verb that labels a builder command: select each element and run the command ("oculte todos os
        títulos": once per element). Every result must change the document and pass the builder's validator, or
        nothing is done; a flag an element already has is left as it is."""
        st, cmds = self.state, []
        for c in [c for c in u.best.constraints if c["kind"] == "command"]:
            if c.get("already"):
                continue
            seq = [{"command": "selection.select", "args": {"target": c["id"]}},
                   {"command": c["command"], "args": {}}]
            res = self.b.call("try", state=st, candidates=[{"sequence": seq}], keep=True)["results"][0]
            cmds += [x["command"] for x in seq]
            if res["status"] != "done" or not res.get("changed"):
                why = res.get("refusal") or res.get("reason") or res["status"]
                a = Answer(text, "recusado", f"O builder recusou «{c['label']}»: {why}", cmds, False)
                self.history.append(a)
                return a
            if res.get("problems") or self.b.validate(self.b.call("stateOf", state=res["state"])["document"]):
                a = Answer(text, "recusado", "O builder rejeitou o resultado.", cmds, False)
                self.history.append(a)
                return a
            st = res["state"]
        self.state = st
        a = Answer(text, "executado", u.message, cmds, True)
        from .lang import preferences

        self.last_reading = (u.best.verb, u.best.frame)
        preferences.kept(*self.last_reading)
        self.history.append(a)
        return a

    def _solve(self, constraints: list) -> list | None:
        r = self.planner.solve_constraints(self.state, constraints)
        if not r.solved:
            return None
        st = self.state
        for action in r.plan:
            st = self.b.call("try", state=st, candidates=[action], keep=True)["results"][0]["state"]
        self.state = st
        return [a["command"] for c in r.plan for a in c.get("sequence", [c])]

    def _build_structure(self, text: str, u) -> Answer:
        """A taught composite element: the head where it was asked, then each part inside it, in order; all or
        nothing."""
        from .builder.client import walk

        start = self.state
        c = next(c for c in u.best.constraints if str(c.get("type", "")).startswith("estrutura:"))
        name = c["type"].split(":", 1)[1]
        spec = learned.structures()[name]
        before = {n["id"] for p in self.document()["document"]["pages"] for n in walk(p["tree"])}
        cmds = self._solve([{**c, "type": spec["cabeca"]}])
        head_id = None
        if cmds is not None:
            doc = self.document()["document"]
            new = [n for p in doc["pages"] for n in walk(p["tree"]) if n["id"] not in before]
            head_id = next((n["id"] for n in new if n["type"] == spec["cabeca"]), None)
        for i, part in enumerate(spec["partes"]):
            if cmds is None or head_id is None:
                break
            more = self._solve([{"kind": "added", "type": part["type"], "parent": head_id, "index": i,
                                 **({"text": part["text"]} if part.get("text") else {})}])
            cmds = None if more is None else cmds + more
        if cmds is None or self.b.validate(self.document()["document"]):
            self.state = start
            a = Answer(text, "sem_plano", f"Não consegui montar «{name}»; nada foi feito.", [], False)
        else:
            a = Answer(text, "executado", f"{u.message} («{name}»: {spec['cabeca']} com "
                                          f"{len(spec['partes'])} parte(s))", cmds, True)
        self.history.append(a)
        return a

    def export(self) -> list[dict]:
        return self.b.export(self.document()["document"])
