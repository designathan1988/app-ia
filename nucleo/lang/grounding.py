"""Grounding a word the system does not know, through the dictionary, until it reaches something the builder can do.

A word is grounded when it names an element type, a property, a value, a command or a verb class the system acts
on. For any other word, the meaning is searched in the dictionary (``dictionary.py``), the way a reader looks a word
up and follows its definition:

1. **synonyms** (Wiktionary, OpenWordNet-PT): "esconder" ~ "ocultar" (a command), "figura" ~ "imagem" (a type);
2. **translation**: the English word is the builder's own English label or a CSS keyword ("rodapé" -> "footer",
   "sublinhar" -> "underline");
3. **definition**: a word of its first definitions is grounded ("colorir: dar cor a" -> "cor"; "pintar: aplicar ...
   uma cor ..." -> "cor"), followed one more step when needed.

Every meaning found carries its cost (each step is an assumption: shorter and more direct paths are likelier) and its
path, so the reading can be explained ("pintar ≈ cor, pela definição"). Nothing here is a list of words: the
vocabulary is the dictionary's; what the words can mean is the builder's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from . import dictionary, lexicon
from .values import fold

STEP = {"sinonimo": 1.0, "traducao": 1.0, "definicao": 1.5}
MAX_COST = 3.0


@dataclass(frozen=True)
class Meaning:
    kind: str  # verbo | comando | tipo | propriedade | valor | familia
    target: object  # verb lemma | command id | type id | property id | (property, value) | valueType
    cost: float
    path: tuple = field(default=())  # (("sinonimo", "ocultar"), ...)

    def explain(self, word: str) -> str:
        steps = " → ".join(f"{w} ({how})" for how, w in self.path)
        return f"«{word}» → {steps}" if steps else f"«{word}»"


def _english_labels(kind: str) -> dict[str, str]:
    """English label word -> entity id, from the builder's English catalog (types and properties)."""
    import json
    import pathlib

    from ..builder.client import DEFAULT_BUILDER

    base = pathlib.Path(DEFAULT_BUILDER)
    en = json.loads((base / "src" / "i18n" / "locales" / "en.json").read_text(encoding="utf-8"))
    pt = json.loads((base / "src" / "i18n" / "locales" / "pt-BR.json").read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for e in lexicon.load():
        if e.kind != kind:
            continue
        for key, label in pt.items():
            if label == e.label and key in en and len(en[key].split()) == 1:
                out.setdefault(en[key].lower(), e.id)
    return out


@lru_cache(maxsize=1)
def _type_en() -> dict[str, str]:
    return _english_labels("tipo")


def direct(word: str) -> list[Meaning]:
    """What a single word already names, without the dictionary."""
    from . import command_verbs, learned
    from .values import index as value_index

    w = fold(word)
    out = []
    for e, n in lexicon.match((lexicon.lemma_of(word),), {"tipo", "propriedade"}):
        if n == 1:
            out.append(Meaning("tipo" if e.kind == "tipo" else "propriedade", e.id, 0.0))
    for pair in value_index().get(fold(lexicon.lemma_of(word)), []):
        out.append(Meaning("valor", pair, 0.0))
    if word in command_verbs.table():
        out += [Meaning("comando", cv.command, 0.0) for cv in command_verbs.table()[word] if not cv.rest]
    from .understand import FRAMES

    if any(word in f["verbos"] for f in FRAMES["quadros"]) or word in learned.classes() or word in learned.verbs():
        out.append(Meaning("verbo", word, 0.0))
    for e in lexicon.load():  # the word heads property labels: "cor" (cor do texto, cor da borda...)
        if e.kind == "propriedade" and e.lemmas[:1] == (w,) and len(e.lemmas) > 1:
            from .values import _builder_properties

            vt = _builder_properties().get(e.id, {}).get("valueType")
            if vt:
                out.append(Meaning("familia", vt, 0.5))
                break
    return out


def _from_translation(en: str) -> list[Meaning]:
    from . import command_verbs
    from .values import _builder_properties, _keywords, named_colors

    out = []
    if en in _type_en():
        out.append(Meaning("tipo", _type_en()[en], 0.0))
    if en in command_verbs.english_verbs():
        for verbs in command_verbs.table().values():
            for cv in verbs:
                if not cv.rest and cv.english == en:
                    out.append(Meaning("comando", cv.command, 0.0))
    if en in named_colors():
        from .values import color_properties

        out += [Meaning("valor", (p, en), 0.0) for p in color_properties()]
    props = [p for p in _builder_properties() if en in _keywords(p)]
    if 0 < len(props) <= 4:
        out += [Meaning("valor", (p, en), 0.0) for p in props]
    return out


def _from_graph(word: str, pos: str | None, lang: str) -> list[Meaning]:
    """Meanings through the concept graph (``concepts``): the word's senses, the relations between concepts, and
    the machine's entities anchored to concepts."""
    from . import concepts

    wn_pos = {"V": "v", "N": "n", "A": "a"}.get(pos or "", None)
    out = []
    for entity, cost, path in concepts.meanings(word, lang, wn_pos):
        kind, target = entity
        steps = tuple(("conceito", concepts.explain(((c, how),), lang)) for c, how in path)
        out.append(Meaning({"acao": "acao"}.get(kind, kind), target, cost, steps))
    return out


@lru_cache(maxsize=20_000)
def meanings(word: str, pos: str | None = None, depth: int = 2, lang: str = "pt") -> tuple[Meaning, ...]:
    """The meanings a word can have for the machine, cheapest first: what it names directly, then the concept
    graph, then the dictionary's synonyms, translations and definitions (for words the wordnets lack)."""
    found = {(m.kind, m.target): m for m in direct(word)}
    if found:
        return tuple(sorted(found.values(), key=lambda m: m.cost))
    lemmas = [word]
    from .morph import analyses

    lemmas += [lem for lem, tags in analyses(word) if lem not in lemmas and (not pos or tags.startswith(pos))]
    for lem in lemmas[:3]:
        for m in _from_graph(lem, pos, lang):
            key = (m.kind, m.target)
            if key not in found or m.cost < found[key].cost:
                found[key] = m
    from_graph = bool(found)

    def add(ms, how, via, base):
        for m in ms:
            cost = base + STEP.get(how, 1.0) + m.cost
            if cost > MAX_COST:
                continue
            key = (m.kind, m.target)
            if key not in found or cost < found[key].cost:
                found[key] = Meaning(m.kind, m.target, cost, ((how, via),) + m.path)

    for s in dictionary.synonyms(word):
        add(direct(s), "sinonimo", s, 0.0)
    for en in dictionary.translations(word):
        add(_from_translation(en), "traducao", en, 0.0)
    # the dictionary's synonyms and translations always count (a synonym may be a known action the wordnet does
    # not link: "travar" ~ "trancar"); its definitions only when the graph found nothing (they are noisier)
    if depth > 0 and not from_graph:
        for g in dictionary.gloss_words(word, pos):
            if g in GLOSS_STOP or fold(g) == fold(word) or not _content_word(g):
                continue
            sub = direct(g) or _from_graph(g, None, "pt") or (meanings(g, None, depth - 1) if depth > 1 else ())
            add(sub, "definicao", g, 0.0)
    return tuple(sorted(found.values(), key=lambda m: m.cost))


# function words of definitions: they ground to nothing and would only add noise
GLOSS_STOP = {"que", "para", "com", "por", "uma", "dos", "das", "seu", "sua", "mais", "como", "ser", "ter", "estar",
              "outro", "outra", "mesmo", "algo", "alguma", "algum", "pelo", "pela", "nas", "nos", "num", "numa",
              "onde", "quando", "qual", "diz", "relativo", "pessoa", "terceira", "singular", "presente", "indicativo",
              "verbo", "plural", "feminino", "masculino", "forma", "ato", "efeito", "ação", "todo", "toda", "todos", "todas",
              "primeiro", "primeira", "início", "coisa", "modo", "maneira", "parte", "tipo"}


@lru_cache(maxsize=50_000)
def _content_word(w: str) -> bool:
    """A noun, adjective or verb of a definition (MorphoBr), not a function word ("todas", "onde", "seu")."""
    from .morph import analyses

    tags = {t.split("+")[0] for _, t in analyses(w)}
    return bool(tags & {"N", "A", "V"}) and not tags & {"DET", "PRON", "PREP", "CONJ", "NUM", "ADV"}
