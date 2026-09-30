"""A project's code as knowledge: questions about it are answered by rules, with proofs.

Facts come from the per-file resolution (``resolve.py``), from the cross-file
module facts (``modules.py``) and from the owner of each use (the top-level
declaration it is written in). On top of them:

* ``alcanca(F, U, G, Q)``: the use U in file F refers to the declaration Q in
  file G, locally or through any chain of imports and re-exports;
* ``depende(F, O, G, Q)``: the top-level declaration O of F uses Q of G;
* ``impacto(F, O)``, for a chosen target: everything that depends on the
  target, transitively. The target is seeded, so only what is asked is
  derived;
* ``nao_usado(G, Q)``: an exported declaration that nothing outside itself
  uses. This is closed-world reasoning, valid because the project's files
  are completely known.
"""

from __future__ import annotations

from ..kb.syntax import Atom, PredKey, Text, parse_program
from ..logic.engine import Model, evaluate
from ..logic.incremental import update
from ..logic.proof import proof_tree
from .modules import RULES as MODULE_RULES
from .modules import project_program
from .resolve import _q, resolve_file

RULES = """
pred ref_local/3 fechado. pred dono/3 fechado. pred alcanca/4 fechado. pred depende/4 fechado.
pred usado_fora/2 fechado. pred exportado/2 fechado. pred nao_usado/2 fechado.
alcanca(F, U, F, P) :- ref_local(F, U, P), not e_import(F, P).
alcanca(F, U, G, Q) :- ref_local(F, U, P), vem_de(F, P, G, Q).
depende(F, O, G, Q) :- dono(F, U, O), alcanca(F, U, G, Q), F != G.
depende(F, O, G, Q) :- dono(F, U, O), alcanca(F, U, G, Q), O != Q.
usado_fora(G, Q) :- depende(F, O, G, Q).
exportado(G, Q) :- define(G, N, G, Q).
nao_usado(G, Q) :- exportado(G, Q), not usado_fora(G, Q).
"""

IMPACT_RULES = """
pred alvo/2 fechado. pred impacto/2 fechado.
impacto(F, O) :- alvo(G, Q), depende(F, O, G, Q), O >= 0.
impacto(F, O) :- impacto(G, Q), depende(F, O, G, Q), O >= 0.
"""


class CodeBase:
    def __init__(self, files: list[dict]) -> None:
        self.files = {f["file"]: f for f in files}
        self.local: dict[str, dict] = {}
        for f in files:
            self.local[f["file"]], _ = resolve_file(f)
        self._model: Model | None = None
        self._text = self._program_text()

    def _file_facts(self, name: str) -> str:
        f = self.files[name]
        F = _q(name)
        res = self.local[name]
        lines = [project_program([f], rules=False)]
        for use in f["uses"]:
            pos = use[0]
            d = res.get(pos)
            if isinstance(d, int):
                lines.append(f"ref_local({F}, {pos}, {d}).")
            if len(use) > 4:
                lines.append(f"dono({F}, {pos}, {use[4]}).")
        return "\n".join(lines)

    def _program_text(self) -> str:
        return "\n".join([MODULE_RULES, RULES] + [self._file_facts(n) for n in self.files])

    def update_file(self, facts: dict | None, name: str | None = None) -> None:
        """Replace (or add, or with facts=None remove) one file. Only that file is resolved again; the project model
        is maintained incrementally (``logic.incremental``), not rebuilt."""
        name = name or facts["file"]
        old = parse_program(self._file_facts(name)).facts if name in self.files else []
        if facts is None:
            self.files.pop(name, None)
            self.local.pop(name, None)
            new = []
        else:
            self.files[name] = facts
            self.local[name], _ = resolve_file(facts)
            new = parse_program(self._file_facts(name)).facts
        self._text = self._program_text()
        if self._model is not None:
            gone, came = set(old) - set(new), set(new) - set(old)
            self._model = update(self._model, add=list(came), remove=list(gone))

    @property
    def model(self) -> Model:
        if self._model is None:
            self._model = evaluate(parse_program(self._text))
        return self._model

    def references(self, file: str, pos: int) -> set[tuple[str, int]]:
        out = set()
        for a in self.model.atoms(PredKey("alcanca", 4)):
            if a.args[2].value == file and a.args[3] == pos:
                out.add((a.args[0].value, a.args[1]))
        return out

    def why_reference(self, use_file: str, use_pos: int, file: str, pos: int) -> dict:
        """The proof that a use refers to a declaration (local scoping plus the import chain)."""
        atom = Atom(PredKey("alcanca", 4), (Text(use_file), use_pos, Text(file), pos))
        return proof_tree(self.model, atom)

    def unused_exports(self) -> set[tuple[str, int]]:
        return {(a.args[0].value, a.args[1]) for a in self.model.atoms(PredKey("nao_usado", 2))}

    def impact(self, file: str, pos: int) -> set[tuple[str, int]]:
        """Top-level declarations that depend on (file, pos), transitively."""
        text = self._text + IMPACT_RULES + f"\nalvo({_q(file)}, {pos})."
        m = evaluate(parse_program(text))
        return {(a.args[0].value, a.args[1]) for a in m.atoms(PredKey("impacto", 2))}
