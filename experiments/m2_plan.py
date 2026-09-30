"""M2 gate: plan from each builder-6 scenario's start to its expected document, without seeing its steps.

Reported over two denominators: all scenarios with a document expectation, and
those the headless editor can reproduce with the scenario's own steps
(``m2_replay.py``), which is the reachable set.

A plan counts as solved only if, replayed in the real editor, it reaches a
document the builder's own ``matchDocument`` accepts and the builder's own
validator finds no problem in any committed state. The scenario's steps are
read only after planning, to report whether the planner chose the same main
command.

Usage: python experiments/m2_plan.py [limit] [--effects-fresh]
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from nucleo.builder.client import Builder  # noqa: E402
from nucleo.builder.effects import CACHE, learn, load_model  # noqa: E402
from nucleo.builder.knowledge import load_domains  # noqa: E402
from nucleo.builder.planner import Planner  # noqa: E402
from nucleo.builder.rename import rename_scenario  # noqa: E402
from nucleo.builder.scenarios import Scenario, load_fixture, load_scenarios  # noqa: E402

DATA = pathlib.Path(__file__).resolve().parents[1] / "data" / "cache"


def verify(b, s, fx, plan) -> bool:
    """Replay the plan from a fresh setup; the builder's matchDocument and validator must both accept the result."""
    st = b.call("setup", document=fx, selection=s.setup["selection"], locale=s.setup["locale"],
                breakpoint=s.setup["breakpoint"], state=s.setup["state"])["state"]
    for action in plan:
        r = b.call("try", state=st, candidates=[action], keep=True)["results"][0]
        if r["status"] != "done" or r["problems"]:
            return False
        st = r["state"]
    final = b.call("stateOf", state=st)
    return not final["mismatches"] and not b.validate(final["document"])


def main(limit=None, fresh=False, rename=False):
    scenarios = load_scenarios()[:limit]
    fixtures = {}
    if rename:
        renamed = []
        for i, s in enumerate(scenarios):
            r = rename_scenario(load_fixture(s.setup["fixture"]), s.setup["selection"], s.diff, seed=i)
            if r is None:
                continue
            fx, sel, diff = r
            s2 = Scenario(s.feature, s.id, {**s.setup, "selection": sel}, diff, [])
            fixtures[s2.key] = fx
            renamed.append(s2)
        print(f"renomeáveis: {len(renamed)}/{len(scenarios)}")
        scenarios = renamed
    replay = json.loads((DATA / "m2_replay.json").read_text(encoding="utf-8"))
    domains = load_domains()
    out = {}
    stats = collections.Counter()
    t0 = time.time()
    with Builder() as b:
        model = learn(b) if fresh or not CACHE.exists() else load_model()
        planner = Planner(b, domains, model)
        for i, s in enumerate(scenarios):
            fx = fixtures[s.key] if rename else load_fixture(s.setup["fixture"])
            st = b.call("setup", document=fx, selection=s.setup["selection"], locale=s.setup["locale"],
                        breakpoint=s.setup["breakpoint"], state=s.setup["state"])["state"]
            base = fx if fx is not None else b.call("stateOf", state=st)["document"]
            try:
                b.call("goal", document=base, diff=s.diff)
            except Exception as e:  # noqa: BLE001
                out[s.key] = {"solved": False, "error": str(e)[:200]}
                stats["meta inválida"] += 1
                continue
            gd = b.call("goalDiff", state=st)
            start = gd["mismatches"]
            r = planner.solve(st, start, gd["distance"])
            verified = False
            if r.solved:
                verified = verify(b, s, fx, r.plan)
                stats["verificado de novo"] += verified
            gold = [x["door"].split("#")[0] for x in s.steps if x.get("action")]
            used = [a["command"] for c in r.plan for a in c.get("sequence", [c])]
            reach = replay.get(s.key) == "ok"
            stats["resolvido" if r.solved else "não resolvido"] += 1
            if reach:
                stats["alcançáveis"] += 1
                stats["alcançáveis resolvidos"] += r.solved
            if r.solved:
                stats["mesmo comando principal"] += bool(set(gold) & set(used))
            out[s.key] = {"solved": r.solved, "verified": verified, "plan": r.plan, "left": r.mismatches, "start": start,
                          "expansions": r.expansions, "tries": r.tries, "gold": gold, "reachable": reach}
            if (i + 1) % 100 == 0:
                print(f"  {i + 1}/{len(scenarios)} {dict(stats)} {time.time() - t0:.0f}s", flush=True)
    n = len(scenarios)
    print(f"\n{n} cenários em {time.time() - t0:.0f}s")
    print(dict(stats))
    print(f"resolvidos: {stats['resolvido']}/{n} = {stats['resolvido'] / n:.1%}; alcançáveis: "
          f"{stats['alcançáveis resolvidos']}/{stats['alcançáveis']} = "
          f"{stats['alcançáveis resolvidos'] / max(stats['alcançáveis'], 1):.1%}")
    name = "m2_plan_renomeado.json" if rename else "m2_plan.json"
    (DATA / name).write_text(json.dumps(out, indent=0, default=str), encoding="utf-8")
    if rename:
        orig = json.loads((DATA / "m2_plan.json").read_text(encoding="utf-8"))
        a = sum(orig[k]["solved"] for k in out if k in orig)
        c = sum(v["solved"] for v in out.values())
        print(f"mesmo subconjunto: nomes originais {a}/{len(out)}; nomes inventados {c}/{len(out)}")
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(int(args[0]) if args else None, "--effects-fresh" in sys.argv, "--rename" in sys.argv)
