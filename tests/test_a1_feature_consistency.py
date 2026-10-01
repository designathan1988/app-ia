"""Training and inference must score the same IR with the same feature vector.

The controlled catalog and abstract tokens avoid training a new phrase or loading
external lexical resources. Generation, ranking and forced featurization are real.
"""

import pytest

from nucleo.lang import acoes_ranker as ar
from nucleo.lang.mundo import Discourse, Page


@pytest.fixture
def inference_case(monkeypatch):
    tokens = [ar.Tok(1, "q", ("q",), "VERB"),
              ar.Tok(2, "v", ("v",), "ADJ", 1, "obj")]
    schemas = {
        "unit.run": ar.E.ActionSchema("unit.run", (), "always", True, (),
                                       {"en": "q"}, "unit"),
        "style.set": ar.E.ActionSchema(
            "style.set", (ar.E.Arg("target", "node"), ar.E.Arg("property", "property"),
                          ar.E.Arg("value", "string")),
            "targetOrSelection", True, (), {"en": "q"}, "style"),
    }
    properties = {"surface-tone": {"label": {"en": "tone"},
                                    "appliesTo": "always", "valueType": "string"}}
    evidence = {
        "q": (("op", "unit.run", 1.0, "catalog"),
              ("op", "style.set", 1.0, "catalog")),
        "v": (("value", ("surface-tone", "v"), 1.0, "catalog"),),
    }
    monkeypatch.setattr(ar, "analyse", lambda *args: tokens)
    monkeypatch.setattr(ar, "negation_words", lambda lang: frozenset())
    monkeypatch.setattr(ar.EV, "evidence", lambda word, lang: evidence.get(word, ()))
    monkeypatch.setattr(ar.E, "schemas", lambda: schemas)
    monkeypatch.setattr(ar.E, "properties", lambda: properties)
    monkeypatch.setattr(ar, "_catalog_words", lambda: frozenset({"q", "v"}))
    monkeypatch.setattr(ar, "_label_words", lambda: {
        "op": {sid: frozenset({"q"}) for sid in schemas},
        "prop": {"surface-tone": frozenset({"tone"})},
        "type": {"unit": frozenset({"unit"})},
    })
    monkeypatch.setattr(ar, "_keywords", lambda: {"surface-tone": ["v"]})
    monkeypatch.setattr(ar, "_numeric_props", lambda: frozenset())
    page = Page({"pages": [{"tree": {
        "id": "n", "type": "unit", "name": "n", "text": None, "children": [],
    }}]})
    ranker = ar.Ranker()
    context = ranker.context("q v", "en", page, Discourse())
    return ranker, context


def nonzero(features):
    return {key: value for key, value in features.items() if value != 0}


@pytest.mark.parametrize("operation", ["unit.run", "style.set"])
def test_natural_and_forced_features_match_for_the_same_ir(inference_case, operation):
    ranker, context = inference_case
    candidates = ranker.rank(context, ranker.generate(context))
    matching = [candidate for candidate in candidates
                if candidate.action is not None and not candidate.action.negated
                and candidate.action.op == operation and candidate.kind == "act"]
    assert len(matching) == 1
    candidate = matching[0]
    assert candidate.seg is None
    # Losing the generic action features on the natural path lets TRAIN satisfy
    # its margin with weights that inference can never use.
    forced = ar.featurize(context, candidate.action)
    assert nonzero(candidate.full) == nonzero(forced)
