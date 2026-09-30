"""Name resolution as reasoning: from syntactic facts to "this use means that declaration", by rules.

The rules are the language's lexical scoping, stated once and run by the
knowledge core:

* a use of name N in space E (value or type) looks for N in its own scope,
  then in each enclosing scope, stopping at the first scope that declares N in
  a compatible space (``not declara_ns``: negation over closed-world facts,
  since a file's declarations are completely known);
* several declarations of N in that scope (overloads, merged declarations)
  resolve to the first one (``#min`` over positions);
* a name no enclosing scope declares is external: a global, a library or an
  ambient declaration.

The same rules serve any language whose extractor produces the same four
kinds of fact. Only the extractor knows TypeScript (``bridge/code/ts_facts.mjs``)
or Python (``python_facts.py``).
"""

from __future__ import annotations

from ..kb.syntax import PredKey, parse_program
from ..logic.engine import Model, evaluate

RULES = """
pred escopo/2 fechado. pred declara/4 fechado. pred uso/4 fechado. pred compat/2 fechado.
pred chave/3 fechado. pred declara_ns/3 fechado. pred busca/4 fechado. pred menor/4 fechado.
pred resolve/2 fechado. pred tem_achado/3 fechado. pred externo/1 fechado.
compat(valor, valor). compat(valor, ambos). compat(tipo, tipo). compat(tipo, ambos).
compat(qualquer, valor). compat(qualquer, tipo). compat(qualquer, ambos).
chave(S, N, E) :- uso(U, N, S, E).
declara_ns(S, N, E) :- declara(S, N, P, E2), compat(E, E2).
busca(S0, N, E, S0) :- chave(S0, N, E).
busca(S0, N, E, P) :- busca(S0, N, E, S), not declara_ns(S, N, E), escopo(S, P).
menor(S0, N, E, D) :- busca(S0, N, E, S), declara_ns(S, N, E), D = #min{P : declara(S, N, P, E2), compat(E, E2)}.
resolve(U, D) :- uso(U, N, S, E), menor(S, N, E, D).
tem_achado(S, N, E) :- menor(S, N, E, D).
externo(U) :- uso(U, N, S, E), not tem_achado(S, N, E).
"""


def _q(name: str) -> str:
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def file_program(facts: dict) -> str:
    lines = [RULES]
    for sid, parent, _kind in facts["scopes"]:
        if parent >= 0:
            lines.append(f"escopo({sid}, {parent}).")
    for scope, name, pos, space, _kind in facts["decls"]:
        lines.append(f"declara({scope}, {_q(name)}, {pos}, {space}).")
    for pos, name, scope, space, *_ in facts["uses"]:
        lines.append(f"uso({pos}, {_q(name)}, {scope}, {space}).")
    return "\n".join(lines)


def resolve_file(facts: dict) -> tuple[dict, Model]:
    """use position -> declaration position | "externo", with the model (and its proofs) behind the answer."""
    model = evaluate(parse_program(file_program(facts)))
    out: dict = {}
    for atom in model.atoms(PredKey("resolve", 2)):
        out.setdefault(atom.args[0], atom.args[1])
    for atom in model.atoms(PredKey("externo", 1)):
        out.setdefault(atom.args[0], "externo")
    return out, model
