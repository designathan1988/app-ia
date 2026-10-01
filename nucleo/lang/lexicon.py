"""The grounded lexicon: Portuguese phrases -> the builder's own entities, built from the builder's pt-BR catalog.

Every entry comes from the manifest plus the human-written pt-BR catalog. Nothing here is typed by hand:
- element types: element and palette labels ("Seção", "Botão");
- CSS properties: property labels ("Cor de fundo", "Margem superior");
- attributes: attribute labels ("Texto alternativo");
- style states: state labels ("Ao passar o mouse");
- breakpoints: breakpoint labels ("Celular").

A label is stored as the sequence of lemmas of its words, so "cores de fundo" and "cor de fundo" meet. Matching is by
lemma sequence, longest first, inside a phrase the parser delimited.
"""

from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass
from functools import lru_cache

from ..builder.client import DEFAULT_BUILDER
from .morph import analyses

STOP = {"o", "a", "os", "as", "um", "uma", "uns", "umas"}


def stop() -> set:
    """The articles of the current language (not content)."""
    from . import langs

    return langs.profile()["articles"]


def lemma_of(word: str) -> str:
    """Nouns and adjectives to their lemma (singular, masculine for adjectives); other words lowercased. The result
    is folded (no accents), so "título", "titulo" and "TÍTULO" are the same word to every matcher."""
    from . import langs
    from .values import fold

    if langs.current() == "en":
        return fold(langs.english_lemma(word))
    w = word.lower()
    cands = [(lem, tags) for lem, tags in analyses(w) if tags.startswith("N+") or tags.startswith("A+")]
    # prefer a plain analysis (not a diminutive/augmentative of another word: "linha" is not "lia" + -inha)
    cands.sort(key=lambda x: ("+DIM" in x[1] or "+AUG" in x[1], x[0] != w, x[0]))
    return fold(cands[0][0] if cands else w)


def lemma_seq(text: str) -> tuple[str, ...]:
    from .tokenize import contractions

    table = contractions()
    words = []
    for w in re.findall(r"[\wÀ-ÿ-]+", text.lower()):
        words += list(table.get(w, (w,)))  # "do" -> "de o", as the parser sees it
    return tuple(lemma_of(w) for w in words if w not in stop())  # lemma_of folds accents


@dataclass(frozen=True)
class Entry:
    kind: str  # tipo | propriedade | atributo | campo | estado | breakpoint
    id: str
    label: str
    lemmas: tuple[str, ...]


def load(root: str | None = None) -> list[Entry]:
    """The lexicon of the current language (its catalog of the builder's labels)."""
    from . import langs

    with langs.use(langs.current()):
        return _load(langs.current(), root)


@lru_cache(maxsize=4)
def _load(lang: str, root: str | None = None) -> list[Entry]:
    from . import langs

    base = pathlib.Path(root or DEFAULT_BUILDER)
    cat = json.loads((base / "src" / "i18n" / "locales" / langs.profile(lang)["catalog"]).read_text(encoding="utf-8"))

    def flat(d, p=""):
        for k, v in d.items():
            if isinstance(v, dict):
                yield from flat(v, p + k + ".")
            else:
                yield p + k, v

    words = dict(flat(cat))
    man = base / "manifest"
    elements = json.loads((man / "elements.json").read_text(encoding="utf-8"))
    props = json.loads((man / "properties.json").read_text(encoding="utf-8"))
    out: list[Entry] = []

    def add(kind, id_, label):
        if isinstance(label, str) and label and "{" not in label:
            clean = re.sub(r"\s*\([^)]*\)", "", label)
            out.append(Entry(kind, id_, label, lemma_seq(clean)))

    for e in elements["elements"]:
        add("tipo", e["id"], words.get(e["labelKey"]))
    for group in elements["palette"]:
        for entry in group["entries"]:
            if entry.get("element"):
                add("tipo", entry["element"], words.get(f"palette.entry.{entry['id']}"))
    for p in props["properties"]:
        add("propriedade", p["id"], words.get(p.get("labelKey", "")))
    for a in elements.get("attributes") or []:
        if isinstance(a, dict) and a.get("html"):
            # a real HTML attribute: stored in the node's attributes under its HTML name
            add("atributo", a["html"], words.get(a.get("labelKey") or f"attribute.{a['id']}.label"))
        elif isinstance(a, dict):
            # html: null (text, tag): a field of the node itself, edited like an attribute in the inspector
            add("campo", a["id"], words.get(a.get("labelKey") or f"attribute.{a['id']}.label"))
    for st in props.get("states") or []:
        sid = st["id"] if isinstance(st, dict) else st
        camel = re.sub(r"-(\w)", lambda m: m.group(1).upper(), sid)
        add("estado", sid, words.get(f"styleState.{camel}"))
    for bp in props.get("breakpoints") or []:
        bid = bp["id"] if isinstance(bp, dict) else bp
        add("breakpoint", bid, words.get(f"breakpoint.{bid}"))
    # the CSS name itself is also a way to name a property ("o display", "o padding-top"): the manifest's, plus
    # every property the W3C specifications define (@webref/css, installed with the builder)
    css_names = {p["id"] for p in props["properties"]}
    webref = base / "node_modules" / "@webref" / "css"
    for spec in sorted(webref.glob("*.json")) if webref.is_dir() else []:
        try:
            data = json.loads(spec.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for prop in data.get("properties", []) if isinstance(data, dict) else []:
            name = prop.get("name") if isinstance(prop, dict) else None
            if isinstance(name, str) and not name.startswith("-"):
                css_names.add(name)
    for name in sorted(css_names):
        out.append(Entry("propriedade", name, name, (name,)))
    # phrases the user taught ("cor de fundo significa fundo"): another label for an entity already grounded
    from .learned import phrases, structures

    for phrase, d in phrases().items():
        out.append(Entry(d["tipo"], d["entidade"], phrase, lemma_seq(phrase)))
    for name in structures():  # a taught composite element is a type too ("insira um card ...")
        out.append(Entry("tipo", f"estrutura:{name}", name, lemma_seq(name)))
    return out


def _close(a: str, b: str) -> bool:
    """Equal, or one typing slip apart (one letter missing, extra, wrong or two swapped) for words of 5+ letters."""
    if a == b:
        return True
    if min(len(a), len(b)) < 5 or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        return len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]]
                                  and a[diff[1]] == b[diff[0]])
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def match(seq: tuple[str, ...], kinds: set[str], start: int = 0) -> list[tuple[Entry, int]]:
    """Entries of the given kinds whose lemma sequence occurs in `seq` at `start`, longest first: (entry, length).
    Exact matches first; a match with typing slips (see ``_close``) only when there is no exact one."""
    from . import langs

    return list(_match(tuple(seq), frozenset(kinds), start, langs.current()))


@lru_cache(maxsize=200_000)
def _match(seq: tuple, kinds: frozenset, start: int, lang: str) -> tuple:
    exact, reordered, near = [], [], []
    for e in load():
        if e.kind not in kinds or not e.lemmas:
            continue
        if len(e.lemmas) == 1 and "-" in e.lemmas[0]:
            # a CSS name said with spaces ("background color" for background-color)
            n = e.lemmas[0].count("-") + 1
            if "-".join(seq[start:start + n]) == e.lemmas[0]:
                exact.append((e, n))
                continue
        part = tuple(seq[start:start + len(e.lemmas)])
        if len(part) != len(e.lemmas):
            continue
        if part == e.lemmas:
            exact.append((e, len(e.lemmas)))
        elif len(part) > 1 and sorted(part) == sorted(e.lemmas):
            # the same words in another order: a label is often written head-first ("Margin top") and said
            # modifier-first ("top margin")
            reordered.append((e, len(e.lemmas)))
        elif e.lemmas != (e.id,) and all(_close(x, y) for x, y in zip(part, e.lemmas)):
            near.append((e, len(e.lemmas)))
    out = exact + [r for r in reordered if r[1] > max((x[1] for x in exact), default=0)] or near
    out.sort(key=lambda x: -x[1])
    return tuple(out)


def _clear() -> None:
    _load.cache_clear()
    _match.cache_clear()


load.cache_clear = _clear  # learned vocabulary clears it
