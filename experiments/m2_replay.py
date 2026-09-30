"""M2 preliminary: how many builder-6 scenarios can the headless editor reproduce at all?

Every step of every scenario is replayed by dispatching its command with the
arguments its door fixes plus the step's own arguments. Node paths are resolved
to ids at dispatch time. The final document is then compared with the expected
one by the builder's own ``matchDocument``.

This does not test planning; the planner never sees the steps. It measures the
reachable set: a scenario that the real steps cannot reproduce headlessly
(because a door computes its arguments from pixels, the clipboard or a file)
is out of scope for the headless planner, and is reported with the reason.

Usage: python experiments/m2_replay.py [limit]
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from nucleo.builder.client import Builder  # noqa: E402
from nucleo.builder.scenarios import door_args, load_commands, load_fixture, load_scenarios  # noqa: E402

NODE_TYPES = {"node", "nodes"}


def wrap(value, typ):
    if typ == "node" and isinstance(value, str) and value.startswith("/"):
        return {"$node": value}
    if typ == "nodes" and isinstance(value, list):
        return [{"$node": v} if isinstance(v, str) and v.startswith("/") else v for v in value]
    return value


def gold_actions(commands, step):
    """The dispatches a step amounts to: a gesture on a node it does not pass as an argument selects it first."""
    command, args = door_args(commands, step["door"])
    args.update(step.get("args") or {})
    schema = commands.get(command, {}).get("args", {})
    actions = []
    target = step.get("target")
    if target and target not in args.values() and command != "selection.select":
        actions.append({"command": "selection.select", "args": {"target": {"$node": target}}})
    actions.append({"command": command, "args": {k: wrap(v, schema.get(k, {}).get("type")) for k, v in args.items()}})
    return actions


def main(limit: int | None = None) -> dict:
    commands = load_commands()
    scenarios = load_scenarios()[:limit]
    outcome = collections.Counter()
    reasons = collections.Counter()
    per = {}
    t0 = time.time()
    with Builder() as b:
        for s in scenarios:
            fixture = load_fixture(s.setup["fixture"])
            try:
                st = b.call("setup", document=fixture, selection=s.setup["selection"], locale=s.setup["locale"],
                            breakpoint=s.setup["breakpoint"], state=s.setup["state"])["state"]
                goal_base = fixture if fixture is not None else b.call("stateOf", state=st)["document"]
                b.call("goal", document=goal_base, diff=s.diff)
            except Exception as e:  # noqa: BLE001
                outcome["setup falhou"] += 1
                reasons[str(e)[:90]] += 1
                per[s.key] = "setup"
                continue
            failed = None
            for step in s.steps:
                for action in gold_actions(commands, step):
                    r = b.call("try", state=st, candidates=[action], keep=True)["results"][0]
                    if r["status"] != "done":
                        failed = f"{action['command']}: {r['status']} {str(r.get('message'))[:60]}"
                        break
                    st = r["state"]
                if failed:
                    break
            if failed:
                outcome["passo recusado/erro"] += 1
                reasons[failed[:90]] += 1
                per[s.key] = "passo"
                continue
            mism = b.call("stateOf", state=st)["mismatches"]
            if mism:
                outcome["documento difere"] += 1
                reasons[mism[0][:90]] += 1
                per[s.key] = "difere"
            else:
                outcome["reproduzido"] += 1
                per[s.key] = "ok"
    dt = time.time() - t0
    print(f"{len(scenarios)} cenários em {dt:.0f}s: {dict(outcome)}")
    for r, n in reasons.most_common(25):
        print(f"  {n:4d}  {r}")
    out = pathlib.Path(__file__).resolve().parents[1] / "data" / "cache" / "m2_replay.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(per, indent=0), encoding="utf-8")
    return per


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
