"""Proposed tests for per-generation property/value retrieval reuse.

Run only after applying a1_pair_cache.patch. All language and schemas are
abstract fixtures; no corpus, resource loading or builder process is needed.
"""

import pytest

from nucleo.lang import acoes_ranker as ar
from nucleo.lang.mundo import Discourse, Page


@pytest.fixture
def pair_case(monkeypatch):
    tokens = [ar.Tok(1, "q", ("q",), "VERB"),
              ar.Tok(2, "v", ("v",), "ADJ"),
              ar.Tok(3, "w", ("w",), "ADJ")]
    schemas = {
        sid: ar.E.ActionSchema(sid, (ar.E.Arg("target", "node"), ar.E.Arg("property", "property")),
                               "targetOrSelection", True, (), {"en": "q"}, "unit")
        for sid in ("unit.alpha", "unit.beta")
    }
    properties = {"surface-tone": {"label": {"en": "tone"},
                                    "appliesTo": "always", "valueType": "string"}}
    evidence = {value: (("value", ("surface-tone", value), 1.0, "catalog"),)
                for value in ("v", "w")}
    monkeypatch.setattr(ar, "analyse", lambda *args: tokens)
    monkeypatch.setattr(ar, "negation_words", lambda *args: frozenset())
    monkeypatch.setattr(ar.EV, "evidence", lambda word, lang: evidence.get(word, ()))
    monkeypatch.setattr(ar.E, "schemas", lambda: schemas)
    monkeypatch.setattr(ar.E, "properties", lambda: properties)
    monkeypatch.setattr(ar, "_catalog_words", lambda: frozenset({"q", "v", "w"}))
    monkeypatch.setattr(ar, "_label_words", lambda: {
        "op": {sid: frozenset({"q"}) for sid in schemas},
        "prop": {"surface-tone": frozenset({"tone"})},
        "type": {},
    })
    monkeypatch.setattr(ar, "_keywords", lambda: {"surface-tone": ["v", "w"]})
    monkeypatch.setattr(ar, "_numeric_props", lambda: frozenset())
    page = Page({"pages": [{"tree": {"id": "n", "type": "unit", "name": "n", "children": []}}]})
    ranker = ar.Ranker()
    context = ranker.context("q v w", "en", page, Discourse())
    ops = [(sid, {("op-probe", sid): 1.0}) for sid in schemas]
    monkeypatch.setattr(ranker, "_ops", lambda cx: ops)
    monkeypatch.setattr(ranker, "_targets", lambda cx: [("n", {("target-probe", "n"): 1.0})])
    calls = []
    original_pairs = ranker._pairs

    def retrieve(cx, target):
        calls.append(target)
        return original_pairs(cx, target)

    monkeypatch.setattr(ranker, "_pairs", retrieve)
    return ranker, context, ops, calls


def snapshot(candidates):
    # Include insertion order of the feature vector as well as every value.
    return [(c.ir(), c.kind, c.seg, list(c.feats.items()), c.gen.hex()) for c in candidates]


def test_pairs_reused_across_operations_preserve_ir_vectors_and_order(pair_case, monkeypatch):
    ranker, context, ops, calls = pair_case
    together = ranker.generate(context)
    assert calls == ["n"]
    positive = [c for c in together if c.action is not None and not c.action.negated]
    assert {c.ir() for c in positive} == {
        "unit.alpha @n property=surface-tone value=v",
        "unit.alpha @n property=surface-tone value=w",
        "unit.beta @n property=surface-tone value=v",
        "unit.beta @n property=surface-tone value=w",
    }

    # Each isolated operation has its own fresh retrieval. With four positive
    # candidates total, the normal five-candidate negation cap loses none, so
    # their union is an independent reference for the combined call.
    reference = {}
    for op in ops:
        monkeypatch.setattr(ranker, "_ops", lambda cx, op=op: [op])
        for candidate in ranker.generate(context):
            reference.setdefault(candidate.ir(), candidate)
    ordered = sorted(reference.values(), key=lambda c: (-c.gen, c.canonical()))
    assert calls == ["n", "n", "n"]
    assert snapshot(together) == snapshot(ordered)


def test_pair_cache_does_not_survive_weight_changes_between_calls(pair_case):
    ranker, context, _, calls = pair_case
    before = ranker.generate(context)
    ranker.w[("val", "q", "w")] = 100.0
    after = ranker.generate(context)
    assert calls == ["n", "n"]
    before_alpha = [c.action.arg("value").data for c in before
                    if c.action is not None and not c.action.negated and c.action.op == "unit.alpha"]
    after_alpha = [c.action.arg("value").data for c in after
                   if c.action is not None and not c.action.negated and c.action.op == "unit.alpha"]
    assert before_alpha == ["v", "w"]
    assert after_alpha == ["w", "v"]
