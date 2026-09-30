"""Second oracle: translate the program to ASP and let clingo compute the (unique) answer set.

Strong negation is translated to a *separate predicate* (``neg__p``), not to
clingo's own ``-p``. Clingo discards models that contain both ``p`` and ``-p``,
while our semantics is paraconsistent: both sides are kept and the atom is
reported CONTRADITORIO. Both ``not`` and ``nao_consta`` become ASP ``not``,
since they differ only in how the conclusion is qualified, not in the model.

This module imports only the syntax module.
"""

from __future__ import annotations

import clingo

from nucleo.kb.syntax import Agg, Atom, Cmp, Naf, NaoConsta, Pos, PredKey, Program, Sym, Text, Var

_P = "p__"
_N = "neg__"


def _term(t) -> str:
    if isinstance(t, Var):
        return "V" + t.name
    if isinstance(t, int):
        return str(t)
    if isinstance(t, Sym):
        return "c__" + t.name
    if isinstance(t, Text):
        return '"' + t.value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    raise TypeError(t)


def _pred_name(pred: PredKey) -> str:
    return (_N if pred.neg else _P) + pred.name + f"__{pred.arity}"


def _atom(a: Atom) -> str:
    name = _pred_name(a.pred)
    if not a.args:
        return name
    return f"{name}({','.join(_term(t) for t in a.args)})"


class Unsupported(Exception):
    """The program uses a construct with no direct ASP translation (defeasible rules)."""


def _lit(lit) -> list[str]:
    if isinstance(lit, Pos):
        return [_atom(lit.atom)]
    if isinstance(lit, (Naf, NaoConsta)):
        return ["not " + _atom(lit.atom)]
    if isinstance(lit, Cmp):
        return [f"{_term(lit.left)} {lit.op} {_term(lit.right)}"]
    if isinstance(lit, Agg):
        inner = ", ".join(x for l in lit.body for x in _lit(l))
        terms = ", ".join(_term(t) for t in lit.terms)
        out = [f"{_term(lit.result)} = #{lit.func}{{{terms} : {inner}}}"]
        # our semantics: #min/#max of the empty set is undefined (the literal fails);
        # clingo yields #sup/#inf, so those values are excluded explicitly
        if lit.func == "min":
            out.append(f"{_term(lit.result)} < #sup")
        if lit.func == "max":
            out.append(f"{_term(lit.result)} > #inf")
        return out
    raise TypeError(lit)


def to_asp(program: Program) -> str:
    if any(r.defeasible for r in program.rules):
        raise Unsupported("regras derrotáveis")
    lines = [f"{_atom(f)}." for f in program.facts]
    for r in program.rules:
        body = [x for lit in r.body for x in _lit(lit)]
        lines.append(f"{_atom(r.head)} :- {', '.join(body)}.")
    return "\n".join(lines)


def _back(sym: clingo.Symbol):
    if sym.type == clingo.SymbolType.Number:
        return sym.number
    if sym.type == clingo.SymbolType.String:
        return Text(sym.string)
    if sym.type == clingo.SymbolType.Function and not sym.arguments and sym.name.startswith("c__"):
        return Sym(sym.name[3:])
    raise ValueError(f"símbolo inesperado {sym}")


def answer_set(program: Program) -> set:
    ctl = clingo.Control(["0", "--warn=none"])  # "0": enumerate all models
    ctl.add("base", [], to_asp(program))
    ctl.ground([("base", [])])
    models: list[set] = []

    def on_model(m: clingo.Model) -> None:
        out = set()
        for sym in m.symbols(atoms=True):
            name = sym.name
            neg = name.startswith(_N)
            rest = name[len(_N):] if neg else name[len(_P):]
            pname, _, arity = rest.rpartition("__")
            out.add(Atom(PredKey(pname, int(arity), neg), tuple(_back(a) for a in sym.arguments)))
        models.append(out)

    ctl.solve(on_model=on_model)
    if len(models) != 1:
        raise AssertionError(f"clingo encontrou {len(models)} modelos; programa estratificado deve ter 1")
    return models[0]
