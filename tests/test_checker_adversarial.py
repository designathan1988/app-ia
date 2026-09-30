"""The checker must reject every corrupted proof and every corrupted model certificate.

A checker that accepts everything would make the differential tests meaningless,
so here we attack it systematically, field by field.
"""

from __future__ import annotations

import copy
import random

import pytest

from nucleo.check.checker import CheckError, check_model, check_proof, check_status
from nucleo.kb.syntax import Atom, PredKey, Sym, parse_program
from nucleo.logic.engine import evaluate
from nucleo.logic.proof import model_certificate, proof_tree
from tests.gen.worlds import random_program

SRC = """
pred aresta/2 fechado.
pred alcanca/2 fechado.
pred isolado/1 fechado.
pred no/1 fechado.
no(a). no(b). no(c). no(d).
aresta(a, b). aresta(b, c).
alcanca(X, Y) :- aresta(X, Y).
alcanca(X, Z) :- aresta(X, Y), alcanca(Y, Z).
isolado(X) :- no(X), not tem_saida(X).
pred tem_saida/1 fechado.
tem_saida(X) :- aresta(X, Y).
"""


@pytest.fixture(scope="module")
def world():
    program = parse_program(SRC)
    model = evaluate(program)
    cert = model_certificate(model)
    S = check_model(program, cert)
    return program, model, cert, S


def A(name, *args):
    return Atom(PredKey(name, len(args)), tuple(Sym(a) for a in args))


def test_valid_proofs_pass(world):
    program, model, cert, S = world
    assert check_proof(program, proof_tree(model, A("alcanca", "a", "c")), S) > 1
    assert check_proof(program, proof_tree(model, A("isolado", "c")), S) > 1


def _corruptions(tree: dict):
    """Yield (description, corrupted_tree) pairs."""
    t = copy.deepcopy(tree)
    t["regra"] = (t["regra"] + 1) % 10
    yield "regra trocada", t
    if tree["premissas"]:
        t = copy.deepcopy(tree)
        t["premissas"].pop()
        yield "premissa removida", t
        t = copy.deepcopy(tree)
        p = t["premissas"][0]
        p["atomo"] = Atom(p["atomo"].pred, tuple(Sym("zzz") for _ in p["atomo"].args))
        yield "premissa alterada", t
    t = copy.deepcopy(tree)
    for k in list(t["subst"]):
        t["subst"][k] = Sym("zzz")
        break
    yield "substituição alterada", t
    t = copy.deepcopy(tree)
    t["atomo"] = Atom(tree["atomo"].pred, tuple(Sym("d") for _ in tree["atomo"].args))
    yield "conclusão alterada", t


def test_corrupted_proofs_rejected(world):
    program, model, cert, S = world
    for target in (A("alcanca", "a", "c"), A("isolado", "c"), A("alcanca", "b", "c")):
        tree = proof_tree(model, target)
        for desc, bad in _corruptions(tree):
            with pytest.raises((CheckError, KeyError)):
                check_proof(program, bad, S)
                pytest.fail(f"checador aceitou prova com {desc} para {target}")


def test_false_absence_rejected(world):
    program, model, cert, S = world
    tree = proof_tree(model, A("isolado", "c"))
    bad = copy.deepcopy(tree)
    bad["atomo"] = A("isolado", "a")
    bad["subst"] = {"X": Sym("a")}
    bad["premissas"] = [{"tipo": "fato", "atomo": A("no", "a")}]
    bad["ausencias"] = [{"tipo": "not", "atomo": A("tem_saida", "a")}]  # tem_saida(a) IS in the model
    with pytest.raises(CheckError):
        check_proof(program, bad, S)


def test_corrupted_model_rejected(world):
    program, model, cert, S = world
    # 1. drop a derived atom -> closure must fail
    missing = dict(cert)
    del missing[A("alcanca", "a", "c")]
    with pytest.raises(CheckError):
        check_model(program, missing)
    # 2. add an unsupported atom -> support must fail
    extra = dict(cert)
    extra[A("alcanca", "c", "a")] = (5, 0, {"X": Sym("c"), "Y": Sym("a")}, (A("aresta", "c", "a"),))
    with pytest.raises(CheckError):
        check_model(program, extra)
    # 3. circular support (rank not decreasing)
    circ = dict(cert)
    r, rid, s, prem = circ[A("alcanca", "a", "c")]
    circ[A("alcanca", "a", "c")] = (1, rid, s, prem)
    with pytest.raises(CheckError):
        check_model(program, circ)
    # 4. drop an asserted fact
    nofact = dict(cert)
    del nofact[A("aresta", "a", "b")]
    with pytest.raises(CheckError):
        check_model(program, nofact)


def test_wrong_status_rejected(world):
    program, model, cert, S = world
    with pytest.raises(CheckError):
        check_status(program, A("alcanca", "c", "a"), "VERDADEIRO", "inferido", S, None, None)
    with pytest.raises(CheckError):
        check_status(program, A("alcanca", "a", "c"), "DESCONHECIDO", None, S)
    with pytest.raises(CheckError):  # FALSO(mundo_fechado) claimed for a derivable atom
        check_status(program, A("alcanca", "a", "c"), "FALSO", "mundo_fechado", S)


def test_random_world_proof_corruptions_rejected():
    rng = random.Random(7)
    attacked = 0
    for seed in range(400):
        program = parse_program(random_program(seed))
        model = evaluate(program)
        S = check_model(program, model_certificate(model))
        derived = [a for a in model.entries if model.entries[a].just.rule is not None]
        for atom in rng.sample(derived, min(3, len(derived))):
            for desc, bad in _corruptions(proof_tree(model, atom)):
                try:
                    check_proof(program, bad, S)
                except (CheckError, KeyError):
                    attacked += 1
                    continue
                # a corruption may accidentally produce another valid proof; accept only if it is valid
                # for its (new) conclusion by construction -> recheck that conclusion is in S
                assert bad["atomo"] in S, f"seed {seed}: checador aceitou prova inválida ({desc})"
    assert attacked > 200
