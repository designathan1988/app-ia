"""Questions about a code base, in Portuguese, answered by the code knowledge (M3) with its rules.

    "onde está definido createStore?"          -> the declaration(s): file:line
    "quem usa createStore?"                    -> every reference, through imports and re-exports, by file
    "o que é afetado se eu mudar createStore?" -> the top-level declarations that depend on it, transitively
    "quais exportações não são usadas?"        -> exported declarations nothing outside them uses

The question is understood by the same means as requests: the verb's lemma (MorphoBr) selects a question frame
(data below), and the code name is grounded in the project's real declarations (exact name). A name that is not
declared in the project, or a verb outside the frames, is answered with what is missing, never with a guess.
"""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass

from .morph import lemmas as morph_lemmas

FRAMES = {
    "definicao": {"definir", "declarar", "ficar", "estar", "criar", "implementar"},
    "usos": {"usar", "utilizar", "chamar", "referenciar", "importar", "invocar"},
    "impacto": {"afetar", "depender", "quebrar", "impactar"},
}
UNUSED_WORDS = {"exportação", "exportações", "export", "exports"}


@dataclass
class CodeAnswer:
    kind: str  # definicao | usos | impacto | nao_usados | nao_entendi
    text: str
    items: list


class CodeIndex:
    """The project's code base (CodeBase) plus what questions need: names, positions -> lines."""

    def __init__(self, root: str, tsconfig: str = "tsconfig.app.json") -> None:
        from ..code.project import CodeBase
        from ..code.ts_extract import extract

        self.root = pathlib.Path(root)
        self.files = extract(root, tsconfig)
        self.cb = CodeBase(self.files)
        self.decls: dict[str, list[tuple[str, int]]] = {}
        for f in self.files:
            for scope, name, pos, _space, kind in f["decls"]:
                if scope == 0 and kind != "import":  # an import binding is a use of a declaration, not one
                    self.decls.setdefault(name, []).append((f["file"], pos))
        self._text: dict[str, str] = {}

    def line(self, file: str, pos: int) -> int:
        if file not in self._text:
            self._text[file] = (self.root / file).read_text(encoding="utf-8", errors="replace")
        return self._text[file].count("\n", 0, pos) + 1

    def where(self, file: str, pos: int) -> str:
        return f"{file}:{self.line(file, pos)}"


def _frame(words: list[str]) -> str | None:
    for w in words:
        for lemma in morph_lemmas(w.lower(), "V") + [w.lower()]:
            for kind, verbs in FRAMES.items():
                if lemma in verbs:
                    return kind
    return None


REPEAT_WORDS = {"repetido", "repetidos", "repetida", "repetidas", "repetição", "duplicado", "duplicados", "duplicada",
                "duplicação", "clichê", "clichês", "cliche", "cliches", "copiado", "copiada"}


def is_code_question(text: str, index: CodeIndex) -> bool:
    words = re.findall(r"[\w$À-ÿ]+", text)
    if any(w.lower() in REPEAT_WORDS for w in words):
        return True
    names = [w for w in words if w in index.decls]
    unused = any(w.lower() in UNUSED_WORDS for w in words) and any(w.lower() in ("usadas", "usados", "usada", "usado")
                                                                    for w in words)
    asks = bool(words) and words[0].lower() in ("onde", "quem", "quais", "qual", "que", "o") and text.strip().endswith("?")
    return bool(unused or (names and _frame(words)) or (asks and _frame(words)))


def answer(text: str, index: CodeIndex) -> CodeAnswer:
    words = re.findall(r"[\w$À-ÿ]+", text)
    if any(w.lower() in REPEAT_WORDS for w in words):
        from ..code.cliches import find

        found = find(str(index.root))[:12]
        lines = []
        for c in found:
            where = ", ".join(f"{f}:{ln}" for f, ln in c.places[:4]) + (" ..." if len(c.places) > 4 else "")
            example = " ".join(c.example.split())[:110]
            lines.append(f"  {c.saving} nós economizáveis — {len(c.places)} cópias de {c.size} nós: {where}\n"
                         f"      {example}")
        head = f"{len(found)} padrões de código repetido (os que mais economizariam se virassem uma função):\n"
        return CodeAnswer("repetido", head + "\n".join(lines), found)
    if any(w.lower() in UNUSED_WORDS for w in words):
        unused = sorted(index.cb.unused_exports())
        names = {(f, p): n for n, locs in index.decls.items() for f, p in locs}
        items = [(names.get(u, "?"), index.where(*u)) for u in unused]
        head = f"{len(items)} exportações não são usadas fora da própria declaração"
        return CodeAnswer("nao_usados", head + (":\n" + "\n".join(f"  {n}  ({w})" for n, w in items[:40]) if items
                                                else "."), items)
    names = [w for w in words if w in index.decls]
    kind = _frame(words)
    if not names:
        return CodeAnswer("nao_entendi", "Não achei no projeto nenhuma declaração com o nome citado.", [])
    if kind is None:
        return CodeAnswer("nao_entendi", f"Sei o que é {names[0]}, mas não entendi a pergunta "
                                         "(pergunte onde está definido, quem usa, ou o que é afetado).", [])
    name = names[0]
    locs = index.decls[name]
    if kind == "definicao":
        where = ", ".join(index.where(f, p) for f, p in locs)
        return CodeAnswer(kind, f"{name} está definido em {where}.", locs)
    if kind == "usos":
        refs = sorted({r for f, p in locs for r in index.cb.references(f, p)})
        by_file: dict[str, list[int]] = {}
        for f, p in refs:
            by_file.setdefault(f, []).append(index.line(f, p))
        lines = [f"  {f}: linhas {', '.join(map(str, sorted(set(ls))))}" for f, ls in sorted(by_file.items())]
        return CodeAnswer(kind, f"{name} é usado {len(refs)} vez(es) em {len(by_file)} arquivo(s):\n" +
                          "\n".join(lines), refs)
    impacted = sorted({d for f, p in locs for d in index.cb.impact_fast(f, p)})
    names_at = {(f, p): n for n, ls in index.decls.items() for f, p in ls}
    items = [(names_at.get(d, "?"), index.where(*d)) for d in impacted]
    return CodeAnswer(kind, f"Mudar {name} afeta {len(items)} declaração(ões), direta ou indiretamente:\n" +
                      "\n".join(f"  {n}  ({w})" for n, w in items[:40]) + ("\n  ..." if len(items) > 40 else ""),
                      items)
