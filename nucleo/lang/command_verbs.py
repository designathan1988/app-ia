"""Verbs grounded in the builder's own commands, read from its manifest and its pt-BR catalog (nothing typed here).

A command gives a verb its meaning when the manifest says it acts on the element the user points at and changes the
document:
- its availability is "hasSelection" or "targetOrSelection";
- it takes no argument but the target;
- it is undoable (it edits the document, not the view).

Its pt-BR label must start with an infinitive (MorphoBr): "Duplicar", "Ocultar", "Bloquear", "Mover para cima".
That infinitive, applied to an element, means "run this command on it". The rest of the label ("para cima") is part
of the meaning and must be said too. The same command is also named by the first Portuguese verbs a dictionary
(Wiktionary) gives for the verb of its English label ("Hide" -> "esconder", "ocultar").

A command that switches a flag ("Ocultar" writes ``hidden``) is not run when the element already has the flag:
the label names the state the user asks for, and running it again would undo that state.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from functools import lru_cache

from ..builder.client import DEFAULT_BUILDER
from . import values
from .lexicon import lemma_seq
from .morph import analyses


STRUCTURAL = {"added", "removed", "moved", "reordered", "text", "name", "style", "attributes"}


@dataclass(frozen=True)
class CommandVerb:
    verb: str  # infinitive lemma
    command: str
    label: str
    rest: tuple  # lemmas of the label after the verb, which the sentence must also say
    flag: str | None  # the node field the command switches, when it is a toggle
    english: str = ""  # the verb of the command's English label ("hide")


def _qualifying(root: str | None = None):
    """(command id, manifest entry) for the commands that act on the pointed element and edit the document."""
    from ..builder.scenarios import load_commands

    for cid, c in load_commands(root).items():
        avail = (c.get("availability") or {}).get("predicate")
        if avail not in ("hasSelection", "targetOrSelection") or set(c.get("args", {})) - {"target"}:
            continue
        if (c.get("history") or {}).get("undoable"):
            yield cid, c


def english_verbs(root: str | None = None) -> set[str]:
    """The first word of each qualifying command's English label ("Hide", "Duplicate"), to be translated."""
    base = pathlib.Path(root or DEFAULT_BUILDER)
    catalog = json.loads((base / "src" / "i18n" / "locales" / "en.json").read_text(encoding="utf-8"))
    out = set()
    for _, c in _qualifying(root):
        label = catalog.get(c.get("labelKey") or "", "")
        if label and "{" not in label:
            out.add(label.split()[0].lower())
    return out


@lru_cache(maxsize=1)
def table(root: str | None = None) -> dict[str, list[CommandVerb]]:
    from ..builder.effects import load_model

    base = pathlib.Path(root or DEFAULT_BUILDER)
    catalog = json.loads((base / "src" / "i18n" / "locales" / "pt-BR.json").read_text(encoding="utf-8"))
    writes = load_model().writes
    out: dict[str, list[CommandVerb]] = {}
    english = json.loads((base / "src" / "i18n" / "locales" / "en.json").read_text(encoding="utf-8"))
    translations = values._load(values.TRANSLATIONS)
    for cid, c in _qualifying(root):
        label = catalog.get(c.get("labelKey") or "", "")
        words = label.split()
        if not words or "{" in label:
            continue
        first = words[0].lower()
        if not any(lem == first and tags.startswith("V+INF") for lem, tags in analyses(first)):
            continue
        fields = [k.split(":", 1)[1] for k in writes.get(cid, {}) if k.startswith("node:")]
        # a single non-structural node field (``hidden``, ``locked``): a flag; whether the element already has it is
        # read from the document when the verb is used
        flag = fields[0] if len(fields) == 1 and fields[0] not in STRUCTURAL else None
        rest = lemma_seq(" ".join(words[1:]))
        en = (english.get(c.get("labelKey") or "", "").split() or [""])[0].lower()
        out.setdefault(first, []).append(CommandVerb(first, cid, label, rest, flag, en))
        # other Portuguese verbs for the same action: the first verbs a dictionary gives for the English label's
        # verb ("Hide" -> esconder, ocultar)
        verbs = [w for w in translations.get(en, []) if "INF" in values._pos(w)][:2]
        for v in verbs:
            if v != first and not any(x.command == cid for x in out.get(v, [])):
                out.setdefault(v, []).append(CommandVerb(v, cid, label, rest, flag, en))
    return out


def verbs() -> set[str]:
    return set(table())
