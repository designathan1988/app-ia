"""Runs every example of docs/semantica.md (hand-computed expectations) against engine, oracles and checker."""

from __future__ import annotations

import pathlib
import re

import pytest

from nucleo.check.checker import check_model, check_status
from nucleo.kb.syntax import Atom, parse_atom, parse_program
from nucleo.logic.engine import evaluate
from nucleo.logic.proof import model_certificate, proof_tree
from nucleo.logic.status import status_of
from tests.oracle import clingo_bridge, naive

DOC = pathlib.Path(__file__).resolve().parents[1] / "docs" / "semantica.md"
BLOCKS = re.findall(r"```nl\n(.*?)```", DOC.read_text(encoding="utf-8"), flags=re.S)


def _cases():
    for block in BLOCKS:
        title = block.strip().splitlines()[0].lstrip("% ").strip()
        expectations = []
        for line in block.splitlines():
            m = re.match(r"%\?\s*(.+?)\s*=>\s*(\w+)(?:\((\w+)\))?\s*$", line)
            if m:
                expectations.append((m.group(1), m.group(2), m.group(3)))
        yield pytest.param(block, expectations, id=title[:40])


def test_document_has_enough_examples():
    assert len(BLOCKS) >= 35
    assert sum(len(e) for _, e in [(b, [l for l in b.splitlines() if l.startswith("%?")]) for b in BLOCKS]) >= 60


@pytest.mark.parametrize("src, expectations", list(_cases()))
def test_example(src, expectations):
    program = parse_program(src)
    model = evaluate(program)
    ref, ref_indet = naive.perfect_model(program, with_indeterminate=True)
    assert set(model.entries) == ref and model.indeterminate == ref_indet
    try:
        assert set(model.entries) == clingo_bridge.answer_set(program)
    except clingo_bridge.Unsupported:
        pass  # defeasible rules: only the naive oracle and the checker apply
    S = check_model(program, model_certificate(model), model.indeterminate)
    assert expectations, "exemplo sem expectativa"
    for atom_src, value, qual in expectations:
        atom = parse_atom(atom_src)
        st = status_of(model, atom)
        assert (st.value, st.qualifier) == (value, qual), f"{atom_src}: obtido {st}, esperado {value}({qual})"
        neg = Atom(atom.pred.negated(), atom.args)
        check_status(program, atom, st.value, st.qualifier, S,
                     proof_tree(model, atom) if atom in model else None,
                     proof_tree(model, neg) if neg in model else None, model.indeterminate)
