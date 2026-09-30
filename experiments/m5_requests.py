"""M5 gate: Portuguese requests -> understanding -> planner -> the builder scenario's expected document.

For each builder scenario whose goal is one describable change, the test generator (tests/gen/requests.py) realizes
Portuguese requests. The system understands each one against the start document, as constraints; the planner (M2)
reaches them through the real editor; the builder's own matchDocument judges the final document against the
scenario's expected one.

Metrics (plan §11):
- top-1: executed and correct;
- silent error: executed and wrong;
- asked or refused: neither executed nor wrong.
All three are also measured with node names replaced by invented words (§7).

Usage: python experiments/m5_requests.py [per-scenario] [--rename] [--limit=N]
"""
from __future__ import annotations

import collections
import json
import pathlib
import random
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from nucleo.builder.client import Builder, walk  # noqa: E402
from nucleo.builder.effects import CACHE, learn, load_model  # noqa: E402
from nucleo.builder.knowledge import load_domains  # noqa: E402
from nucleo.builder.planner import Planner  # noqa: E402
from nucleo.builder.rename import rename_scenario  # noqa: E402
from nucleo.builder.scenarios import Scenario, load_fixture, load_scenarios, start  # noqa: E402
from nucleo.lang.understand import World, understand  # noqa: E402
from tests.gen.requests import realize  # noqa: E402

DATA = pathlib.Path(__file__).resolve().parents[1] / "data" / "cache"


def nodes_of(doc):
    out = {}
    for p in doc["pages"]:
        for n in walk(p["tree"]):
            if "id" not in n:
                continue  # a node the goal adds: it has no id yet
            out[n["id"]] = {"name": n.get("name"), "type": n.get("type"),
                            "children": [c.get("id") for c in n.get("children", []) if "id" in c]}
    return out


def default_node(b, domains, typ, locale, cache={}):
    """The node the builder creates for a type in a language (test side: to know what a request must say)."""
    key = (typ, locale)
    if key not in cache:
        entry = next((e for e, t in domains.palette.items() if t == typ), None)
        node = None
        if entry:
            st = b.call("setup", document=None, selection=[], locale=locale)["state"]
            r = b.call("try", state=st, candidates=[{"command": "element.insert", "args": {"entry": entry}}],
                       keep=True)["results"][0]
            if r["status"] == "done":
                doc = b.call("stateOf", state=r["state"])["document"]
                node = next((n for n in walk(doc["pages"][0]["tree"]) if n.get("type") == typ), None)
        cache[key] = node
    return cache[key]


def replay(b, st, plan):
    for action in plan:
        r = b.call("try", state=st, candidates=[action], keep=True)["results"][0]
        if r["status"] != "done" or r["problems"]:
            return None
        st = r["state"]
    return st


def main(per=2, rename=False, limit=None, seed_offset=0):
    domains = load_domains()
    c = collections.Counter()
    rows = []
    t0 = time.time()
    with Builder() as b:
        planner = Planner(b, domains, load_model() if CACHE.exists() else learn(b))
        scenarios = load_scenarios()[:limit]
        for si, s in enumerate(scenarios):
            fixture = load_fixture(s.setup["fixture"])
            if rename:
                r = rename_scenario(fixture, s.setup["selection"], s.diff, seed=si)
                if r is None:
                    continue
                fixture, sel, diff = r
                s = Scenario(s.feature, s.id, {**s.setup, "selection": sel}, diff, [])
            defaults = {}
            try:
                probe = start(b, s, fixture)
                first = b.call("goalDiff", state=probe)["items"]
                for it in first:
                    if it["kind"] == "added":
                        defaults[it["type"]] = default_node(b, domains, it["type"], s.setup["locale"])
                st = start(b, s, fixture)
            except Exception:  # noqa: BLE001
                continue
            gd = b.call("goalDiff", state=st)
            if len(gd["items"]) != 1:
                continue
            item = gd["items"][0]
            doc = b.call("stateOf", state=st)
            goal_doc = b.call("goalDocument")["document"]
            layer = (s.setup["breakpoint"], s.setup["state"])
            world = World.from_document(doc["document"], doc["selection"], layer)
            rng = random.Random(si + 100_000 * seed_offset)
            sentences = {realize(item, nodes_of(doc["document"]), nodes_of(goal_doc), layer, rng, defaults)
                         for _ in range(per)}
            for text in sorted(x for x in sentences if x):
                c["pedidos"] += 1
                u = understand(text, world)
                outcome = u.decision
                if u.decision == "executar":
                    res = planner.solve_constraints(st, u.best.constraints)
                    end = replay(b, st, res.plan) if res.solved else None
                    ok = end is not None and not b.call("stateOf", state=end)["mismatches"]
                    outcome = "certo" if ok else "ERRO SILENCIOSO"
                    if not res.solved:
                        outcome = "entendido, plano não achado"
                c[outcome] += 1
                c[f"{item['kind']}: {outcome}"] += 1
                part = "ajuste" if si < 300 else "validacao"
                c[f"{part}: pedidos"] += 1
                c[f"{part}: {outcome}"] += 1
                rows.append({"cenario": s.key, "indice": si, "pedido": text, "decisao": u.decision, "resultado": outcome,
                             "entendido": u.message, "custo": u.best.cost if u.best else None})
            if (si + 1) % 200 == 0:
                print(f"  {si + 1}/{len(scenarios)} {dict(c)} {time.time() - t0:.0f}s", flush=True)
    n = max(c["pedidos"], 1)
    print(f"\n{c['pedidos']} pedidos em {time.time() - t0:.0f}s ({'nomes inventados' if rename else 'nomes originais'})")
    print({k: v for k, v in sorted(c.items())})
    print(f"top-1 {c['certo'] / n:.1%}   erro silencioso {c['ERRO SILENCIOSO'] / n:.1%}   "
          f"perguntou/não entendeu {(c['perguntar'] + c['nao_entendi']) / n:.1%}")
    for part in ("ajuste", "validacao"):
        m = max(c[f"{part}: pedidos"], 1)
        print(f"  {part} (cenários {'1-300' if part == 'ajuste' else '301+'}): {c[f'{part}: pedidos']} pedidos, "
              f"top-1 {c[f'{part}: certo'] / m:.1%}, erro silencioso {c[f'{part}: ERRO SILENCIOSO'] / m:.1%}")
    name = ("m5_requests_renomeado" if rename else "m5_requests") + (f"_s{seed_offset}" if seed_offset else "") + ".json"
    (DATA / name).write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8")
    return c


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    lim = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--limit=")), None)
    seed = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--seed=")), 0)
    main(int(args[0]) if args else 2, "--rename" in sys.argv, lim, seed)
