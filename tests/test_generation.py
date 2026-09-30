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


def test_portuguese_description_becomes_a_verified_project():
    from nucleo.lang.describe_model import model_from_text

    model = model_from_text(
        "crie um projeto com a entidade Cliente com email (e-mail, obrigatório, até 120), idade (inteiro de 0 a 150)"
        " e plano (opções basico, pro); e a entidade Pedido com total (decimal, obrigatório, no mínimo 0),"
        " cliente (Cliente) e outros (lista de Cliente)")
    ped = model["entidades"][1]
    assert [r["alvo"] for r in ped["relacoes"]] == ["Cliente", "Cliente"] and ped["relacoes"][1]["muitos"]
    assert verify(model, fuzz=150)["verificado"]


@pytest.mark.parametrize("text", ["entidade X com cor (azulado brilhante)", "crie algo legal"])
def test_description_not_understood_generates_nothing(text):
    from nucleo.lang.describe_model import DescriptionError, model_from_text

    with pytest.raises(DescriptionError):
        model_from_text(text)
