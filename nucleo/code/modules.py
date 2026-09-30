"""Cross-file resolution as reasoning: from an import binding to the declaration it reaches, through export chains.

Facts, per project:

* from syntax: module-scope declarations, imports (``import { a as b }``,
  default, namespace) and exports (local, renamed, ``export { x } from``,
  ``export *``);
* from the compiler: module resolution only, i.e. which file a specifier
  such as ``'./x.ts'`` or ``'@core/y'`` names (provenance: the TypeScript
  resolver with the project's options).

Rules follow export chains of any length, including exporting something the
module itself imported, and ``export *`` (which never re-exports
``default``).
"""

from __future__ import annotations

from ..kb.syntax import PredKey, parse_program
from ..logic.engine import Model, evaluate
from .resolve import _q

RULES = """
pred decl_modulo/3 fechado. pred e_import/2 fechado. pred importa/4 fechado. pred exporta/3 fechado.
pred reexporta/4 fechado. pred reexporta_tudo/2 fechado. pred local/3 fechado. pred define/4 fechado.
pred vem_de/4 fechado. pred modulo_de/3 fechado. pred dados/1 fechado.
local(F, L, P) :- decl_modulo(F, L, X), P = #min{Q : decl_modulo(F, L, Q)}.
define(F, N, F, P) :- exporta(F, N, L), local(F, L, P), not e_import(F, P).
define(F, N, G, Q) :- exporta(F, N, L), local(F, L, P), e_import(F, P), vem_de(F, P, G, Q).
define(F, N, G, Q) :- reexporta(F, N, T, M), define(T, M, G, Q).
define(F, N, G, Q) :- reexporta_tudo(F, T), define(T, N, G, Q), N != "default".
vem_de(F, P, G, Q) :- importa(F, P, T, N), define(T, N, G, Q).
modulo_de(F, P, T) :- importa(F, P, T, "*").
modulo_de(F, P, T) :- importa(F, P, T, "default"), dados(T).
"""


def project_program(files: list[dict], rules: bool = True) -> str:
    lines = [RULES] if rules else []
    for f in files:
        F = _q(f["file"])
        for scope, name, pos, _space, _kind in f["decls"]:
            if scope == 0:
                lines.append(f"decl_modulo({F}, {_q(name)}, {pos}).")
        for pos, _local, spec, imported in f["imports"]:
            lines.append(f"e_import({F}, {pos}).")
            target = f["modules"].get(spec)
            if target:
                lines.append(f"importa({F}, {pos}, {_q(target)}, {_q(imported)}).")
                if target.endswith(".json"):  # a data module: its default import is the module's value itself
                    lines.append(f"dados({_q(target)}).")
        for name, local, spec in f["exports"]:
            target = f["modules"].get(spec) if spec else None
            if spec is None and local is not None:
                lines.append(f"exporta({F}, {_q(name)}, {_q(local)}).")
            elif target and name == "*" and local is None:
                lines.append(f"reexporta_tudo({F}, {_q(target)}).")
            elif target and local not in (None, "*"):
                lines.append(f"reexporta({F}, {_q(name)}, {_q(target)}, {_q(local)}).")
    return "\n".join(lines)


def resolve_imports(files: list[dict]) -> tuple[dict, Model]:
    """(file, import position) -> set of "file:pos" | "file:modulo" the import reaches."""
    model = evaluate(parse_program(project_program(files)))
    out: dict = {}
    for a in model.atoms(PredKey("vem_de", 4)):
        out.setdefault((a.args[0].value, a.args[1]), set()).add(f"{a.args[2].value}:{a.args[3]}")
    for a in model.atoms(PredKey("modulo_de", 3)):
        out.setdefault((a.args[0].value, a.args[1]), set()).add(f"{a.args[2].value}:modulo")
    return out, model
