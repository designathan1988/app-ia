"""Epistemic status of a ground atom, plus its explanation.

For a positive ground atom ``p(t)`` with strong-negation counterpart ``-p(t)``:

| in model: p(t) | -p(t) | status | qualifier |
|---|---|---|---|
| yes | no | VERDADEIRO | afirmado (asserted fact), inferido (clean proof), presumido (proof needs nao_consta) |
| no | yes | FALSO | same qualifiers, taken from the proof of -p(t) |
| no | no, p closed-world | FALSO | mundo_fechado |
| yes | yes | CONTRADITORIO | both proofs are returned |
| no | no, p open-world | DESCONHECIDO | — |

INDETERMINADO: defeasible rules for and against, and no winner by priority or specificity.
HIPOTETICO (a conclusion of a learned rule) arrives with the learning layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..kb.syntax import Atom
from .conflict import minimal_conflict
from .engine import Model
from .proof import proof_tree

VERDADEIRO = "VERDADEIRO"
FALSO = "FALSO"
CONTRADITORIO = "CONTRADITORIO"
DESCONHECIDO = "DESCONHECIDO"
INDETERMINADO = "INDETERMINADO"

AFIRMADO = "afirmado"
INFERIDO = "inferido"
PRESUMIDO = "presumido"
MUNDO_FECHADO = "mundo_fechado"


@dataclass(frozen=True)
class Status:
    value: str
    qualifier: str | None = None

    def __str__(self) -> str:
        return self.value if self.qualifier is None else f"{self.value}({self.qualifier})"


def _qualifier(model: Model, atom: Atom) -> str:
    if atom in model.facts:
        return AFIRMADO
    return PRESUMIDO if model.entries[atom].cost[0] > 0 else INFERIDO


def status_of(model: Model, atom: Atom) -> Status:
    if atom.pred.neg:
        raise ValueError("consulte o átomo positivo; o status já considera a negação forte")
    if not atom.is_ground():
        raise ValueError("status é definido para átomos sem variáveis")
    neg = Atom(atom.pred.negated(), atom.args)
    pos_in, neg_in = atom in model, neg in model
    if pos_in and neg_in:
        return Status(CONTRADITORIO)
    if pos_in:
        return Status(VERDADEIRO, _qualifier(model, atom))
    if neg_in:
        return Status(FALSO, _qualifier(model, neg))
    if atom in model.indeterminate:
        return Status(INDETERMINADO)
    if model.program.is_closed(atom.pred):
        return Status(FALSO, MUNDO_FECHADO)
    return Status(DESCONHECIDO)


def explain(model: Model, atom: Atom) -> dict:
    """Status plus the proof(s) that support it, as plain data."""
    st = status_of(model, atom)
    neg = Atom(atom.pred.negated(), atom.args)
    out: dict = {"atomo": str(atom), "status": st.value, "qualificador": st.qualifier}
    if st.value in (VERDADEIRO, CONTRADITORIO):
        out["prova"] = proof_tree(model, atom)
    if st.value == FALSO and st.qualifier != MUNDO_FECHADO or st.value == CONTRADITORIO:
        out["prova_negacao"] = proof_tree(model, neg)
    if st.value == CONTRADITORIO:
        c = minimal_conflict(model, atom)
        out["conflito_minimo"] = {"fatos": [str(f) for f in c["fatos"]], "regras": c["regras"],
                                  "minimalidade": c["minimalidade"]}
    if st.value == FALSO and st.qualifier == MUNDO_FECHADO:
        out["motivo"] = f"{atom.pred.name}/{atom.pred.arity} é de mundo fechado e {atom} não é derivável"
    if st.value == INDETERMINADO:
        out["motivo"] = f"regras derrotáveis a favor e contra {atom}, sem vencedor por prioridade ou especificidade"
    if st.value == DESCONHECIDO:
        out["motivo"] = f"nem {atom} nem {neg} são deriváveis, e {atom.pred.name}/{atom.pred.arity} é de mundo aberto"
    return out
