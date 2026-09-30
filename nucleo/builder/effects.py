"""Learning what each builder command does, by experiment (an action model learned from observation).

The manifest declares each command's arguments but not its effect on the
document. The effect is learned by running the command in the real headless
editor, in training states, and describing the change with the same
vocabulary the planner uses for goals (``itemFields``): ``node:added``,
``node:moved``, ``node:text``, ``style:<property>``, ``doc:tokens``, …

* **Training states:** the builder's own fixtures, with no selection and with
  each of a sample of nodes selected.
* **Arguments:** generated only from the manifest's domains (enum values,
  property value subsets, palette entries) and from the training document's
  own nodes. Goal documents are never read here.

Two kinds of knowledge result, each with its evidence count:

* ``escreve(C, F)``: command C was observed to make a change of kind F.
* ``estilo_parametrico(C)``: whenever C wrote styles, it wrote exactly the
  property named by its ``property`` argument, in every observation and never
  otherwise. This is an inductive generalisation. It is kept only with enough
  support and no counterexample, and is revised as soon as one appears.

The result is saved with its provenance (``data/cache/efeitos.json``) and
turned into Datalog facts (``facts()``) for the planner's relevance rules.
"""

from __future__ import annotations

import itertools
import json
import pathlib
import random
from dataclasses import dataclass, field

from .client import Builder, walk
from .knowledge import Domains, load_domains
from .scenarios import load_fixture

CACHE = pathlib.Path(__file__).resolve().parents[2] / "data" / "cache" / "efeitos.json"
TRAINING_FIXTURES = ["empty", "aurora", "table", "grid-page", "form-controls"]
MIN_SUPPORT = 3


@dataclass
class EffectModel:
    writes: dict[str, dict[str, int]] = field(default_factory=dict)  # command -> field -> observations
    runs: dict[str, dict[str, int]] = field(default_factory=dict)  # command -> status -> count
    param_ok: dict[str, int] = field(default_factory=dict)
    param_bad: dict[str, int] = field(default_factory=dict)

    def parametric(self, command: str) -> bool:
        return self.param_ok.get(command, 0) >= MIN_SUPPORT and self.param_bad.get(command, 0) == 0

    def fields(self, command: str) -> set[str]:
        return set(self.writes.get(command, {}))

    def to_json(self) -> dict:
        return {"writes": self.writes, "runs": self.runs, "param_ok": self.param_ok, "param_bad": self.param_bad}

    @classmethod
    def from_json(cls, d: dict) -> "EffectModel":
        return cls(d["writes"], d["runs"], d["param_ok"], d["param_bad"])

    def facts(self) -> str:
        """The learned model as Datalog facts (strings are quoted constants)."""
        lines = []
        for c, fs in sorted(self.writes.items()):
            for f in sorted(fs):
                if f.startswith("style:"):
                    lines.append(f'escreve_estilo("{c}", "{f[6:]}").')
                else:
                    lines.append(f'escreve("{c}", "{f}").')
            if self.parametric(c):
                lines.append(f'estilo_parametrico("{c}").')
        return "\n".join(lines)


def _explore_args(domains: Domains, command: str, doc: dict | None, selection: list, rng: random.Random, k: int = 6):
    nodes = [n["id"] for p in (doc or {}).get("pages", []) for n in walk(p["tree"])] if doc else []
    pages = [p["id"] for p in (doc or {}).get("pages", [])]
    spec = domains.args(command)
    styled = [p for p, vs in domains.properties.items() if vs]
    choices: dict[str, list] = {}
    prop_pick = rng.sample(styled, min(3, len(styled))) + ["width"]
    for name, s in spec.items():
        t = s["type"]
        vals: list
        if t in domains.unsupported_types:
            vals = [] if s.get("optional") else [None]
        elif t == "node":
            vals = (selection[:1] or []) + rng.sample(nodes, min(2, len(nodes)))
        elif t == "nodes":
            vals = [selection[:1]] if selection else [rng.sample(nodes, 1)] if nodes else [[]]
        elif t == "property":
            vals = prop_pick
        elif t == "string":
            vals = ["Novo", "10px"]
        elif t == "enum":
            vals = list(s.get("values") or [])[:4]
        elif t == "palette-entry":
            vals = rng.sample(sorted(domains.palette), 4)
        elif t in ("number",):
            vals = [1, 10]
        elif t == "integer":
            vals = [0, 1]
        elif t == "json":
            vals = [{}, [], "x"]
        elif t == "boolean":
            vals = [True, False]
        elif t == "color":
            vals = ["#ff0000"]
        elif t == "attribute":
            vals = ["title", "id"]
        elif t == "path":
            vals = pages[:2]
        elif t == "breakpoint":
            vals = domains.breakpoints
        elif t == "state":
            vals = domains.states[:3]
        else:
            vals = [None]
        if s.get("optional"):
            vals = [...] + vals  # Ellipsis marks "omit this argument"
        choices[name] = vals or [...]
    out = []
    seen = set()
    for _ in range(k * 4):
        args = {}
        for name, vals in choices.items():
            v = rng.choice(vals)
            if v is ...:
                continue
            args[name] = v
        # a string value goes with the property it is written to: use one of that property's declared values
        if "property" in args and isinstance(args.get("value"), str) and domains.properties.get(args["property"]):
            args["value"] = rng.choice(domains.properties[args["property"]])
        key = json.dumps(args, sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(args)
        if len(out) >= k:
            break
    return out


def learn(builder: Builder | None = None, seed: int = 0, per_fixture_selections: int = 8) -> EffectModel:
    domains = load_domains()
    model = EffectModel()
    rng = random.Random(seed)
    own = builder is None
    b = builder or Builder()
    try:
        for fx in TRAINING_FIXTURES:
            doc = load_fixture(fx)
            st0 = b.call("setup", document=doc, selection=[], locale="en")["state"]
            if doc is None:
                doc = b.call("stateOf", state=st0)["document"]
            names = {}
            for p in doc["pages"]:
                for path, node in _paths(p["tree"]):
                    names[node["id"]] = path
            ids = [i for i in names if names[i].count("/") > 1]
            sample = [[]] + [[i] for i in rng.sample(ids, min(per_fixture_selections, len(ids)))]
            for sel in sample:
                st = b.call("setup", document=None if fx == "empty" else doc,
                            selection=[names[i] for i in sel], locale="en")["state"]
                for command in sorted(domains.commands):
                    if not domains.plannable(command):
                        continue
                    cands = _explore_args(domains, command, doc, sel, rng)
                    res = b.call("try", state=st, candidates=[{"command": command, "args": a} for a in cands],
                                 fields=True)["results"]
                    for args, r in zip(cands, res):
                        runs = model.runs.setdefault(command, {})
                        runs[r["status"]] = runs.get(r["status"], 0) + 1
                        if r["status"] != "done" or not r.get("fields"):
                            continue
                        w = model.writes.setdefault(command, {})
                        for f in r["fields"]:
                            w[f] = w.get(f, 0) + 1
                        styles = {f[6:] for f in r["fields"] if f.startswith("style:")}
                        if "property" in args and styles:
                            if styles == {args["property"]}:
                                model.param_ok[command] = model.param_ok.get(command, 0) + 1
                            else:
                                model.param_bad[command] = model.param_bad.get(command, 0) + 1
    finally:
        if own:
            b.close()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(model.to_json(), indent=1, sort_keys=True), encoding="utf-8")
    return model


def _paths(tree: dict, prefix: str = ""):
    path = f"{prefix}/{tree['name']}"
    yield path, tree
    for c in tree.get("children", []):
        yield from _paths(c, path)


def load_model() -> EffectModel:
    return EffectModel.from_json(json.loads(CACHE.read_text(encoding="utf-8")))


if __name__ == "__main__":
    import time

    t = time.time()
    m = learn()
    print(f"aprendido em {time.time() - t:.0f}s: {len(m.writes)} comandos com efeito observado; "
          f"paramétricos: {sorted(c for c in m.writes if m.parametric(c))}")
    for c in itertools.islice(sorted(m.writes), 400):
        print(f"  {c}: {sorted(m.writes[c])}")
