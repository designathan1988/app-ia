"""Planning over builder-6's real commands: from a start state to a goal document.

The loop is means-ends analysis with best-first search, over the real headless
editor. Each iteration does five things:

1. **Difference.** The structured difference between the current document and
   the goal (``goalDiff``) lists what is still needed: a style property on a
   node, a node added under a parent, a node moved, a text or a field changed.
2. **Relevance, by deduction.** The learned effect model (``effects.py``) is
   loaded as Datalog facts. Rules in the knowledge core derive which command
   can produce which needed change. The proof of each relevance is kept, and
   it becomes the explanation of the plan.
3. **Arguments, by abduction.** For each needed item and each relevant command,
   the arguments are hypotheses taken from the item itself, filtered by the
   type each argument declares in the manifest:
   - the node it concerns, or its parent;
   - the property and value it needs;
   - the palette entry whose element type it adds;
   - the position it must reach.
4. **Preconditions.** A command that acts on the selection is also tried after
   selecting the node the item concerns. A style needed at another breakpoint
   or state is also tried after switching the editor to that layer.
5. **Simulation.** Every candidate runs in the real editor. The builder's own
   ``matchDocument`` measures the distance to the goal, and every committed
   state is validated by the builder's own validator. States closer to the
   goal are expanded first.

What the planner sees: the start state and the goal document. It never sees
how the goal was produced.
"""

from __future__ import annotations

import heapq
import itertools
import json
from dataclasses import dataclass, field

from ..kb.syntax import Atom, PredKey, Text, parse_program
from ..logic.engine import evaluate
from ..logic.proof import proof_tree
from .client import Builder
from .effects import EffectModel
from .knowledge import Domains

RELEVANCE_RULES = """
relevante(C, F) :- precisa(F), escreve(C, F).
relevante(C, P) :- precisa_estilo(P), escreve_estilo(C, P).
relevante(C, P) :- precisa_estilo(P), estilo_parametrico(C).
"""


def need_of(item: dict) -> str:
    if item["kind"] == "style":
        return item["property"]
    if item["kind"] == "doc":
        return f"doc:{item['field']}"
    if item["kind"] == "field":
        return f"node:{item['field']}"
    return f"node:{item['kind']}"


def _numbers(v) -> list:
    if isinstance(v, bool):
        return []
    if isinstance(v, (int, float)):
        return [v]
    if isinstance(v, str):
        num = ""
        for ch in v:
            if ch.isdigit() or ch in ".-":
                num += ch
            else:
                break
        try:
            return [float(num) if "." in num else int(num)] if num not in ("", "-", ".") else []
        except ValueError:
            return []
    return []


@dataclass
class PlanResult:
    solved: bool
    plan: list
    mismatches: int
    expansions: int
    tries: int
    why: dict = field(default_factory=dict)  # command -> proof of relevance (as data)


class Planner:
    def __init__(self, builder: Builder, domains: Domains, model: EffectModel,
                 max_expansions: int = 12, per_item: int = 24, beam: int = 6) -> None:
        self.b = builder
        self.d = domains
        self.model = model
        self.max_expansions = max_expansions
        self.per_item = per_item
        self.beam = beam
        self._facts = model.facts()

    # -- relevance, deduced by the knowledge core --------------------------------------------------------------
    def relevance(self, items: list[dict]) -> tuple[dict[str, set], dict]:
        needs = set()
        lines = [self._facts, RELEVANCE_RULES]
        for it in items:
            n = need_of(it)
            needs.add(n)
            if it["kind"] == "style":
                lines.append(f'precisa_estilo("{n}").')
            else:
                lines.append(f'precisa("{n}").')
        model = evaluate(parse_program("\n".join(lines)))
        by_need: dict[str, set] = {n: set() for n in needs}
        proofs = {}
        for atom in model.atoms(PredKey("relevante", 2)):
            c, n = atom.args[0].value, atom.args[1].value
            by_need.setdefault(n, set()).add(c)
            proofs.setdefault(c, proof_tree(model, atom))
        return by_need, proofs

    # -- arguments, by abduction from one needed item ------------------------------------------------------------
    def _arg_values(self, command: str, name: str, spec: dict, item: dict, selection: list) -> list:
        t = spec["type"]
        node_ids = [x for x in (item.get("id"), item.get("parent")) if isinstance(x, str)]
        if t in self.d.unsupported_types:
            return []
        if t == "node":
            return list(dict.fromkeys(node_ids + selection[:1]))
        if t == "nodes":
            return [[x] for x in dict.fromkeys(node_ids)] + ([selection] if selection else [])
        if t == "property":
            return [item["property"]] if item["kind"] == "style" else []
        if t == "string":
            vals = [item.get("value")] if isinstance(item.get("value"), str) else []
            if item["kind"] == "added":
                vals += [item.get("text"), item.get("name")]
            if item["kind"] == "field" and isinstance(item.get("value"), dict):
                vals += [v for v in item["value"].values() if isinstance(v, str)]
            return [v for v in dict.fromkeys(vals) if isinstance(v, str)]
        if t == "palette-entry":
            return [e for e, typ in self.d.palette.items() if typ == item.get("type")] if item["kind"] == "added" else []
        if t in ("integer", "number"):
            vals = []
            if "index" in item:
                vals.append(item["index"])
            for v in _numbers(item.get("value")):
                vals.append(v)
                for c in _numbers(item.get("current")):
                    vals.append(v - c)
            return list(dict.fromkeys(v for v in vals if t == "number" or isinstance(v, int)))
        if t == "json":
            vals = [item.get("value")] if item["kind"] in ("field", "doc") else []
            if item["kind"] == "field" and isinstance(item.get("value"), dict):
                cur = item.get("current") or {}
                vals += [v for k, v in item["value"].items() if cur.get(k) != v]
            return vals
        if t == "attribute":
            if item["kind"] == "field" and isinstance(item.get("value"), dict):
                cur = item.get("current") or {}
                return [k for k, v in item["value"].items() if cur.get(k) != v]
            return []
        if t == "color":
            v = item.get("value")
            return [v] if isinstance(v, str) and (v.startswith("#") or v.startswith("rgb")) else []
        if t == "enum":
            return list(spec.get("values") or [])
        if t == "boolean":
            return [True, False]
        if t == "breakpoint":
            return [item["breakpoint"]] if item["kind"] == "style" else []
        if t == "state":
            return [item["state"]] if item["kind"] == "style" else []
        return []

    def bindings(self, command: str, item: dict, selection: list) -> list[dict]:
        per_arg = []
        for name, spec in self.d.args(command).items():
            vals = self._arg_values(command, name, spec, item, selection)
            if spec.get("optional"):
                vals = [...] + vals
            if not vals:
                return []  # a required argument the item cannot explain: this command does not explain it
            per_arg.append((name, vals))
        out = []
        for combo in itertools.product(*[v for _, v in per_arg]):
            out.append({n: v for (n, _), v in zip(per_arg, combo) if v is not ...})
            if len(out) >= self.per_item:
                break
        return out

    def candidates(self, items: list[dict], selection: list, by_need: dict[str, set]) -> list[dict]:
        out, seen = [], set()

        def add(action):
            key = json.dumps(action, sort_keys=True, default=str)
            if key not in seen:
                seen.add(key)
                out.append(action)

        for item in items:
            for command in sorted(by_need.get(need_of(item), ())):
                if not self.d.plannable(command):
                    continue
                prefixes: list[list] = [[]]
                focus = item.get("id") if isinstance(item.get("id"), str) else item.get("parent")
                if isinstance(focus, str) and selection != [focus]:
                    prefixes.append([{"command": "selection.select", "args": {"target": focus}}])
                if item["kind"] == "style" and (item["breakpoint"], item["state"]) != ("desktop", "base"):
                    layer = [{"command": "view.setBreakpoint", "args": {"breakpoint": item["breakpoint"]}},
                             {"command": "view.setStyleState", "args": {"state": item["state"]}}]
                    prefixes += [layer + p for p in list(prefixes)]
                for args in self.bindings(command, item, selection):
                    for pre in prefixes:
                        act = {"command": command, "args": args}
                        add({"sequence": pre + [act]} if pre else act)
        return out

    # -- search -------------------------------------------------------------------------------------------------
    def solve(self, state: int, start_mismatches: int, start_distance: int | None = None) -> PlanResult:
        """Best-first on (distance, mismatches): the graded leaf distance guides, matchDocument decides success."""
        d0 = start_distance if start_distance is not None else start_mismatches
        frontier = [((d0, start_mismatches), 0, state, [])]
        best = ((d0, start_mismatches), state, [])
        tries = expansions = 0
        why: dict = {}
        seen = set()
        while frontier and expansions < self.max_expansions:
            h, depth, st, plan = heapq.heappop(frontier)
            if h[1] == 0:
                return PlanResult(True, plan, 0, expansions, tries, why)
            expansions += 1
            g = self.b.call("goalDiff", state=st)
            by_need, proofs = self.relevance(g["items"])
            cands = self.candidates(g["items"], g["selection"], by_need)
            if not cands:
                continue
            res = self.b.call("try", state=st, candidates=cands, keep=True, fields=True)["results"]
            tries += len(cands)
            children = []
            for cand, r in zip(cands, res):
                self._observe(cand, r)
                if r["status"] != "done" or not r.get("changed") or r.get("problems"):
                    continue
                h2 = (r["distance"], r["mismatches"])
                if h2 >= h:
                    continue  # only moves that bring the document closer to the goal
                children.append((h2, cand, r["state"]))
            children.sort(key=lambda x: (x[0], len(json.dumps(x[1]))))
            for h2, cand, s2 in children[: self.beam]:
                key = (h2, json.dumps(cand, sort_keys=True, default=str))
                if key in seen:
                    continue
                seen.add(key)
                for a in cand.get("sequence", [cand]):
                    if a["command"] in proofs:
                        why.setdefault(a["command"], proofs[a["command"]])
                heapq.heappush(frontier, (h2, depth + 1, s2, plan + [cand]))
                if h2 < best[0]:
                    best = (h2, s2, plan + [cand])
        return PlanResult(False, best[2], best[0][1], expansions, tries, why)

    def solve_constraints(self, state: int, items: list[dict]) -> PlanResult:
        """Reach a goal given as constraint items (what language understanding produces), not as a document.
        Success: every constraint holds and the builder's validator accepts every committed state."""
        self.b.call("constraints", state=state, items=items)
        h0 = self.b.call("unsatisfied", state=state)["count"]
        frontier = [(h0, 0, state, [])]
        best = (h0, state, [])
        tries = expansions = 0
        why: dict = {}
        seen = set()
        while frontier and expansions < self.max_expansions:
            h, depth, st, plan = heapq.heappop(frontier)
            if h == 0:
                return PlanResult(True, plan, 0, expansions, tries, why)
            expansions += 1
            u = self.b.call("unsatisfied", state=st)
            by_need, proofs = self.relevance(u["items"])
            cands = self.candidates(u["items"], u["selection"], by_need)
            if not cands:
                continue
            res = self.b.call("try", state=st, candidates=cands, keep=True)["results"]
            tries += len(cands)
            children = []
            for cand, r in zip(cands, res):
                if r["status"] != "done" or not r.get("changed") or r.get("problems"):
                    continue
                if r["unsatisfied"] >= h:
                    continue
                children.append((r["unsatisfied"], cand, r["state"]))
            children.sort(key=lambda x: (x[0], len(json.dumps(x[1]))))
            for h2, cand, s2 in children[: self.beam]:
                key = (h2, json.dumps(cand, sort_keys=True, default=str))
                if key in seen:
                    continue
                seen.add(key)
                for a in cand.get("sequence", [cand]):
                    if a["command"] in proofs:
                        why.setdefault(a["command"], proofs[a["command"]])
                heapq.heappush(frontier, (h2, depth + 1, s2, plan + [cand]))
                if h2 < best[0]:
                    best = (h2, s2, plan + [cand])
        return PlanResult(False, best[2], best[0], expansions, tries, why)

    def _observe(self, cand: dict, r: dict) -> None:
        """Online learning: every simulated single command adds evidence to the effect model."""
        if "sequence" in cand or r["status"] != "done" or not r.get("fields"):
            return
        w = self.model.writes.setdefault(cand["command"], {})
        for f in r["fields"]:
            w[f] = w.get(f, 0) + 1
