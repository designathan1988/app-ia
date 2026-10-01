"""Language profiles: what differs between languages in the understanding pipeline, and nothing else.

The meaning side (concepts, entities, frames, abduction) is shared by every language. A language contributes:
- its parser models (trained on its UD treebank) and its lemmas;
- its closed-class grammar: articles, pronouns, modal and copular verbs, the prepositions that mark a value or a
  place (function words, which every grammar of the language lists);
- its catalog of the builder's labels (pt-BR.json, en.json), from which its lexicon is built;
- the verbs of each action frame: listed for Portuguese in frames.json, and for other languages taken from the
  dictionary's translations of those Portuguese verbs (no list per language).

The current language is set by ``use`` around one understanding (the web server handles one request at a time).
"""

from __future__ import annotations

import contextlib
import re
from functools import lru_cache

PROFILES = {
    "pt": {
        "catalog": "pt-BR.json",
        "of": "de",
        "articles": {"o", "a", "os", "as", "um", "uma", "uns", "umas"},
        "article_forms": {"a", "o", "as", "os"},
        "definite": {"o", "a", "os", "as", "este", "esta", "esse", "essa", "aquele", "aquela"},
        "indefinite": {"um", "uma", "uns", "umas"},
        "pronouns": {"isso", "isto", "aquilo", "ele", "ela", "este", "esta", "esse", "essa", "selecionado",
                     "selecionada", "selecao"},
        "modals": {"poder", "querer", "gostar", "precisar", "conseguir", "dever", "ir", "favor", "ter"},
        "copulas": {"ficar", "estar", "ser", "permanecer", "tornar"},
    },
    "en": {
        "catalog": "en.json",
        "of": "of",
        "articles": {"the", "a", "an"},
        "article_forms": {"the", "a", "an"},
        "definite": {"the", "this", "that", "these", "those"},
        "indefinite": {"a", "an", "some"},
        "pronouns": {"it", "this", "that", "selected", "selection"},
        "modals": {"can", "could", "would", "will", "should", "want", "need", "please", "must", "have", "like"},
        "copulas": {"be", "become", "get", "stay", "look"},
        # places and value markers, by the place kinds and cases of frames.json
        "locais": {"dentro": ["in", "into", "inside", "to"], "depois": ["after", "below", "under"],
                   "antes": ["before", "above"], "inicio": ["at the beginning of", "at the start of",
                                                            "to the beginning of", "to the start of"],
                   "fim": ["at the end of", "to the end of", "at the bottom of"]},
        "valor_casos": ["to", "as", "in", "with", "of", "by", "into"],
        "campos": {"text": "text", "content": "text", "name": "name", "label": "text"},
    },
}

_current = ["pt"]


def current() -> str:
    return _current[0]


@contextlib.contextmanager
def use(lang: str):
    previous = _current[0]
    _current[0] = lang if lang in PROFILES else "pt"
    try:
        yield
    finally:
        _current[0] = previous


def profile(lang: str | None = None) -> dict:
    return PROFILES[lang or current()]


@lru_cache(maxsize=1)
def _english_words() -> set:
    from . import concepts

    con = concepts._con()
    if con is None:
        return set()
    return {r[0] for r in con.execute("SELECT DISTINCT word FROM lex WHERE lang = 'en'")}


def detect(text: str) -> str:
    """The language of a request, by which lexicon knows more of its words (MorphoBr for Portuguese, the English
    wordnet plus English function words for English). Portuguese when unsure."""
    from .morph import analyses

    words = [w.lower() for w in re.findall(r"[A-Za-zÀ-ÿ']+", text)]
    if not words:
        return "pt"
    en_fn = PROFILES["en"]["articles"] | PROFILES["en"]["modals"] | {w for ws in PROFILES["en"]["locais"].values()
                                                                       for p in ws for w in p.split()}
    pt = sum(1 for w in words if analyses(w))
    en = sum(1 for w in words if w in _english_words() or w in en_fn or w.rstrip("s") in _english_words())
    accents = any(ch in text.lower() for ch in "áàâãéêíóôõúç")
    return "en" if en > pt and not accents else "pt"


@lru_cache(maxsize=1)
def _english_lemmas() -> dict:
    """form -> lemma from the English treebank's annotation (data, not rules)."""
    from .syntax import models_dir
    import json

    path = models_dir("en") / "lemmas.json"
    if not path.exists():
        return {}
    out = {}
    for form, upos, lemma in json.loads(path.read_text(encoding="utf-8")):
        out.setdefault((form, upos), lemma)
        out.setdefault((form, None), lemma)
    return out


def english_lemma(word: str, upos: str | None = None) -> str:
    w = word.lower()
    table = _english_lemmas()
    if upos is None:
        # a content word without its tag: the noun or adjective reading ("beginning", "heading" are nouns here;
        # verbs are always lemmatized with their tag)
        lem = table.get((w, "NOUN")) or table.get((w, "ADJ")) or table.get((w, "PROPN"))
        if lem:
            return lem.lower()
    lem = table.get((w, upos)) or table.get((w, None))
    if lem:
        return lem.lower()
    # an unseen form: the wordnet's own words decide among the regular endings
    words = _english_words()
    for suffix, repl in (("ies", "y"), ("es", ""), ("s", ""), ("ed", ""), ("ed", "e"), ("ing", ""), ("ing", "e")):
        if w.endswith(suffix) and (w[: -len(suffix)] + repl) in words:
            return w[: -len(suffix)] + repl
    return w


@lru_cache(maxsize=4096)
def frame_verbs(frame_id: str, lang: str) -> frozenset:
    """The verbs of an action frame in a language: Portuguese from frames.json; others from the dictionary's
    translations of those verbs (Wiktionary)."""
    from . import dictionary
    from .understand import FRAMES

    frame = next(f for f in FRAMES["quadros"] if f["id"] == frame_id)
    if lang == "pt":
        return frozenset(frame["verbos"])
    from . import concepts

    out = set()
    for v in frame["verbos"]:
        for t in dictionary.translations(v):
            t = t.lower().strip()
            # only what that language's wordnet knows as a verb ("pôr" also translates the preposition "by")
            if re.fullmatch(r"[a-z]+( [a-z]+)?", t) and concepts.concepts_of(t, lang, "v"):
                out.add(t)
    # and the words of the same concepts in that language (the first senses of each Portuguese verb: the wordnets
    # share their concepts, so "renomear" and "rename" are one concept)
    for v in frame["verbos"][:6]:
        for c, k in concepts.concepts_of(v, "pt", "v")[:2]:
            out.update(w for w in concepts.words_of(c, lang)[:3] if re.fullmatch(r"[a-z]+( [a-z]+)?", w))
    # and the verb of the English label of the builder command that performs the frame ("Rename", "Set")
    from .builder_commands import FRAME_COMMANDS
    from ..builder.scenarios import load_commands
    import json
    import pathlib
    from ..builder.client import DEFAULT_BUILDER

    cid = FRAME_COMMANDS.get(frame_id)
    if cid:
        cat = json.loads((pathlib.Path(DEFAULT_BUILDER) / "src" / "i18n" / "locales" / profile(lang)["catalog"])
                         .read_text(encoding="utf-8"))
        label = cat.get(load_commands().get(cid, {}).get("labelKey") or "", "")
        first = (re.findall(r"[A-Za-z]+", label) or [""])[0].lower()
        if first and concepts.concepts_of(first, lang, "v"):
            out.add(first)
    return frozenset(out)
