"""builder-6's own scenarios (manifest/features/*.json) as planning problems.

A scenario gives:

* a starting point: a fixture document, a selection, a language, a
  breakpoint and a style state;
* a sequence of steps through the editor's doors;
* the expected document, as a diff applied to the fixture.

For planning, only the starting point and the expected document are used. The
problem is to reach a document the builder's own ``matchDocument`` accepts
from the start, with no access to the steps. The steps are read only to check
that the headless editor can reproduce the scenario at all (``gold_steps``),
which bounds what any planner can reach.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass

from .client import DEFAULT_BUILDER


@dataclass(frozen=True)
class Scenario:
    feature: str
    id: str
    setup: dict
    diff: list
    steps: list  # read only by the reproducibility check, never by the planner

    @property
    def key(self) -> str:
        return f"{self.feature}/{self.id}"


def _root(root: str | None) -> pathlib.Path:
    return pathlib.Path(root or DEFAULT_BUILDER)


def load_scenarios(root: str | None = None, with_document_only: bool = True) -> list[Scenario]:
    out = []
    for path in sorted((_root(root) / "manifest" / "features").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for feature in data["features"]:
            for s in feature.get("scenarios", []):
                diff = s.get("expect", {}).get("document") or []
                if with_document_only and not diff:
                    continue
                out.append(Scenario(feature["id"], s["id"], s["setup"], diff, s["steps"]))
    return out


def load_fixture(name: str, root: str | None = None) -> dict | None:
    if name == "empty":
        return None
    return json.loads((_root(root) / "manifest" / "features" / "fixtures" / f"{name}.json").read_text(encoding="utf-8"))


def load_commands(root: str | None = None) -> dict[str, dict]:
    out = {}
    for path in sorted((_root(root) / "manifest" / "commands").glob("*.json")):
        for c in json.loads(path.read_text(encoding="utf-8"))["commands"]:
            out[c["id"]] = c
    return out


def door_args(commands: dict, door: str) -> tuple[str, dict]:
    """(command id, the arguments the door itself fixes) for a door reference "command#door"."""
    command, _, door_id = door.partition("#")
    for ep in commands.get(command, {}).get("entryPoints", []):
        if ep["id"] == door_id:
            return command, dict(ep.get("args") or {})
    return command, {}


def _wrap(value, typ):
    if typ == "node" and isinstance(value, str) and value.startswith("/"):
        return {"$node": value}
    if typ == "nodes" and isinstance(value, list):
        return [{"$node": v} if isinstance(v, str) and v.startswith("/") else v for v in value]
    return value


def gold_actions(commands: dict, step: dict) -> list[dict]:
    """The dispatches a step amounts to: a gesture on a node it does not pass as an argument selects it first."""
    command, args = door_args(commands, step["door"])
    args.update(step.get("args") or {})
    schema = commands.get(command, {}).get("args", {})
    actions = []
    target = step.get("target")
    if target and target not in args.values() and command != "selection.select":
        actions.append({"command": "selection.select", "args": {"target": {"$node": target}}})
    actions.append({"command": command, "args": {k: _wrap(v, schema.get(k, {}).get("type")) for k, v in args.items()}})
    return actions


def start(builder, scenario: Scenario, fixture: dict | None = None) -> int:
    """Set the scenario's starting point and goal in the headless editor; returns the start state."""
    fx = fixture if fixture is not None else load_fixture(scenario.setup["fixture"])
    s = scenario.setup
    st = builder.call("setup", document=fx, selection=s["selection"], locale=s["locale"],
                      breakpoint=s["breakpoint"], state=s["state"])["state"]
    base = fx if fx is not None else builder.call("stateOf", state=st)["document"]
    builder.call("goal", document=base, diff=scenario.diff)
    return st


def reproducible(builder, scenario: Scenario, commands: dict) -> bool:
    """Whether the scenario's own steps, dispatched headlessly, reach its expected document (the reachable set)."""
    try:
        st = start(builder, scenario)
    except Exception:  # noqa: BLE001 - a goal the builder's applyDiff rejects
        return False
    for step in scenario.steps:
        for action in gold_actions(commands, step):
            r = builder.call("try", state=st, candidates=[action], keep=True)["results"][0]
            if r["status"] != "done":
                return False
            st = r["state"]
    return not builder.call("stateOf", state=st)["mismatches"]
