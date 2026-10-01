"""Questions about the page, answered from the document, in the language they were asked in.

A question is recognized by its form (a question mark, or an interrogative word of the language: closed-class
grammar in ``langs``). Its content is grounded by the same machinery as requests: the element it is about
(``_reference``), the property (the lexicon, a property family, the concept graph), the type (lexicon or graph).

Kinds of question, by what they ask:
- **content**: what an element (or the page) has ("o que tem na seção Topo?", "what is in the section?");
- **value**: a property or the text of an element ("qual a cor do título?", "what is the font size of the title?");
- **count**: how many elements of a type ("quantos botões tem?", "how many buttons are there?");
- **existence**: whether there is one ("tem rodapé?", "is there a footer?");
- **place**: where an element is ("onde está o botão?", "where is the button?");
- **why**: the explanation of the last thing done (its reading, and the path in the concept graph that gave the
  meaning of each word).

The answer is a structure (who, what, value) realized in the asker's language with that language's labels from the
builder's catalog; when the document does not say (a property never set), the answer says so rather than inventing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import langs, lexicon
from .values import fold

INTERROGATIVES = {
    "pt": {"what": {"que", "o que", "qual", "quais"}, "count": {"quantos", "quantas", "quanto"},
           "where": {"onde"}, "why": {"por que", "porque", "por quê"}, "exist": {"tem", "existe", "há", "ha"}},
    "en": {"what": {"what", "which"}, "count": {"how many", "how much"}, "where": {"where"},
           "why": {"why"}, "exist": {"is there", "are there", "does", "do", "is", "are", "has", "have"}},
}
CONTENT_WORDS = {"pt": {"tem", "contém", "contem", "há", "ha", "dentro", "existe"},
                 "en": {"in", "inside", "contain", "contains", "there", "on"}}


@dataclass
class AnswerText:
    kind: str
    text: str


def is_question(text: str, lang: str) -> bool:
    t = text.strip().lower()
    if t.endswith("?"):
        return True
    first = " ".join(re.findall(r"[\wÀ-ÿ]+", t)[:2])
    return any(first.startswith(w) for ws in INTERROGATIVES[lang].values() for w in ws if w not in ("tem", "is", "do",
                                                                                                  "does", "are"))


def _kind(text: str, lang: str) -> str:
    t = " " + " ".join(re.findall(r"[\wÀ-ÿ]+", text.lower())) + " "
    q = INTERROGATIVES[lang]
    for kind in ("why", "count", "where"):
        if any(f" {w} " in t for w in q[kind]):
            return kind
    words = t.split()
    if words and words[0] in q["exist"] or " ".join(words[:2]) in q["exist"]:
        return "exist"
    return "what"


def _label(kind: str, id_: str) -> str:
    for e in lexicon.load():
        if e.kind == kind and e.id == id_:
            return e.label
    return id_


def _name(world, nid: str) -> str:
    n = world.nodes[nid]
    return f"{_label('tipo', n['type']).lower()} «{n['name']}»" if n["name"] else _label("tipo", n["type"]).lower()


def _style(doc_nodes: dict, nid: str, prop: str, layer=("desktop", "base")):
    styles = doc_nodes[nid].get("styles") or {}
    return ((styles.get(layer[0]) or {}).get(layer[1]) or {}).get(prop)


def _say(lang: str, pt: str, en: str) -> str:
    return en if lang == "en" else pt


def answer(text: str, world, doc: dict, last=None) -> AnswerText | None:
    """The answer to a question about the page, or None when the text is not such a question."""
    lang = langs.detect(text)
    with langs.use(lang):
        if not is_question(text, lang):
            return None
        return _answer(text, world, doc, last, lang)


def _nodes(doc: dict) -> dict:
    out = {}

    def walk(n):
        out[n["id"]] = n
        for c in n.get("children", []):
            walk(c)

    for p in doc.get("pages", []):
        walk(p["tree"])
    return out


def _answer(text: str, world, doc: dict, last, lang: str) -> AnswerText | None:
    from .understand import Piece, _pieces, _predicate, _reference, _span_match, analyse

    kind = _kind(text, lang)
    if kind == "why":
        if last is None:
            return AnswerText("why", _say(lang, "Ainda não fiz nada nesta conversa.", "I have not done anything yet."))
        steps = "; ".join(getattr(last, "assumptions", []) or [])
        if not steps:
            return AnswerText("why", _say(lang, f"Fiz «{last.paraphrase}»: era o sentido direto das palavras do pedido.",
                                          f"I did «{last.paraphrase}»: it was what the words of the request said."))
        return AnswerText("why", _say(lang, f"Fiz «{last.paraphrase}». Como entendi: {steps}.",
                                      f"I did «{last.paraphrase}». How I understood it: {steps}."))
    tokens = analyse(re.sub(r"\?+\s*$", "", text))
    words = [t for t in tokens if t.upos != "PUNCT"]
    if not words:
        return None
    # the parts of the question: everything is an argument (there is no request verb)
    pred = _predicate(tokens) or words[0]
    pieces = _pieces(tokens, pred) or [Piece((), words)]
    nodes = _nodes(doc)
    # the element asked about: the first phrase that refers to one
    target, prop = None, None
    for k, p in enumerate(pieces):
        span = _span_match(pieces, k, {"propriedade", "campo"}) if not p.case or k == 0 else None
        if span is not None and prop is None:
            prop = span[0]
            continue
        ref = _reference(p, world)[0] if p.words else []
        if len(ref) == 1 and target is None:
            target = ref[0]
    if kind == "count" or kind == "exist":
        typ = _type_asked(tokens)
        if typ is None:
            return None
        found = [n for n, v in world.nodes.items() if v["type"] == typ]
        label = _label("tipo", typ).lower()
        if kind == "count":
            return AnswerText("count", _say(lang, f"Há {len(found)} {label}(s) na página.",
                                            f"There are {len(found)} {label}(s) on the page."))
        if found:
            names = ", ".join(f"«{world.nodes[n]['name']}»" for n in found[:6])
            return AnswerText("exist", _say(lang, f"Sim: {names}.", f"Yes: {names}."))
        return AnswerText("exist", _say(lang, f"Não há {label} na página.", f"There is no {label} on the page."))
    if kind == "where":
        if target is None:
            return None
        parent = world.nodes[target]["parent"]
        if parent is None:
            return AnswerText("where", _say(lang, f"{_name(world, target)} é a página.", f"{_name(world, target)} is the page."))
        pos = world.nodes[parent]["children"].index(target) + 1
        return AnswerText("where", _say(lang, f"{_name(world, target)} está em {_name(world, parent)}, na posição {pos}.",
                                        f"{_name(world, target)} is in {_name(world, parent)}, at position {pos}."))
    # what: a property or the text of an element, else its content
    if prop is not None and target is not None:
        if prop.kind == "campo" or prop.id in ("text", "texto"):
            value = nodes[target].get("text")
        else:
            value = _style(nodes, target, prop.id)
        if value is None:
            return AnswerText("value", _say(lang, f"{prop.label} de {_name(world, target)} não foi definido "
                                                  f"(vale o padrão do builder).",
                                            f"The {prop.label.lower()} of {_name(world, target)} is not set "
                                            f"(the builder's default applies)."))
        return AnswerText("value", _say(lang, f"{prop.label} de {_name(world, target)}: {value}.",
                                        f"The {prop.label.lower()} of {_name(world, target)} is {value}."))
    family = _family_asked(pieces)
    if family is not None and target is not None:
        from .understand import _prior

        props = sorted(family, key=lambda p: _prior(p, world.nodes[target]["type"]))
        prop_id = props[0]
        value = _style(nodes, target, prop_id)
        label = _label("propriedade", prop_id)
        if value is None:
            return AnswerText("value", _say(lang, f"{label} de {_name(world, target)} não foi definido "
                                                  f"(vale o padrão do builder).",
                                            f"The {label.lower()} of {_name(world, target)} is not set "
                                            f"(the builder's default applies)."))
        return AnswerText("value", _say(lang, f"{label} de {_name(world, target)}: {value}.",
                                        f"The {label.lower()} of {_name(world, target)} is {value}."))
    container = target or next((n for n, v in world.nodes.items() if v["parent"] is None), None)
    if container is None:
        return None
    kids = world.nodes[container]["children"]
    if not kids:
        text_value = nodes[container].get("text")
        if text_value:
            return AnswerText("content", _say(lang, f"{_name(world, container)} tem o texto «{text_value}».",
                                              f"{_name(world, container)} has the text «{text_value}»."))
        return AnswerText("content", _say(lang, f"{_name(world, container)} está vazio.",
                                          f"{_name(world, container)} is empty."))
    items = ", ".join(_name(world, k) + (f" («{nodes[k]['text']}»)" if nodes[k].get("text") else "") for k in kids)
    return AnswerText("content", _say(lang, f"{_name(world, container)} tem: {items}.",
                                      f"{_name(world, container)} has: {items}."))


def _type_asked(tokens) -> str | None:
    """The type a count or existence question is about: the first noun naming a type that is not inside a place
    phrase ("quantos títulos tem na página?" counts titles, not pages)."""
    from . import grounding

    for k, t in enumerate(tokens):
        if t.upos not in ("NOUN", "PROPN") or (k > 0 and tokens[k - 1].upos in ("ADP",)) or                 (k > 1 and tokens[k - 2].upos == "ADP" and tokens[k - 1].upos == "DET"):
            continue
        hits = lexicon.match((lexicon.lemma_of(t.form),), {"tipo"})
        if hits:
            return hits[0][0].id
        hit = next((m for m in grounding.meanings(t.form, "N") if m.kind == "tipo" and m.cost <= 1.0), None)
        if hit is not None:
            return hit.target
    return None


def _family_asked(pieces):
    from . import grounding
    from .values import _builder_properties

    types = _builder_properties()
    for p in pieces:
        for t in p.words:
            fam = next((m.target for m in grounding.direct(t.form) if m.kind == "familia"), None)
            if fam is not None:
                return [pid for pid, info in types.items() if info.get("valueType") == fam]
    return None
