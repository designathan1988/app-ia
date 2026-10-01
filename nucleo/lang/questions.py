"""Questions about the page, answered from the document, in the language they were asked in.

A question is recognized by its form (a question mark, or an interrogative word of the language: closed-class
grammar in ``langs``). Its content is grounded by the same machinery as requests: the element it is about
over its logical form (``ground``: the element, the property with its owner, the type).

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
    from . import alternatives
    from . import ground as gr
    from . import logic_form as lf

    analysis = alternatives.analyses(re.sub(r"\?+\s*$", "", text))
    if not analysis:
        return None
    tokens = analysis[0].tokens
    words = [t for t in tokens if t.upos != "PUNCT"]
    if not words:
        return None
    nodes = _nodes(doc)
    # what the question is about, grounded the same way as requests: the property asked (with its owner) and the
    # element asked about, over the phrases of the question's logical form
    mentions = _question_mentions(lf.build(tokens), tokens)
    target, options = None, []  # options: (den cost, kind, property ids) of the property asked
    for m in mentions:
        for d in gr.properties(m, world):
            if d.kind not in ("prop", "field"):
                continue
            kind_, pid, owner = d.data[0], d.data[1], d.data[2]
            if kind_ in ("propriedade", "campo"):
                options.append((d.cost, kind_, [pid]))
            elif kind_ in ("lista", "familia"):
                from .values import _builder_properties

                ids = list(pid) if kind_ == "lista" else                     [q for q, info in _builder_properties().items() if info.get("valueType") == pid]
                options.append((d.cost, "propriedade", ids))
            if owner is not None and len(owner.data) == 1 and target is None:
                target = owner.data[0]
    if target is None:
        # the element asked about: the phrase that refers to one most directly (cheapest), whatever its position
        found = [(r.cost, k, r.data[0]) for k, m in enumerate(mentions) for r in gr.references(m, world)[:1]
                 if len(r.data) == 1]
        if found:
            target = min(found)[2]
    wh = _has_wh(tokens, lang)
    if not wh and kind in ("what", "exist"):
        # a yes/no question about a state ("o título está centralizado?", "is the button bold?"): the state the
        # sentence would assert, read by the request engine, checked against the document
        polar = _polar(text, world, nodes, lang)
        if polar is not None:
            return polar
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
    if options and target is not None:
        from .base import _prior

        ntype = world.nodes[target]["type"]
        ranked = []
        for cost, kind_, ids in options:
            for pid in ids:
                if kind_ == "campo" or pid in ("text", "texto"):
                    value = nodes[target].get("text")
                    ranked.append((value is None, 0.0, cost, "campo", pid, value))
                else:
                    value = _style(nodes, target, pid)
                    # (the property this element most likely means, and one it has set before one it has not)
                    ranked.append((value is None, _prior(pid, ntype), cost, "propriedade", pid, value))
        ranked.sort(key=lambda r: r[:3])
        _, _, _, kind_, pid, value = ranked[0]
        label = SimpleProp(kind_, pid).label
        if value is None:
            return AnswerText("value", _say(lang, f"{label} de {_name(world, target)}: não definido "
                                                  f"(vale o padrão do builder).",
                                            f"The {label.lower()} of {_name(world, target)} is not set "
                                            f"(the builder's default applies)."))
        return AnswerText("value", _say(lang, f"{label} de {_name(world, target)}: {value}.",
                                        f"The {label.lower()} of {_name(world, target)} is {value}."))
    # (the content of the element asked about; with no element of the page in the question, it is not a question
    # about the page: "o que faz a função createStore?" is for the code)
    container = target
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


def _has_wh(tokens, lang: str) -> bool:
    """Whether the question has an interrogative word asking for something ("qual", "o que", "what", "where"): a
    question without one asks yes or no."""
    words = " " + " ".join(fold(t.form.lower()) for t in tokens) + " "
    q = INTERROGATIVES[lang]
    return any(f" {fold(w)} " in words for kind in ("what", "count", "where", "why") for w in q[kind])


def _polar(text: str, world, nodes: dict, lang: str) -> AnswerText | None:
    """Yes or no: the states the question's sentence states (as the request engine reads it), each compared with
    the document. None when the sentence states no style (then it is not this kind of question)."""
    from . import interpret

    its = interpret.interpretations(re.sub(r"\?+\s*$", "", text), world)
    if not its or its[0].cost > interpret.u_limit():
        return None
    best = its[0]
    cons = list(best.constraints) + [c for f in best.facts for c in f.constraints]
    if not cons or any(c["kind"] != "style" or c["id"] not in nodes for c in cons):
        return None
    yes, parts = True, []
    for c in cons:
        have = _style(nodes, c["id"], c["property"], (c["breakpoint"], c["state"]))
        label = _label("propriedade", c["property"])
        label = label[:1].lower() + label[1:]
        if have is None:
            yes = False
            parts.append(_say(lang, f"{label} de {_name(world, c['id'])}: não definido (vale o padrão do builder)",
                              f"the {label.lower()} of {_name(world, c['id'])} is not set (the builder's default "
                              f"applies)"))
            continue
        same = fold(str(have).lower()) == fold(str(c["value"]).lower())
        yes = yes and same
        parts.append(_say(lang, f"{label} de {_name(world, c['id'])}: {have}",
                          f"the {label.lower()} of {_name(world, c['id'])} is {have}"))
    word = _say(lang, "Sim" if yes else "Não", "Yes" if yes else "No")
    return AnswerText("polar", f"{word}: " + "; ".join(parts) + ".")


@dataclass
class SimpleProp:
    kind: str  # propriedade | campo
    id: str

    @property
    def label(self) -> str:
        return _label("propriedade" if self.kind == "propriedade" else "campo", self.id)


def _question_mentions(sentence, tokens) -> list:
    """The phrases of a question, in order: every mention of its predicates' roles (and of nested predicates), and
    the predicate head itself when it is a noun ("qual a cor do título?")."""
    from . import logic_form as lf

    out = []

    def visit(p):
        if p.head.upos in ("NOUN", "PROPN"):
            kids = {}
            for t in tokens:
                kids.setdefault(t.head, []).append(t)
            out.append(lf.mention(p.head, kids))
        for r, w, x in p.roles:
            if isinstance(x, lf.Mention):
                out.append(x)
            elif isinstance(x, lf.Predicate):
                visit(x)

    for p in sentence.predicates:
        visit(p)
    # with the phrases attached to them, at any depth ("o que tem na seção Topo?" however it was parsed)
    full, stack = [], list(out)
    while stack:
        m = stack.pop(0)
        full.append(m)
        stack = [x for _, x in m.attached] + list(m.conj) + stack
    return full


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
