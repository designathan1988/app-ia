"""Lexical evidence that links a word to a constant of the ActionSchema, with its origin (A1, roteiro CCG).

Every source here is external data or the builder's own text; none is a list written for this project. Each piece
of evidence is (kind, target, strength, origin) and becomes a feature whose weight is learned:

- ``catalog``  : the word is a word of the builder's own label of the constant (src/i18n/locales pt-BR and en);
- ``wordnet``  : the word reaches the constant through the ILI-linked WordNets (Open English WordNet, OpenWordNet-PT)
                 and their anchors to the builder's labels and the W3C keywords (nucleo/lang/concepts.py); the
                 anchors to the hand-written frames (kind ``acao``) are not used;
- ``values``   : the word names a (property, keyword) in nucleo/lang/values.index (Wiktionary translations of CSS
                 keywords, MDN pt-BR descriptions, the builder's value labels, colour names);
- ``synonym``  : a Wiktionary/OpenWordNet-PT synonym of the word has catalog/wordnet/values evidence;
- ``translation``: a Wiktionary translation of the (Portuguese) word has catalog/values evidence;
- ``number``   : a word whose WordNet concept also has a numeral lemma ("twenty" ~ "20"; "vinte" via the ILI).

``ORIGINS`` documents them for the audit (experiments/a1/auditoria.py).
"""

from __future__ import annotations

import math
import re
from functools import lru_cache

from . import esquema as E
from .values import fold

ORIGINS = {
    "catalog": "builder i18n catalogs (src/i18n/locales/pt-BR.json, en.json)",
    "wordnet": "Open English WordNet 2024 + OpenWordNet-PT via ILI (data/dicionario), anchored to builder labels/W3C",
    "values": "nucleo/lang/values.index: Wiktionary translations of CSS keywords, MDN pt-BR, builder value labels",
    "synonym": "Wiktionary (kaikki pt) and OpenWordNet-PT synonyms",
    "translation": "Wiktionary (kaikki pt) translations pt->en",
    "number": "WordNet numeral lemmas of a word's concept",
}
KINDS = ("op", "prop", "value", "type")
_GRAPH_KIND = {"comando": "op", "propriedade": "prop", "valor": "value", "tipo": "type"}
_WORD = re.compile(r"[^\W\d_]+")


def _words(text: str) -> frozenset:
    return frozenset(fold(w) for w in _WORD.findall((text or "").lower()))


@lru_cache(maxsize=1)
def catalog_index() -> dict:
    """folded word -> [(kind, target)] from the builder's labels of every operation, property, element type and
    value, in both languages."""
    out: dict = {}

    def add(text, kind, target):
        for w in _words(text):
            if len(w) > 2:
                out.setdefault(w, []).append((kind, target))

    for sid, sc in E.schemas().items():
        for lab in sc.labels.values():
            add(re.sub(r"\{\w+\}", " ", lab), "op", sid)
    for p, v in E.properties().items():
        for lab in v["label"].values():
            add(lab, "prop", p)
        add(p.replace("-", " "), "prop", p)
    for t, v in E.element_types().items():
        for lab in v["label"].values():
            add(lab, "type", t)
        add(re.sub(r"([A-Z])", r" \1", t), "type", t)
    for (p, val), labs in E.value_labels().items():
        for lab in labs.values():
            add(lab, "value", (p, val))
    return out


def _from_catalog(word: str) -> list:
    return [(k, t, 1.0, "catalog") for k, t in catalog_index().get(word, ())]


def _from_graph(word: str, lang: str) -> list:
    from . import concepts

    out = []
    try:
        for ent, cost, *_ in concepts.meanings(word, lang)[:40]:
            kind = _GRAPH_KIND.get(ent[0])
            if kind:
                out.append((kind, ent[1], math.exp(-cost), "wordnet"))
    except Exception:  # noqa: BLE001
        pass
    return out


def _from_values(word: str) -> list:
    from . import values

    try:
        pairs = values.index().get(word, ())
    except Exception:  # noqa: BLE001
        pairs = ()
    n = max(1, len(pairs))
    return [("value", (p, v), 1.0 / math.sqrt(n), "values") for p, v in pairs]


@lru_cache(maxsize=50_000)
def evidence(word: str, lang: str) -> tuple:
    """All evidence for one folded word: (kind, target, strength, origin)."""
    out = _from_catalog(word) + _from_graph(word, lang) + _from_values(word)
    if lang == "pt" and len(word) > 3:
        from . import dictionary

        try:
            for s in dictionary.synonyms(word)[:8]:
                for k, t, st, o in _from_catalog(fold(s)) + _from_values(fold(s)) + _from_graph(fold(s), "pt")[:8]:
                    out.append((k, t, 0.5 * st, "synonym"))
            for tr in dictionary.translations(word)[:4]:
                for w in sorted(_words(tr)):
                    for k, t, st, o in _from_catalog(w) + _from_values(w):
                        out.append((k, t, 0.7 * st, "translation"))
        except Exception:  # noqa: BLE001
            pass
    best: dict = {}
    for k, t, st, o in out:
        key = (k, t, o)
        if st > best.get(key, 0.0):
            best[key] = st
    return tuple((k, t, st, o) for (k, t, o), st in sorted(best.items()))


@lru_cache(maxsize=10_000)
def number(word: str, lang: str) -> float | None:
    """The number a numeral word names, from its WordNet concept's numeral lemma ("twenty" -> 20)."""
    if re.fullmatch(r"-?\d+(?:[.,]\d+)?", word):
        return float(word.replace(",", "."))
    from . import concepts

    words = [(word, lang)]
    if lang == "pt":
        from . import dictionary

        try:
            words += [(fold(t), "en") for t in dictionary.translations(word)[:3]]
        except Exception:  # noqa: BLE001
            pass
    try:
        for w0, lg in words:
            for c, _ in concepts.concepts_of(w0, lg)[:3]:
                for w in concepts.words_of(c, "en"):
                    if re.fullmatch(r"\d+", w):
                        return float(w)
    except Exception:  # noqa: BLE001
        return None
    return None
