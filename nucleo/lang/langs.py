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
        "between": {"entre"},
        "universal": {"todo", "toda", "todos", "todas", "cada"},
        # totality: "a página inteira" is the page itself, all of it
        "whole": {"inteiro", "inteira", "inteiros", "inteiras", "todo", "toda"},
        # the side a spatial preposition names, as property labels say it ("acima de" -> superior)
        "sides": {"antes": "superior", "depois": "inferior"},
        # degree: comparison words and the verbs of changing an amount (closed class)
        "more": {"maior", "maiores", "aumentar", "ampliar", "crescer", "engrossar"},
        "less": {"menor", "menores", "menos", "diminuir", "reduzir", "encolher", "afinar"},
        # ("mais um parágrafo" is a new paragraph, not a bigger one: "mais" alone is not a comparison here)
        "new": {"novo", "nova", "novos", "novas", "outro", "outra", "outros", "outras", "mais"},
        "informal": {"pro": ["para", "o"], "pra": ["para", "a"], "pros": ["para", "os"], "pras": ["para", "as"],
                     "num": ["em", "um"], "numa": ["em", "uma"], "nuns": ["em", "uns"], "numas": ["em", "umas"]},
        "ordinals": {"primeiro": 0, "primeira": 0, "segundo": 1, "segunda": 1, "terceiro": 2, "terceira": 2,
                     "quarto": 3, "quarta": 3, "ultimo": -1, "ultima": -1, "penultimo": -2, "penultima": -2},
        "say": {"as": "como", "in": "em", "to": "para", "at": ", na posição", "with_text": "com o texto",
                "with_name": "com o nome", "already": "(já está assim)", "element": "o elemento", "text": "texto",
                "name": "nome", "attributes": "atributos"},
        "articles": {"o", "a", "os", "as", "um", "uma", "uns", "umas"},
        "article_forms": {"a", "o", "as", "os"},
        "definite": {"o", "a", "os", "as", "este", "esta", "esse", "essa", "aquele", "aquela"},
        "indefinite": {"um", "uma", "uns", "umas"},
        "pronouns": {"isso", "isto", "aquilo", "ele", "ela", "este", "esta", "esse", "essa", "selecionado",
                     "selecionada", "selecao"},
        "modals": {"poder", "querer", "gostar", "precisar", "conseguir", "dever", "ir", "favor", "ter", "possível",
                   "possivel"},
        "copulas": {"ficar", "estar", "ser", "permanecer", "tornar"},
    },
    "en": {
        "catalog": "en.json",
        "of": "of",
        "between": {"between"},
        "from": "from",
        "universal": {"all", "every", "each"},
        "whole": {"whole", "entire", "full"},
        "sides": {"antes": "top", "depois": "bottom"},
        "more": {"bigger", "larger", "more", "increase", "enlarge", "grow", "greater", "wider", "taller"},
        "less": {"smaller", "less", "decrease", "reduce", "shrink", "narrower", "shorter"},
        "new": {"new", "another", "extra", "more", "additional"},
        "ordinals": {"first": 0, "second": 1, "third": 2, "fourth": 3, "last": -1, "penultimate": -2},
        "say": {"as": "to", "in": "in", "to": "to", "at": ", at position", "with_text": "with the text",
                "with_name": "named", "already": "(already so)", "element": "the element", "text": "text",
                "name": "name", "attributes": "attributes"},
        "articles": {"the", "a", "an"},
        "article_forms": {"the", "a", "an"},
        "definite": {"the", "this", "that", "these", "those"},
        "indefinite": {"a", "an", "some"},
        "pronouns": {"it", "this", "that", "selected", "selection"},
        "modals": {"can", "could", "would", "will", "should", "want", "need", "please", "must", "have", "like", "possible",
                   "'d", "'ll", "wanna", "gonna"},
        "copulas": {"be", "become", "get", "stay", "look"},
        # places and value markers, by the place kinds and cases of frames.json
        "locais": {"dentro": ["in", "into", "inside", "to"],
                   "depois": ["after", "below", "under", "underneath", "beneath", "right after", "right below",
                              "between"],
                   "antes": ["before", "above", "on top of", "right before", "right above"],
                   "inicio": ["at the beginning of", "at the start of", "to the beginning of", "to the start of",
                              "at the top of", "to the top of", "at the top", "at the beginning"],
                   "fim": ["at the end of", "to the end of", "at the bottom of", "to the bottom of", "at the end",
                           "at the bottom"]},
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


@lru_cache(maxsize=8)
def action_word(action: str, lang: str) -> str:
    """The verb the builder's own catalog uses, in a language, for an action: the first word of the label of the
    command that performs it ("Insert {element}" -> insert; "Excluir" -> excluir)."""
    import json
    import pathlib

    from ..builder.client import DEFAULT_BUILDER

    keys = {"insert": "command.insertElement", "remove": "command.delete", "move": "command.moveTo",
            "set": "command.setText"}
    cat = json.loads((pathlib.Path(DEFAULT_BUILDER) / "src" / "i18n" / "locales" / profile(lang)["catalog"])
                     .read_text(encoding="utf-8"))
    label = cat.get(keys[action], action)
    return (re.findall(r"[^\s{]+", label) or [action])[0].lower()


MESSAGES = {
    "pt": {
        "not_understood": "Não entendi: {why}.", "no_verb": "não achei o verbo do pedido",
        "no_such_element": "nenhum elemento se chama «{name}»",
        "missing_value": "falta o valor (por exemplo: «... como 24px»)",
        "unknown_verb": "não conheço o verbo «{verb}»",
        "verb_without_object": "entendi o verbo «{verb}», mas não o que ele deve alterar",
        "ask_unknown_verb": "Não conheço o verbo «{verb}». O que ele deve fazer? (responda com um pedido que eu já "
                            "entendo, ou ensine com «{verb} significa ...»)",
        "which": "Qual deles: {names}?", "did_you_mean": "Você quer dizer {options}?", "or": " ou ",
        "confirm": "Não tenho certeza{why}: entendi «{what}». É isso? (sim/não)",
        "unknown_verb_guess": "{what} (não conheço «{verb}»; entendi pelo resto da frase)",
        "nothing_done": "Certo, nada foi feito.", "no_plan": "Entendi «{what}», mas não achei comandos que façam isso.",
        "learned": "Aprendi: «{verb}» = «{body}».", "same_again": "O mesmo: {what}",
        "part_failed": "Nada foi feito: na parte «{part}»: {why}",
        "ask_amount": "{prop} de «{name}» não tem valor definido para eu aumentar ou diminuir: qual valor? "
                      "(por exemplo: «... para 24px»)",
    },
    "en": {
        "not_understood": "I did not understand: {why}.", "no_verb": "I found no verb in the request",
        "no_such_element": "no element is called «{name}»",
        "missing_value": "the value is missing (for example: «... to 24px»)",
        "unknown_verb": "I do not know the verb «{verb}»",
        "verb_without_object": "I understood the verb «{verb}», but not what it should change",
        "ask_unknown_verb": "I do not know the verb «{verb}». What should it do? (answer with a request I already "
                            "understand)",
        "which": "Which one: {names}?", "did_you_mean": "Do you mean {options}?", "or": " or ",
        "confirm": "I am not sure{why}: I understood «{what}». Is that right? (yes/no)",
        "unknown_verb_guess": "{what} (I did not know «{verb}»; I understood it from the rest of the sentence)",
        "nothing_done": "OK, nothing was done.", "no_plan": "I understood «{what}», but found no commands that do it.",
        "learned": "Learned: «{verb}» = «{body}».", "same_again": "The same: {what}",
        "part_failed": "Nothing was done: in the part «{part}»: {why}",
        "ask_amount": "The {prop} of «{name}» has no value set for me to make bigger or smaller: which value? "
                      "(for example: «... to 24px»)",
    },
}


def msg(key: str, lang: str | None = None, **kw) -> str:
    """A message of the system itself, in the conversation's language."""
    return MESSAGES[lang or current()][key].format(**kw)
