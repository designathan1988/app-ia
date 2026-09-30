"""M6 (multi-file): model -> TypeScript + Python projects, verified by the compiler, their tests and a differential
test against the model's meaning. A few random models here; experiments/m6_multifile.py runs 30."""

from __future__ import annotations

import pytest

from experiments.m6_multifile import random_model
from nucleo.gen.build import verify
from nucleo.gen.model import ModelError, check_model


@pytest.mark.parametrize("seed", [0, 3, 7])
def test_random_models_are_generated_and_verified(seed):
    r = verify(random_model(seed), fuzz=200, seed=seed)
    assert r["tsc"] == [] and r["testes_ts"] == "OK" and r["py_ok"], r
    assert r["diferencial"]["divergencias"] == 0, r["diferencial"]["exemplos"]


@pytest.mark.parametrize("model", [
    {"entidades": []},
    {"entidades": [{"nome": "class", "campos": []}]},
    {"entidades": [{"nome": "A", "campos": [{"nome": "x", "tipo": "data"}]}]},
    {"entidades": [{"nome": "A", "campos": [], "relacoes": [{"nome": "b", "alvo": "B"}]}]},
    {"entidades": [{"nome": "A", "campos": [{"nome": "x", "tipo": "inteiro", "min": 5, "max": 1}]}]},
])
def test_unsound_models_are_refused(model):
    with pytest.raises(ModelError):
        check_model(model)
