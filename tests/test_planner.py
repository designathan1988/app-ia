"""M2: the planner reaches builder-6 scenario goals through the real editor, without seeing the scenarios' steps.

A fixed sample (every 8th scenario) keeps the suite fast; experiments/m2_plan.py runs all 1,023.
"""

from __future__ import annotations

import inspect

import pytest

from nucleo.builder.client import Builder
from nucleo.builder.effects import CACHE, learn, load_model
from nucleo.builder.knowledge import load_domains
from nucleo.builder.planner import Planner
from nucleo.builder.rename import rename_scenario
from nucleo.builder.scenarios import Scenario, load_commands, load_fixture, load_scenarios, reproducible, start
from nucleo.check.checker import check_proof
from nucleo.kb.syntax import parse_program
from nucleo.builder.planner import RELEVANCE_RULES


@pytest.fixture(scope="module")
def world():
    with Builder() as b:
        model = load_model() if CACHE.exists() else learn(b)
        yield b, Planner(b, load_domains(), model), model


def _verify(b, scenario, plan, fixture=None) -> bool:
    st = start(b, scenario, fixture)
    for action in plan:
        r = b.call("try", state=st, candidates=[action], keep=True)["results"][0]
        if r["status"] != "done" or r["problems"]:
            return False
        st = r["state"]
    final = b.call("stateOf", state=st)
    return not final["mismatches"] and not b.validate(final["document"])


def test_planner_never_receives_the_steps():
    params = inspect.signature(Planner.solve).parameters
    assert list(params) == ["self", "state", "start_mismatches", "start_distance"]


def test_sample_goals_are_reached_and_plans_verify(world):
    b, planner, _ = world
    commands = load_commands()
    sample = load_scenarios()[::8]
    reach = solved_reach = solved = 0
    for s in sample:
        ok_gold = reproducible(b, s, commands)
        try:
            st = start(b, s)
        except Exception:  # noqa: BLE001 - a goal the builder's own applyDiff rejects is not a planning problem
            continue
        g = b.call("goalDiff", state=st)
        r = planner.solve(st, g["mismatches"], g["distance"])
        if r.solved:
            solved += 1
            assert _verify(b, s, r.plan), f"{s.key}: plano não se confirma ao ser refeito"
        reach += ok_gold
        solved_reach += ok_gold and r.solved
    print(f"\namostra {len(sample)}: resolvidos {solved}; alcançáveis {solved_reach}/{reach}")
    assert solved_reach >= 0.8 * reach


def test_invented_names_do_not_change_the_outcome(world):
    b, planner, _ = world
    same = total = 0
    for i, s in enumerate(load_scenarios()[::16]):
        r = rename_scenario(load_fixture(s.setup["fixture"]), s.setup["selection"], s.diff, seed=i)
        if r is None:
            continue
        fx, sel, diff = r
        outcomes = []
        for scen, fixture in ((s, None), (Scenario(s.feature, s.id, {**s.setup, "selection": sel}, diff, []), fx)):
            st = start(b, scen, fixture)
            g = b.call("goalDiff", state=st)
            outcomes.append(planner.solve(st, g["mismatches"], g["distance"]).solved)
        total += 1
        same += outcomes[0] == outcomes[1]
    assert total > 30 and same >= total - 1


def test_relevance_is_deduced_with_checkable_proofs(world):
    _, planner, model = world
    items = [{"kind": "style", "id": "n", "breakpoint": "desktop", "state": "base", "property": "background-size",
              "value": "cover", "current": None},
             {"kind": "added", "id": None, "parent": "p", "index": 0, "type": "heading"}]
    by_need, proofs = planner.relevance(items)
    assert "style.set" in by_need["background-size"]  # through the learned parametric generalisation
    assert "element.insert" in by_need["node:added"]
    program = parse_program(model.facts() + RELEVANCE_RULES + '\nprecisa_estilo("background-size").\nprecisa("node:added").')
    from nucleo.check.checker import check_model
    from nucleo.logic.engine import evaluate
    from nucleo.logic.proof import model_certificate
    m = evaluate(program)
    S = check_model(program, model_certificate(m), m.indeterminate)
    for tree in proofs.values():
        check_proof(program, tree, S)
