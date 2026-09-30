"""API change between two versions of a package, deduced by rules from the two surfaces.

A surface is the set of exported names, each in a space (value, type or both)
with its signature as the compiler prints it. The rules say, for every name
of the old version, whether code that used it in its space still finds it in
the new version (``indisponivel``), and which names are new (``novo``) or kept
with another signature (``assinatura_mudou``).

The claims are judged by the real compiler: a probe file that imports each
name in its space is compiled against the other version.
"""

from __future__ import annotations

from ..kb.syntax import PredKey, parse_program
from ..logic.engine import evaluate
from ..code.resolve import _q

RULES = """
pred api/4 fechado. pred oferece/3 fechado. pred da_espaco/2 fechado. pred testa/2 fechado.
pred indisponivel/2 fechado. pred novo/2 fechado. pred assinatura_mudou/1 fechado.
da_espaco(valor, valor). da_espaco(tipo, tipo). da_espaco(ambos, valor). da_espaco(ambos, tipo).
testa(valor, valor). testa(tipo, tipo). testa(ambos, valor).
oferece(V, N, X) :- api(V, N, E, S), da_espaco(E, X).
indisponivel(N, X) :- api(antiga, N, E, S), testa(E, X), not oferece(nova, N, X).
novo(N, X) :- api(nova, N, E, S), testa(E, X), not oferece(antiga, N, X).
assinatura_mudou(N) :- api(antiga, N, E, S1), api(nova, N, E, S2), S1 != S2.
"""


def diff(old: list, new: list) -> dict:
    lines = [RULES]
    for version, exports in (("antiga", old), ("nova", new)):
        for name, space, sig in exports:
            lines.append(f"api({version}, {_q(name)}, {space}, {_q(sig)}).")
    m = evaluate(parse_program("\n".join(lines)))
    get = lambda p, n: {tuple(a.args) for a in m.atoms(PredKey(p, n))}  # noqa: E731
    return {
        "indisponivel": {(a[0].value, a[1].name) for a in get("indisponivel", 2)},
        "novo": {(a[0].value, a[1].name) for a in get("novo", 2)},
        "assinatura_mudou": {a[0].value for a in get("assinatura_mudou", 1)},
    }
