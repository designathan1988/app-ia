"""ActionSchema: the semantic universe of the builder, discovered from the builder itself (A1, roteiro CCG).

Nothing here is a linguistic inventory. Every operation, its typed arguments, when it is available, whether it
changes the document, what it writes and what it is called in each language come from the builder's own files:

- ``manifest/commands/*.json``: the 263 commands, argument names and types, availability predicate, history;
- ``src/i18n/locales/{pt-BR,en}.json``: each command's label, with its argument slots ("Definir {property} como
  {value}"), the labels of properties, values, element types and attributes;
- ``data/cache/efeitos.json``: what each command was observed to write when run on the builder's fixtures
  (``nucleo/builder/effects.py``, learned by experiment);
- ``manifest/properties.json`` / ``elements.json``: properties (with ``appliesTo``), element types, palette entries
  and attributes (with the command that edits each and the element types it applies to).

An operation acts on the document when the builder records it in its history (``history.undoable``) or when it was
observed to change the document; selection and history commands are kept because a conversation needs them.
"""

from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass, field
from functools import lru_cache

from ..builder.client import DEFAULT_BUILDER

SLOT = re.compile(r"\{(\w+)\}")


@dataclass(frozen=True)
class Arg:
    name: str
    type: str  # the manifest's argument type: node, nodes, property, string, enum, number, integer, color, ...
    values: tuple = ()
    optional: bool = False


@dataclass
class ActionSchema:
    id: str
    args: tuple  # (Arg, ...)
    availability: str  # the builder's predicate: always, hasSelection, editableSelection, ...
    undoable: bool
    writes: tuple  # fields the command was observed to write ("style:color", "node:added", "doc:text", ...)
    labels: dict = field(default_factory=dict)  # lang -> label text with {slots}
    namespace: str = ""

    def slots(self, lang: str) -> list[str]:
        return SLOT.findall(self.labels.get(lang, ""))

    def label_words(self, lang: str) -> list[str]:
        return [w for w in re.findall(r"[^\W\d_]+", SLOT.sub(" ", self.labels.get(lang, "")).lower()) if w]

    def acts_on_selection(self) -> bool:
        return self.availability in ("hasSelection", "editableSelection", "singleSelection", "targetOrSelection")


def _root(root=None) -> pathlib.Path:
    return pathlib.Path(root or DEFAULT_BUILDER)


@lru_cache(maxsize=2)
def catalog(lang: str, root: str | None = None) -> dict:
    name = {"pt": "pt-BR", "en": "en"}[lang]
    return json.loads((_root(root) / "src" / "i18n" / "locales" / f"{name}.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _effects() -> dict:
    p = pathlib.Path(__file__).resolve().parents[2] / "data" / "cache" / "efeitos.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


@lru_cache(maxsize=1)
def schemas(root: str | None = None) -> dict:
    """id -> ActionSchema for every command of the manifest that acts on the document, the selection or the
    history."""
    from ..builder.scenarios import load_commands

    cmds = load_commands(root)
    writes = _effects().get("writes", {})
    out = {}
    for cid, c in cmds.items():
        hist = c.get("history") or {}
        observed = tuple(sorted(writes.get(cid, {}).keys())) if isinstance(writes.get(cid), dict) else ()
        ns = cid.split(".")[0]
        if not (hist.get("undoable") or observed or ns in ("selection", "history")):
            continue
        args = tuple(Arg(n, a.get("type", "string"), tuple(a.get("values") or ()), bool(a.get("optional")))
                     for n, a in (c.get("args") or {}).items())
        labels = {lang: catalog(lang, root).get(c.get("labelKey") or "", "") for lang in ("pt", "en")}
        out[cid] = ActionSchema(cid, args, (c.get("availability") or {}).get("predicate") or "always",
                                bool(hist.get("undoable")), observed, labels, ns)
    return out


# -- the other typed constants of the domain ---------------------------------------------------------------------
@lru_cache(maxsize=1)
def manifest(root: str | None = None) -> dict:
    base = _root(root) / "manifest"
    return {"properties": json.loads((base / "properties.json").read_text(encoding="utf-8")),
            "elements": json.loads((base / "elements.json").read_text(encoding="utf-8"))}


@lru_cache(maxsize=1)
def properties(root: str | None = None) -> dict:
    """property id -> {label: {lang: text}, appliesTo, valueType}"""
    out = {}
    for p in manifest(root)["properties"]["properties"]:
        lk = p.get("labelKey") or ""
        out[p["id"]] = {"label": {lang: catalog(lang, root).get(lk, "") for lang in ("pt", "en")},
                        "appliesTo": p.get("appliesTo") or "always", "valueType": p.get("valueType")}
    return out


@lru_cache(maxsize=1)
def element_types(root: str | None = None) -> dict:
    """element type -> {label: {lang: text}, content}"""
    out = {}
    for e in manifest(root)["elements"]["elements"]:
        lk = e.get("labelKey") or ""
        out[e["id"]] = {"label": {lang: catalog(lang, root).get(lk, "") for lang in ("pt", "en")},
                        "content": e.get("content")}
    return out


@lru_cache(maxsize=1)
def palette(root: str | None = None) -> dict:
    """palette entry -> element type it inserts"""
    out = {}
    for group in manifest(root)["elements"]["palette"]:
        for entry in group["entries"]:
            if isinstance(entry, dict):
                out[entry["id"]] = entry.get("element") or entry.get("type")
    return out


@lru_cache(maxsize=1)
def value_labels(root: str | None = None) -> dict:
    """(property, value) -> {lang: label}, from the catalog keys value.<property>.<value>"""
    out: dict = {}
    for lang in ("pt", "en"):
        for k, v in catalog(lang, root).items():
            if k.startswith("value."):
                parts = k.split(".")
                if len(parts) >= 3:
                    out.setdefault((parts[1], ".".join(parts[2:])), {})[lang] = v
    return out
