"""Proof trees and the model certificate, as plain data consumed by the independent checker.

Two objects are exported:

* **Proof tree** of an atom: the chain of best justifications from asserted facts
  to the conclusion. It is acyclic because every premise is strictly cheaper than
  what it supports.
* **Model certificate**: every atom of the model with its rank (proof size) and
  justification. The checker uses it to verify *absences* (``not`` /
  ``nao_consta`` / closed world / unknown). It checks that the certified set is
  exactly the stable model: every atom well-supported by lower-ranked atoms, and
  the set closed under every rule. For stratified programs that is the unique
  perfect model, so a non-member is genuinely not derivable.
"""

from __future__ import annotations

from ..kb.syntax import Atom
from .engine import Model


def proof_tree(model: Model, atom: Atom) -> dict:
    entry = model.entries.get(atom)
    if entry is None:
        raise KeyError(f"{atom} não pertence ao modelo")
    j = entry.just
    if j.rule is None:
        return {"tipo": "fato", "atomo": atom}
    return {
        "tipo": "regra",
        "atomo": atom,
        "regra": j.rule,
        "subst": dict(j.subst),
        "premissas": [proof_tree(model, p) for p in j.premises],
        "ausencias": [{"tipo": kind, "atomo": a} for kind, a in j.absences],
        "comparacoes": [list(c) for c in j.comparisons],
    }


def model_certificate(model: Model) -> dict[Atom, tuple[int, int | None, dict, tuple]]:
    """atom -> (rank, rule id or None, substitution, premises)."""
    cert = {}
    for atom, entry in model.entries.items():
        j = entry.just
        cert[atom] = (entry.cost[1], j.rule, dict(j.subst), j.premises)
    return cert


def render_proof(tree: dict, indent: int = 0) -> str:
    """Human-readable rendering of a proof tree (Portuguese labels)."""
    pad = "  " * indent
    if tree["tipo"] == "fato":
        return f"{pad}{tree['atomo']}  [fato afirmado]"
    lines = [f"{pad}{tree['atomo']}  [regra {tree['regra']}]"]
    for p in tree["premissas"]:
        lines.append(render_proof(p, indent + 1))
    for a in tree["ausencias"]:
        label = "ausente (mundo fechado)" if a["tipo"] == "not" else "não consta (suposição)"
        lines.append(f"{pad}  {a['atomo']}  [{label}]")
    for op, left, right in tree["comparacoes"]:
        lines.append(f"{pad}  {left} {op} {right}  [comparação]")
    return "\n".join(lines)
