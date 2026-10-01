"""C3 (docs/plano_compreensao.md §3.3, §5a): what state of the document makes the logical form true.

For each alternative analysis of the sentence (``alternatives``) and each of its predicates (``logic_form``), the
kinds of state the machine can reach are filled from the **typed denotations** of the predicate's arguments
(``ground``):

- ``style(E, P, V)``: a value (a named value, a literal, a measure, or the verb's own value) whose property is the
  one said (a property mention) or the value's own; on the element said (the property's owner, the theme, or the
  place the value goes to). The value must fit the property (W3C grammar).
- ``command(E, C)``: the verb names a builder command (with the rest of its label said).
- ``added(T, place)``, ``removed(E)``, ``moved(E, place)``.
- ``field(E, text | name, literal)``.

The verb is evidence (a cost per kind of state), not a gate. Every word with a meaning that the reading leaves
unused costs; an analysis costs its edits. The cheapest reading over all analyses is the interpretation; a rival
with a different effect at almost the same cost makes it a question.

The output is the same goal constraints the planner already takes (``understand.Reading``).
"""

from __future__ import annotations

import itertools
import pathlib
from dataclasses import dataclass, field

from . import alternatives, grounding, langs, lexicon
from . import ground as gr
from . import logic_form as lf
from .tokenize import is_literal
from .values import fold

RIVAL_MARGIN = 1.0
UNLIKELY = 2.0  # a property this improbable for the element, reached by one clue only, is confirmed first
CONSTRUCTION = 1.5  # a meaning the construction gives, not the verb (caused motion, insertion): Goldberg
MEANINGFUL_UNUSED = 4.5  # a word with a meaning that the reading ignores: never executed silently
UNUSED = 0.5  # a word that grounds to nothing


def _u():
    from . import understand

    return understand


@dataclass
class Cand:
    state: str
    constraints: list
    cost: float
    explained: set
    notes: list = field(default_factory=list)
    ambiguous: list = field(default_factory=list)
    unknown_verb: bool = False
    ask_value: tuple | None = None  # (node, property): a change of amount with no current value to start from
    uncertain: bool = False  # one weak clue only (a value named by the verb alone, for an unlikely property)
    parts: dict = field(default_factory=dict)  # where the cost comes from (to explain a reading)


# -- the arguments ------------------------------------------------------------------------------------------------
@dataclass
class Arg:
    role: str
    case: str
    mention: lf.Mention
    dens: list

    def of(self, *kinds):
        return [d for d in self.dens if d.kind in kinds]


def _args(p: lf.Predicate, world, particles=frozenset()) -> list[Arg]:
    out = []
    for r, c, x in p.roles:
        if isinstance(x, lf.Mention):
            ds = [d for d in gr.ground(x, world) + gr.place(c, x, world) if not d.words & particles]
            out.append(Arg(r, c, x, ds))
    return out


def _themes(p: lf.Predicate, args: list[Arg], ctx: "Context | None" = None) -> list[tuple[Arg, gr.Den]]:
    """The element(s) the predicate is about: the object of an event, else its subject (a copular, obligation or
    passive clause: "o botão tem que ficar verde"); with none said, the element the discourse made salient."""
    out = _said_themes(p, args)
    # (the element the discourse made salient stands for an element the clause does not say: never for one it says
    # but that was not found, "duplicate the card" with no card is not the last element)
    said = any(a.role in ("obj", "subj", "iobj") and a.mention is not None and a.mention.det != "pronoun"
               and not is_literal(a.mention.head.form) and not a.of("val", "lit", "measure", "cmp", "prop", "field")
               for a in args)  # (a value said as the object, "coloca 36px", names no element)
    if not out and ctx is not None and ctx.salient and not said:
        out = [(Arg("contexto", "", None, []), gr.Den("ref", tuple(ctx.salient), CONTEXT_COST, frozenset(),
                                                       ("pelo contexto",)))]
    return out


def _said_themes(p: lf.Predicate, args: list[Arg]) -> list[tuple[Arg, gr.Den]]:
    out = []
    # (the recipient of a giving verb is what the state is about: "give the section a white background")
    for role in ("iobj", "obj", "subj"):
        for a in args:
            if a.role == role and a.case == "" or a.role == role and role == "subj":
                out += [(a, d) for d in a.of("ref")]
        if out:
            return out
    return out


def _value_case(case: str) -> bool:
    from .understand import FRAMES

    cw = lexicon.lemma_seq(case) if case else ()
    return not cw or cw[-1] in {fold(x) for x in FRAMES["valor_casos"]}


def _case_tokens(m: lf.Mention) -> set:
    if m is None:
        return set()
    case = {t.i for t in m.words if t.upos == "ADP" and t.head == m.head.i and
            t.deprel.split(":")[0] in ("case", "mark") and not _open_class(t)}
    return case | {t.i for t in m.words if t.head in case and t.deprel.split(":")[0] == "fixed"}


@dataclass
class Context:
    """What the discourse so far makes salient (DRT, plan §3.1 "Textos"): the element last acted on or mentioned
    (for "ele", "it", and for a request that does not say its element), and the property last talked about (for
    "o título tá pequeno, coloca 36px")."""
    salient: tuple = ()
    topic_prop: tuple | None = None
    new_count: int = 0
    created: tuple = ()  # (id, node) of the elements earlier clauses created: they exist for the later ones


CONTEXT_COST = 0.5  # an element or property taken from the discourse, not said in the clause


# -- the kinds of state -----------------------------------------------------------------------------------------
def _style(p, args, ev, world, ctx=None, tokens=()) -> list[Cand]:
    u = _u()
    from .values import _builder_properties

    builder = _builder_properties()
    values_ = [(a, d) for a in args for d in a.of("val", "lit", "measure", "cmp")
               if a.role in ("result", "attr", "obj", "obl", "adv") and (_value_case(a.case) or a.role != "obl")]
    if ev.cmp:
        values_.append((None, gr.Den("cmp", ev.cmp, 0.0, frozenset({p.head.i}))))
    for pr in ev.pairs:
        values_.append((None, gr.Den("val", (pr,), 0.0, frozenset({p.head.i}))))
    # a property said, or the text of an element ("o texto do botão branco": the owner's text); with none said,
    # the property the discourse is about ("o título tá pequeno, coloca 36px")
    topic = [(None, gr.Den("prop", ctx.topic_prop + (None,), CONTEXT_COST, frozenset(), ("pelo contexto",)))] \
        if ctx is not None and ctx.topic_prop and not any(a.of("prop") for a in args) else []
    props = topic + [(a, d) for a in args for d in a.of("prop")] + \
        [(a, d) for a in args for d in a.of("field") if d.data[1] == "text" and d.data[2] is not None] + \
        _surface_labels(args, tokens, world) + [(None, None)]
    themes = _themes(p, args, ctx)
    places = [(a, d) for a in args for d in a.of("place") if d.data[0] == "dentro"]
    out = []
    names = {(n.get("name") or "").lower() for n in world.nodes.values()}
    # a bare word that is a keyword of the property said is its value ("o user-select para none")
    keyword_values = []
    from .values import _keywords

    for pa, pd in props:
        if pd is None or pd.data[0] != "propriedade":
            continue
        kws = _keywords(pd.data[1])
        for a in args:
            if a.role not in ("result", "attr", "obj", "obl", "adv") or a.role == "obl" and not _value_case(a.case):
                continue
            for t in a.mention.words if a.mention is not None else []:
                if t.i not in pd.words and fold(t.form.lower()) in kws and not is_literal(t.form):
                    keyword_values.append((a, gr.Den("val", ((pd.data[1], t.form.lower()),), 0.0, frozenset({t.i}))))
    for (va, v), (pa, pd) in itertools.product(values_ + keyword_values, props):
        if pd is not None and (v.words & pd.words) and v.kind != "measure":
            continue
        if v.kind == "lit" and isinstance(v.data, str) and v.data.lower() in names:
            # the name of an element of the page refers to it: read as a text value it costs (DRT)
            v = gr.Den(v.kind, v.data, v.cost + 2.0, v.words, v.notes)
        owner = pd.data[2] if pd is not None else None
        if owner is not None:
            targets = [(pa, owner)]
        else:
            sides = langs.profile().get("sides", {})
            sided_places = [(a, d) for a in args for d in a.of("place") if d.data[0] in sides]
            targets = [(a, d) for a, d in themes if a is not va] + [(a, d) for a, d in places if a is not va] + \
                [(a, d) for a, d in sided_places if a is not va]
        for ta, t in targets:
            if t.words & v.words:
                continue
            nodes = list(t.data[1]) if t.kind == "place" else list(t.data)
            ntype = world.nodes[nodes[0]]["type"]
            options = []  # (prop, value, cost)
            said = pd.data[:2] if pd is not None and pd.kind == "prop" else None
            v_lit = None
            if v.kind == "measure":
                # (the property said by its full label wins over the measure's own head word: "altura mínima de
                # 200px" is min-height; the measure gives the literal)
                said, v_lit = (said if said is not None else v.data[:2]), v.data[2]
            if v.kind == "val":
                for prop, value in v.data:
                    if said is not None:
                        kind, pid = said
                        if kind == "familia" and builder.get(prop, {}).get("valueType") != pid:
                            continue
                        if kind == "lista" and prop not in pid:
                            continue
                        if kind not in ("familia", "lista") and prop != pid:
                            continue
                    options.append((prop, value, u._prior(prop, ntype)))
            elif v.kind in ("lit", "measure") and said is not None:
                lit = v_lit if v.kind == "measure" else v.data
                options += _literal_options(said, lit, ntype)
            elif v.kind == "cmp":
                options += _comparative_options(said, ntype)
            if ev.props and any(q in ev.props for q, _, _ in options):
                # the verb's own meaning is about properties ("alinhar", "align": alignment): one of them, whatever
                # the element ("align the image to the right": its alignment, though an image is no text)
                options = [(q, val, min(c, 1.0)) for q, val, c in options if q in ev.props]
            side_words = _side_words(args, va, ta)
            if side_words and len({q for q, _, _ in options}) > 1:
                # a side said ("em cima do botão", "on top"): the property of that side
                sided = [o for o in options if _label_has(o[0], side_words[0])]
                if sided:
                    options = sided
                    explained_side = side_words[1]
                else:
                    explained_side = set()
            else:
                explained_side = set()
            # the machine can only reach what the builder has: a CSS shorthand it lacks ("padding", "font") is no
            # state it can set
            from .values import reachable

            if said is not None and said[0] == "atributo":
                options = [o for o in options if _attribute_ok(o[0], ntype, o[1])]
            else:
                options = [o for o in options if reachable(o[0])]
            if not options:
                continue
            best = min(c for _, _, c in options)
            chosen = [o for o in options if o[2] == best]
            prop, value, prior = chosen[0]
            if pd is not None and pd.data[0] == "propriedade" and pd.data[1] == prop:
                # the property was named: how likely it is for such an element only breaks ties
                prior = min(prior, 0.5)
            used = set(v.words) | (set(pd.words) if pd is not None else set())  # (a label word is not a layer)
            bp, st, layer_words = _layer(p, [x for x in tokens if x.i not in used], world)
            ask = None
            if v.kind == "cmp":
                value, ask = _scaled(world, nodes[0], prop, v.data)
            cons = [{"kind": "style", "id": n, "breakpoint": bp, "state": st, "property": prop,
                     "value": u._as_keyword(value, prop)} for n in nodes]
            if said is not None and said[0] == "atributo":
                # an HTML attribute said ("o id do parágrafo como 'note'"): the element's attributes
                cons = [{"kind": "field", "id": n, "field": "attributes", "value": {prop: value}} for n in nodes]
            explained = set(v.words) | set(t.words) | ({p.head.i} if "style" in ev.kinds else set()) | \
                ev.particles | explained_side | layer_words
            # (the owner's cost is already in the property said when the element is that owner)
            t_cost = 0.0 if owner is not None else t.cost
            cost = v.cost + t_cost + prior + ev.kinds.get("style", 9.0)
            if pd is not None:
                explained |= set(pd.words)
                cost += pd.cost
            for a in (va, ta, pa):
                if a is not None:
                    explained |= _case_tokens(a.mention)
            notes = list(t.notes)
            if len({o[0] for o in chosen}) > 1:
                cost += 0.5
                notes.append("várias propriedades possíveis")
            # coordinated values ("em negrito e itálico", "bold and italic"): each one on the same element
            if va is not None:
                for c2 in va.mention.conj:
                    for v2 in gr.values(c2):
                        if v2.kind != "val":
                            continue
                        opts2 = [(q, val, u._prior(q, ntype)) for q, val in v2.data]
                        q, val, _ = min(opts2, key=lambda o: o[2])
                        cons += [{"kind": "style", "id": n, "breakpoint": bp, "state": st, "property": q,
                                  "value": u._as_keyword(val, q)} for n in nodes]
                        explained |= set(v2.words) | {t.i for t in va.mention.words if t.upos == "CCONJ"}
                        break
            c = Cand("style", [] if ask else cons, cost, explained, notes, list(nodes) if t.ambiguous else [])
            c.ask_value = ask
            # a value named only by the verb ("arredondar": arredondado = round) for a property unlikely on this
            # element is a single weak clue: confirmed before it is done
            c.uncertain = va is None and v.kind == "val" and prior >= UNLIKELY
            c.parts = {"valor": v.cost, "alvo": t_cost, "propriedade_a_priori": prior,
                       "verbo": ev.kinds.get("style", 9.0), "propriedade_dita": pd.cost if pd is not None else 0.0,
                       "varias": cost - (v.cost + t_cost + prior + ev.kinds.get("style", 9.0) +
                                         (pd.cost if pd is not None else 0.0))}
            c.sources = {"valor": (v.kind, sorted(v.words)), "propriedade": (pd.data[:2] if pd is not None else None),
                         "alvo": sorted(t.words)}  # (which words gave what: to explain the reading)
            out.append(c)
    return out


COMPARATIVE_STEP = 1.25  # one step of the usual type scale (a major third)
NUMERIC = ("length", "length-percentage", "number", "integer")


def _comparative_options(said, ntype) -> list:
    """The amount a comparative changes: the property said if it is an amount, else an amount whose label contains
    it ("a fonte maior": tamanho da fonte); with none said, the element's size (its text's size for a text
    element, its width otherwise)."""
    u = _u()
    from .values import _builder_properties

    builder = _builder_properties()
    if said is None:
        _, contents = u._property_facts()
        return [("font-size" if contents.get(ntype) == "text" else "width", None, 0.5)]
    kind, pid = said
    ids = list(pid) if kind == "lista" else [pid]
    out = [(q, None, u._prior(q, ntype)) for q in ids if builder.get(q, {}).get("valueType") in NUMERIC]
    if out:
        return out
    for q in ids:
        entry = next((e for e in lexicon.load() if e.kind == "propriedade" and e.id == q and e.lemmas != (q,)), None)
        if entry is None:
            continue
        n = len(entry.lemmas)
        out += [(e.id, None, u._prior(e.id, ntype) + 0.3) for e in lexicon.load()
                if e.kind == "propriedade" and e.id != q and builder.get(e.id, {}).get("valueType") in NUMERIC and
                any(e.lemmas[i:i + n] == entry.lemmas for i in range(len(e.lemmas) - n + 1))]
    return out


def _scaled(world, node, prop, direction):
    """The new value one step up or down from the element's current one; (None, (node, prop)) when the document
    does not say the current value (then the number is asked)."""
    import re

    current = ((world.nodes[node].get("styles") or {}).get(world.layer[0]) or {}).get(world.layer[1], {}).get(prop)
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)(px|rem|em|%)", str(current or ""))
    if m is None:
        return None, (node, prop)
    n, unit = float(m.group(1)), m.group(2)
    new = round(n * (COMPARATIVE_STEP if direction > 0 else 1 / COMPARATIVE_STEP), 2 if unit in ("rem", "em") else 0)
    return f"{int(new) if unit in ('px', '%') else new}{unit}", None


def _mentions(args) -> list:
    """Every mention of the clause's arguments, with the phrases attached to them."""
    out, stack = [], [a.mention for a in args if a.mention is not None]
    while stack:
        m = stack.pop(0)
        out.append(m)
        stack += [x for _, x in m.attached] + list(m.conj)
    return out


def _surface_labels(args, tokens, world) -> list:
    """Property labels said as contiguous words of the clause, whatever tree the parser built over them: a label is
    one lexical unit (a multiword expression), "quebra antes" is break-before even when "antes" was attached to
    the verb. The owner is the element named right after the label ("... do contêiner Actions")."""
    arts = langs.profile()["articles"]
    own = sorted((t for t in tokens if t.upos != "PUNCT" and fold(t.form.lower()) not in arts), key=lambda t: t.i)
    seq = tuple(lexicon.lemma_of(t.form) for t in own)
    found = []
    for k in range(len(seq)):
        for e, n in lexicon.match(seq, {"propriedade"}, k):
            if e.lemmas == (e.id,) or n < 2 and own[k].upos != "VERB":
                # (one word, or a CSS name: the tree's own grounding covers it - unless the parser took the word
                # for a verb: a label that is an infinitive, "o flutuar", "o limpar flutuação")
                continue
            span = own[k:k + n]
            ws = frozenset(t.i for t in span)
            if n > 1 and sum(1 for t in span if t.head not in ws) < 2:
                continue  # one word of the span dominates the rest: the tree kept the label as a phrase
            after = [m for m in _mentions(args) if m.head.i > span[-1].i and not ({t.i for t in m.words} & ws)]
            after.sort(key=lambda m: m.head.i)
            owner = next((r for m in after for r in gr.references(m, world)[:1]), None)
            if owner is None:
                continue
            words = ws | owner.words | {t.i for m in after[:1] for t in m.words if t.upos == "ADP"}
            found.append((Arg("rotulo", "", None, []), gr.Den("prop", ("propriedade", e.id, owner), owner.cost,
                                                                frozenset(words))))
            break
    return found


def _label_spans(tokens) -> list:
    """(properties, token indices) of every property named exactly by contiguous words: a catalog label (of one or
    more words) or a CSS identifier ("line-clamp"). A label inside a longer one ("fundo" in "cor de fundo") is
    the longer one's. A word can be the exact label of several properties: any of them is that word's use."""
    arts = langs.profile()["articles"]
    own = sorted((t for t in tokens if t.upos != "PUNCT" and fold(t.form.lower()) not in arts), key=lambda t: t.i)
    seq = tuple(lexicon.lemma_of(t.form) for t in own)
    found = []
    for k in range(len(seq)):
        from .values import index as value_index

        # exact labels only (a typing slip is not an exact naming: "mundo" is not "fundo"); a one-word CSS name like
        # "color" is said as a word; a word that is also a value ("esquerda": left, and text-align: left) is
        # not only a property's name
        hits = [(e, n) for e, n in lexicon.match(seq, {"propriedade"}, k)
                if (e.lemmas != (e.id,) or "-" in e.id) and tuple(seq[k:k + n]) in (e.lemmas, tuple(sorted(e.lemmas)))
                and not (n == 1 and value_index().get(fold(seq[k])))]
        if not hits:
            continue
        n = max(n for _, n in hits)
        ids = frozenset(e.id for e, m in hits if m == n)
        found.append((ids, frozenset(t.i for t in own[k:k + n])))
    return [(ids, ws) for ids, ws in found if not any(ws < other for _, other in found)]


def _label_contains(prop: str, said_ids) -> bool:
    """The property set has a label that contains one of the labels said ("tamanho da fonte" contains "fonte")."""
    labels = [e.lemmas for e in lexicon.load() if e.kind == "propriedade" and e.id in said_ids and e.lemmas != (e.id,)]
    own = [e.lemmas for e in lexicon.load() if e.kind == "propriedade" and e.id == prop]
    return any(len(l) < len(o) and any(o[i:i + len(l)] == l for i in range(len(o) - len(l) + 1))
               for l in labels for o in own)


LABEL_SPLIT = 2.0  # using the words of a multiword label apart (a lexical unit read as separate words)


def _layer(p: lf.Predicate, tokens, world) -> tuple:
    """The breakpoint and style state a change is for: catalog labels said anywhere in the clause ("ao passar o
    mouse", "no tablet", "no estado depois", "on hover"); (breakpoint, state, tokens explained)."""
    bp, st = world.layer
    ws = set()
    arts = langs.profile()["articles"]
    # (articles are not part of labels: "ao passar o mouse" is the label "Ao passar o mouse" without them)
    own = sorted((t for t in tokens if t.upos != "PUNCT" and fold(t.form.lower()) not in arts), key=lambda t: t.i)
    seq = tuple(lexicon.lemma_of(t.form) for t in own)
    k = 0
    while k < len(seq):
        hits = lexicon.match(seq, {"breakpoint", "estado"}, k)
        if not hits:
            k += 1
            continue
        e, n = hits[0]
        if e.kind == "breakpoint":
            bp = e.id
        else:
            st = e.id
        ws |= {t.i for t in own[k:k + n]}
        # the preposition and the common noun before the label ("no estado depois", "in the hover state")
        j = k - 1
        while j >= 0 and own[j].upos in ("ADP", "DET", "NOUN") and own[j].i not in ws and k - j <= 3:
            if own[j].upos == "NOUN" and lexicon.match((seq[j],), {"tipo", "propriedade"}):
                break
            ws.add(own[j].i)
            j -= 1
        k += n
    return bp, st, ws


def _side_words(args, va, ta):
    """The side a place phrase says ("em cima do", "on top of" -> the profile's word for that side: "superior",
    "top"), and the tokens it explains; the anchor of that place is the element."""
    sides = langs.profile().get("sides", {})
    for a in args:
        if a is va:
            continue
        for d in a.of("place"):
            if d.data[0] in sides:
                return sides[d.data[0]], set(d.words) | _case_tokens(a.mention)
    return None


def _label_has(prop: str, word: str) -> bool:
    lem = lexicon.lemma_of(word)
    return any(e.id == prop and (lem in e.lemmas or fold(word) in e.lemmas) for e in lexicon.load()
               if e.kind == "propriedade")


def _attribute_ok(attr: str, ntype: str, value) -> bool:
    """An HTML attribute can be given to this element (the manifest's "elements") with this value (its type):
    "cols" is a textarea's, and a number."""
    import json

    from ..builder.client import DEFAULT_BUILDER

    if "attrs" not in _ATTRS:
        path = pathlib.Path(DEFAULT_BUILDER) / "manifest" / "elements.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        _ATTRS["attrs"] = {a["html"]: a for a in data.get("attributes") or [] if isinstance(a, dict) and a.get("html")}
    a = _ATTRS["attrs"].get(attr)
    if a is None:
        return True
    elems = a.get("elements")
    if elems != "all" and isinstance(elems, list) and ntype not in elems:
        return False
    if a.get("valueType") in ("number", "integer"):
        return _u()._value_kind(str(value)) == "number"
    return True


_ATTRS: dict = {}


def _fits(prop: str, lit) -> bool:
    """A literal fits a property when the builder's declared type takes it or the W3C grammar does
    (line-height is declared a number, and its grammar also takes lengths)."""
    from .values import literal_kinds

    u = _u()
    return u._value_fits(prop, lit) or u._value_kind(lit) in literal_kinds(prop)


def _literal_options(said, lit, ntype) -> list:
    """The properties a literal can be the value of, given the property said: the property itself if the value fits
    it; for a family ("cor", "length"), its properties; and the properties whose label contains the one said and
    whose type takes this kind of value ("fonte" with 32px: "tamanho da fonte")."""
    u = _u()
    from .values import _builder_properties

    builder = _builder_properties()
    kind, pid = said
    out = []
    if kind == "lista":
        return [(q, lit, u._prior(q, ntype)) for q in pid if _fits(q, lit)]
    if kind == "familia":
        out += [(q, lit, u._prior(q, ntype)) for q, info in builder.items()
                if info.get("valueType") == pid and _fits(q, lit)]
        return out
    vtype = builder.get(pid, {}).get("valueType")
    from .values import literal_kinds

    kind_ = u._value_kind(lit)
    if kind_ == "other":
        takes = _fits(pid, lit)  # a function or a phrase ("oklab(...)", "blur(8px)"): the builder judges it
    else:
        takes = (kind_ in u.ACCEPTS.get(vtype, ()) if vtype in u.ACCEPTS else u._value_fits(pid, lit)) or \
            kind_ in literal_kinds(pid)
    if takes:
        out.append((pid, lit, u._prior(pid, ntype)))
    entry = next((e for e in lexicon.load() if e.kind == "propriedade" and e.id == pid and e.lemmas != (pid,)), None)
    if entry is not None:
        for e in lexicon.load():
            if e.kind != "propriedade" or e.id == pid or len(e.lemmas) <= len(entry.lemmas):
                continue
            n = len(entry.lemmas)
            if any(e.lemmas[i:i + n] == entry.lemmas for i in range(len(e.lemmas) - n + 1)) and \
                    u._value_kind(lit) in u.ACCEPTS.get(builder.get(e.id, {}).get("valueType"), ()):
                out.append((e.id, lit, u._prior(e.id, ntype) + 0.3))
    return out


def _same_frame(verb: str, ev) -> bool:
    """Whether a command's label verb is in a structural frame the sentence's verb also evokes (both move)."""
    u = _u()
    states = {gr.STATE_OF_FRAME.get(f["id"]) for f in u.FRAMES["quadros"] if u._in_frame(verb, f)}
    return bool(states & ({k for k, c in ev.kinds.items() if c < 1.0} - {"style", "command"}))


def _participle_lemma(t) -> str | None:
    if langs.current() == "en":
        return langs.english_lemma(t.form, "VERB") if t.form.lower().endswith(("ed", "en")) else None
    from .morph import analyses

    return next((lem for lem, tags in analyses(t.form.lower()) if tags.startswith("V+PTPST")), None)


def _commands(p, args, ev, world, sentence_lemmas, ctx=None) -> list[Cand]:
    from . import command_verbs
    from .builder_commands import FRAME_COMMANDS

    out = []
    sources = [(cv, {p.head.i} | set(ev.particles), ev.kinds.get("command", 9.0), None) for cv in ev.commands]
    # a moving verb with the rest of a moving command's label is that command ("leva o botão pra baixo": Mover
    # para baixo)
    for verbs in command_verbs.table().values():
        for cv in verbs:
            if cv.rest and cv not in ev.commands and cv.command not in FRAME_COMMANDS.values() and \
                    _same_frame(cv.verb, ev):
                sources.append((cv, {p.head.i}, 0.5, None))
    for a in args:
        # the state a command leaves, said as its participle ("deixa as imagens escondidas", "keep it hidden")
        if a.role in ("result", "attr") and a.mention.head.upos in ("VERB", "ADJ"):
            lem = _participle_lemma(a.mention.head)
            for cv in command_verbs.table().get(lem or "", []):
                if cv.command not in FRAME_COMMANDS.values() and not cv.rest:
                    sources.append((cv, {a.mention.head.i, p.head.i},
                                    0.0 if ev.light or "style" in ev.kinds else 1.0, None))
        # an action named by a noun, its theme in the "de/of" phrase ("faz uma cópia do botão", "make a copy of")
        if a.role == "obj" and a.mention.head.upos == "NOUN" and a.mention.det != "definite":
            for g in grounding.meanings(a.mention.head.form, "N"):
                if g.kind != "comando" or g.cost > 2.5:
                    continue
                for verbs in command_verbs.table().values():
                    for cv in verbs:
                        if cv.command == g.target and not cv.rest and cv.command not in FRAME_COMMANDS.values():
                            words = {a.mention.head.i, p.head.i} | {t.i for t in a.mention.words
                                                                    if t.upos in ("DET", "ADP")}
                            sources.append((cv, words, g.cost + 0.5, a.mention))
    seen = set()
    for cv, words, vcost, noun in sources:
        if (cv.command, noun is None) in seen:
            continue
        seen.add((cv.command, noun is None))
        if cv.rest and cv.command not in ev.whole and not set(cv.rest) <= set(sentence_lemmas.values()):
            continue
        rest_tokens = {i for i, lem in sentence_lemmas.items() if lem in cv.rest} if cv.rest else set()
        if noun is not None:
            themes = [(Arg("obl", c, x, []), d) for c, x in noun.attached for d in gr.references(x, world)]
        else:
            themes = _themes(p, args, ctx)
        for a, t in themes:
            cons = [{"kind": "command", "command": cv.command, "id": n, "label": cv.label,
                     "already": bool(cv.flag and world.nodes[n].get("flags", {}).get(cv.flag))} for n in t.data]
            out.append(Cand("command", cons, t.cost + vcost, set(t.words) | words | rest_tokens |
                            _case_tokens(a.mention), list(t.notes), list(t.data) if t.ambiguous else []))
    return out


def _structural(p, args, ev, world, ctx=None) -> list[Cand]:
    u = _u()
    out = []
    places = [(a, d) for a in args for d in a.of("place")]
    # added: a kind to create, where the sentence places it
    for a in args:
        if a.role not in ("obj", "subj"):
            continue
        for k in a.of("kind"):
            # where it goes: a place phrase of the clause, or one attached to the new thing itself ("um parágrafo
            # depois do título": the same place either way)
            own = [(Arg("obl", c, x, []), d) for c, x in (a.mention.attached if a.mention else []) for d in gr.place(c, x, world)]
            opts = [(pa, pd) for pa, pd in places if pa is not a] + own or [(None, None)]
            for pa, pd in opts:
                cost = k.cost + ev.kinds.get("added", CONSTRUCTION if ev.known and pd is not None else 9.0)
                explained = set(k.words) | {p.head.i}
                parent = index = None
                notes = []
                amb = []
                if pd is not None:
                    rel, anchors = pd.data
                    parent, index = u._placement(rel, anchors[0], world)
                    if parent is not None and not _takes_children(world.nodes.get(parent, {}).get("type")):
                        continue  # (an image, a paragraph of text: nothing goes inside them)
                    cost += pd.cost
                    explained |= set(pd.words) | _case_tokens(pa.mention)
                    amb = list(anchors) if pd.ambiguous else []
                else:
                    cost += u.COST["local_ausente"]
                    notes.append("sem local: onde o editor puser")
                if a.mention.det == "definite":
                    cost += u.COST["definido_com_referente"]
                extras, extra_words = _new_element_fields(a.mention, world)
                explained |= extra_words
                count = next((int(n.split("=")[1]) for n in k.notes if n.startswith("n=")), 1)
                out.append(Cand("added", [{"kind": "added", "type": k.data, "parent": parent, "index": index,
                                           **extras} for _ in range(count)],
                                cost, explained, notes, amb))
    for a, t in _themes(p, args, ctx):
        # removed
        out.append(Cand("removed", [{"kind": "removed", "id": n} for n in t.data],
                        t.cost + ev.kinds.get("removed", 9.0), set(t.words) | {p.head.i}, list(t.notes),
                        list(t.data) if t.ambiguous else []))
        # moved: to a place said by another phrase, or by one attached to the theme itself ("move the title below
        # the paragraph" either way)
        own = [(Arg("obl", c, x, []), d) for c, x in (a.mention.attached if a.mention else []) for d in gr.place(c, x, world)
               if not d.words & t.words]
        for pa, pd in places + own:
            if pa is a:
                continue
            rel, anchors = pd.data
            if any(n in anchors for n in t.data):
                continue
            cons = []
            for n in t.data:
                parent, index = u._placement(rel, anchors[0], world, moving=n)
                cons.append({"kind": "moved", "id": n, "parent": parent, "index": index})
            out.append(Cand("moved", cons, t.cost + pd.cost + ev.kinds.get("moved", CONSTRUCTION if ev.known else 9.0),
                            set(t.words) | set(pd.words) | {p.head.i} | _case_tokens(pa.mention), list(t.notes),
                            list(t.data) if t.ambiguous else list(anchors) if pd.ambiguous else []))
    return out


def _new_element_fields(m: lf.Mention, world) -> tuple[dict, set]:
    """The text and name a new element is given in its own phrase: a field word with a literal ("com o texto
    'X'", "with the text 'X'") or a naming participle with a literal ("chamado X", "named X")."""
    extras, words = {}, set()
    phrases, stack = [], list(m.attached)
    while stack:  # every phrase attached, at any depth ("com o nome X com o texto Y"), each with its own literal
        case, a = stack.pop(0)
        phrases.append((case, a))
        stack += a.attached
    for case, a in phrases:
        lits = [d for d in gr.values(a) if d.kind == "lit"] + \
            [d for _, b in a.attached for d in gr.values(b) if d.kind == "lit" and not b.attached and
             not any(d2.kind == "field" for d2 in gr.properties(b, world))]
        if not lits:
            continue
        lit = min(lits, key=lambda d: d.cost)
        field_said = [d for d in gr.properties(a, world) if d.kind == "field" and d.data[1] in ("text", "name")]
        if field_said:
            fid = field_said[0].data[1]
        else:
            # a participle that names ("chamado", "named"): the naming frame's verb
            ev = gr.verb_evidence(lf.Predicate(a.head, _participle_lemma(a.head) or a.head.lemma), None)
            fid = "name" if ev.kinds.get("field:name", 9.0) < 1.0 else None
        if fid and fid not in extras:
            extras[fid] = lit.data
            nested = {x.i for _, b in a.attached for x in b.words}
            words |= {t.i for t in a.words if t.i not in nested} | set(lit.words)
    return extras, words


_CONTENT: dict = {}


def _takes_children(etype) -> bool:
    """Whether elements of this type contain other elements (the manifest's content model)."""
    import json

    from ..builder.client import DEFAULT_BUILDER

    if not _CONTENT:
        data = json.loads((pathlib.Path(DEFAULT_BUILDER) / "manifest" / "elements.json").read_text(encoding="utf-8"))
        _CONTENT.update({e["id"]: e.get("content") for e in data["elements"]})
    if etype is None or etype not in _CONTENT or str(etype).startswith("$"):
        return True
    return _CONTENT[etype] == "children"


def _value_removal(p, args, ev, world) -> list[Cand]:
    """A removal whose object is a value, from an element ("tira o negrito do título", "remove the bold from the
    title"): the element's property goes back to its normal value."""
    u = _u()
    from .values import _builder_properties, _keywords

    if "removed" not in ev.kinds or ev.kinds["removed"] >= 4.0:
        return []
    out = []
    for a in args:
        if a.role not in ("obj", "result"):
            continue
        for v in a.of("val"):
            # the element it is taken from: a phrase attached to the value or to the clause ("de/from/of")
            sources = [(Arg("obl", c, x, []), r) for c, x in a.mention.attached for r in gr.references(x, world)]
            sources += [(b, r) for b in args if b is not a and b.role in ("obl", "adv") for r in b.of("ref")]
            for sa, t in sources:
                nodes = list(t.data)
                ntype = world.nodes[nodes[0]]["type"]
                props = [(prop, u._prior(prop, ntype)) for prop, _ in v.data if prop in _builder_properties()]
                if not props:
                    continue
                prop = min(props, key=lambda x: x[1])[0]
                reset = "normal" if "normal" in _keywords(prop) else "initial"
                bp, st = world.layer
                cons = [{"kind": "style", "id": n, "breakpoint": bp, "state": st, "property": prop, "value": reset}
                        for n in nodes]
                out.append(Cand("style", cons, v.cost + t.cost + ev.kinds["removed"] + min(props, key=lambda x: x[1])[1],
                                set(v.words) | set(t.words) | {p.head.i} | _case_tokens(sa.mention) |
                                _case_tokens(a.mention), list(t.notes), list(nodes) if t.ambiguous else []))
    return out


def _css_form(value) -> bool:
    """A literal with the form of a CSS value: a length, number or colour, or a CSS function ("skewY(5deg)",
    "blur(4px)"): a value by its form, so reading it as a text costs."""
    import re

    if not isinstance(value, str):
        return False
    if re.fullmatch(r"[a-zA-Z][\w-]*\(.*\)", value.strip()):
        return True
    return _u()._value_kind(value) in ("length", "number", "color") and not value.startswith(("'", '"'))


def _fields(p, args, ev, world, ctx=None) -> list[Cand]:
    out = []
    u = _u()
    # (an unquoted literal with the form of a CSS value, "36px", "#f00", is a value by its form: as a text it costs)
    lits = [(a, d if not _css_form(d.data) else gr.Den(d.kind, d.data, d.cost + 2.0, d.words, d.notes))
            for a in args for d in a.of("lit") if a.role in ("obj", "result", "attr", "obl", "content")
            and (a.role != "obl" or _value_case(a.case))]
    # a field said with its owner ("o texto do botão", "the button text", "o nome da foto")
    for a in args:
        for f in a.of("field"):
            fid = f.data[1]
            if fid not in ("text", "name"):
                continue
            owner = f.data[2]
            if owner is None:
                continue
            for la, lit in lits:
                if la is a or lit.words & f.words:
                    continue
                state = f"field:{fid}"
                if "texto com palavras de significado" in lit.notes:
                    # the field said is a text ("o texto do parágrafo para Olá mundo"): its words are the text
                    lit = gr.Den(lit.kind, lit.data, lit.cost - 2.0, lit.words)
                out.append(Cand(state, [{"kind": "field", "id": owner.data[0], "field": fid, "value": lit.data}],
                                f.cost + lit.cost + ev.kinds.get(state, 2.0),
                                set(f.words) | set(lit.words) | {p.head.i} | _case_tokens(a.mention) |
                                _case_tokens(la.mention), list(owner.notes),
                                list(owner.data) if owner.ambiguous else []))
    # a literal written on an element: the theme, or the place it goes to ("escreva X no parágrafo"; "the title
    # should say X")
    for state in ("field:text", "field:name"):
        if state not in ev.kinds or ev.kinds[state] >= 4.0:
            continue
        targets = _themes(p, args, ctx) + [(a, d) for a in args for d in a.of("place") if d.data[0] == "dentro"]
        # (a place attached to the text itself: "escreve X no botão" either way)
        targets += [(Arg("obl", c, x, []), d) for la, _ in lits for c, x in la.mention.attached
                    for d in gr.place(c, x, world) if d.data[0] == "dentro"]
        for (ta, t), (la, lit) in itertools.product(targets, lits):
            if la is ta or t.kind == "place" and la.role == "obl" or t.words & lit.words:
                continue
            node = t.data[0] if t.kind == "ref" else t.data[1][0]
            amb = list(t.data) if t.kind == "ref" and t.ambiguous else []
            out.append(Cand(state, [{"kind": "field", "id": node, "field": state.split(":")[1], "value": lit.data}],
                            t.cost + lit.cost + ev.kinds[state],
                            set(t.words) | set(lit.words) | {p.head.i} | _case_tokens(ta.mention) |
                            _case_tokens(la.mention), list(t.notes), amb))
    return out


# -- costs of what is left unexplained ----------------------------------------------------------------------------
def _content_tokens(p: lf.Predicate) -> set:
    toks = {p.head.i: p.head}
    for r, c, x in p.roles:
        if isinstance(x, lf.Mention):
            for t in x.words:
                toks[t.i] = t
        elif isinstance(x, lf.Predicate):
            sub = _content_tokens(x)
            toks.update({i: None for i in sub})
    # a pronoun is content too ("everything", "tudo", "isso" must refer to something), except the speech
    # participants as subjects ("could you...", "eu quero...")
    subjects = {x.head.i for r, _, x in p.roles if r == "subj" and isinstance(x, lf.Mention)}
    return {i for i, t in toks.items() if t is None or (t.upos in ("NOUN", "PROPN", "ADJ", "VERB", "ADV", "NUM", "X")
                                                         or is_literal(t.form)) and t.upos != "PRON"
            or t.upos == "PRON" and i not in subjects and t.deprel.split(":")[0] in ("obj", "obl", "nmod")
            and fold(t.form.lower()) not in langs.profile()["articles"]
            # (a preposition attaches as case, mark or fixed: one attached otherwise is a word to account for; and a
            # word the lexicon knows only as an open-class word is one, whatever the tagger said: "underline")
            or t.upos == "ADP" and (t.deprel.split(":")[0] not in ("case", "mark", "fixed", "compound")
                                    or _open_class(t))}


def _open_class(t) -> bool:
    from .alternatives import _closed_word, categories

    return bool(categories(t.form, langs.current())) and not _closed_word(t.form, langs.current())


def _meaningful(t) -> bool:
    return gr.meaningful(t)


def _unexplained(p, cand: Cand, tokens) -> tuple[float, list]:
    by_i = {t.i: t for t in tokens}
    cost, left = 0.0, []
    for i in _content_tokens(p) - cand.explained:
        t = by_i[i]
        if fold(t.form.lower()) in langs.profile()["new"] | langs.profile()["universal"]:
            continue
        m = _meaningful(t)
        cost += MEANINGFUL_UNUSED if m else UNUSED
        left.append(t.form)
    return cost, left


# -- the predicate and the sentence -------------------------------------------------------------------------------
def readings(p: lf.Predicate, world, tokens, ctx: Context | None = None) -> list[Cand]:
    ev = gr.verb_evidence(p, tokens)
    args = _args(p, world, ev.particles)
    for a in args:
        # the phrase whose preposition is part of the verb is its object ("get rid of the image")
        cases = {t.i for t in a.mention.words if t.head == a.mention.head.i and t.deprel.split(":")[0] in ("case", "mark")}
        if a.role in ("obl", "adv") and cases and cases <= set(ev.particles):
            a.role, a.case = "obj", ""
    lemmas = {t.i: lexicon.lemma_of(t.form) for t in tokens}
    lemmas.update({t.i: fold(t.lemma) for t in tokens if t.upos in ("VERB", "ADP", "ADV")})
    cands = _style(p, args, ev, world, ctx, tokens) + _commands(p, args, ev, world, lemmas, ctx) + \
        _structural(p, args, ev, world, ctx) + _fields(p, args, ev, world, ctx) + _value_removal(p, args, ev, world)
    # a causative ("faz o parágrafo sumir", "make the image disappear"): the caused event, its theme the causee
    for r, w, q in p.roles:
        if isinstance(q, lf.Predicate) and r in ("content", "result"):
            causee = [x for rl, _, x in p.roles if rl == "obj" and isinstance(x, lf.Mention)]
            q2 = lf.Predicate(q.head, q.lemma, q.kind, q.act, q.negated,
                              list(q.roles) + ([("obj", "", causee[0])] if causee and not q.role("obj") else []))
            for c in readings(q2, world, tokens, ctx):
                c.cost += 0.5
                c.explained |= {p.head.i}
                cands.append(c)
    spans = _label_spans(tokens)
    for c in cands:
        for ids, ws in spans:
            props = [k.get("property") for k in c.constraints] + ([c.ask_value[1]] if c.ask_value else [])
            fields = [k.get("field") for k in c.constraints if k.get("kind") == "field"]
            if c.explained & ws and not fields and not any(q in ids or _label_contains(q, ids) for q in props if q):
                c.cost += LABEL_SPLIT
                c.notes.append("rótulo partido")
                c.parts["rotulo_partido"] = LABEL_SPLIT
    for c in cands:
        c.explained |= set(ev.particles)  # the particle is part of the verb ("jogar fora", "get rid of")
        extra, left = _unexplained(p, c, tokens)
        c.cost += extra
        c.parts["nao_usado"] = extra
        if left:
            c.notes.append("não usado: " + ", ".join(left))
        c.unknown_verb = not ev.known
    return sorted(cands, key=lambda c: c.cost)


@dataclass
class Interpretation:
    cost: float
    constraints: list
    cands: list
    analysis: object
    sentence: object
    act: str
    context: Context = None
    facts: list = field(default_factory=list)  # what assertions stated (not done)


def _courtesy(p: lf.Predicate, tokens) -> bool:
    """A clause that is talk, not a request ("me faz um favor", "por favor", "thanks"): no word but its verb means
    anything to the machine."""
    by_i = {t.i: t for t in tokens}
    ev = gr.verb_evidence(p, tokens)
    # (a value reached only through a synonym, "valer" ~ "anular": none, is no specific meaning of the verb)
    specific = ev.commands or ev.pairs and ev.kinds.get("style", 9.0) < 1.0 or ev.props or ev.cmp or         any(k in ev.kinds and ev.kinds[k] < 1.0 for k in ("added", "removed", "moved", "command"))
    return not specific and not any(_meaningful(by_i[i]) for i in _content_tokens(p) if i != p.head.i and i in by_i)


def _world_with(world, ctx: Context):
    """The page as the discourse leaves it: elements created by earlier clauses exist (as placeholders) and the
    salient element is the one a pronoun points to."""
    from .understand import World

    nodes = dict(world.nodes)
    nodes.update(dict(ctx.created))
    return World(nodes, list(ctx.salient) or list(world.selection), world.layer)


def _after(cands: list, ctx: Context, world) -> Context:
    """The discourse after a clause: what it acted on is salient; an element it created exists from now on."""
    salient, topic, n, created = ctx.salient, ctx.topic_prop, ctx.new_count, ctx.created
    for c in cands:
        for k in c.constraints:
            if k["kind"] == "added":
                n += 1
                nid = f"$novo{n}"
                node = {"name": k.get("name"), "type": k["type"], "parent": k.get("parent"), "index": 0,
                        "children": [], "flags": {}, "styles": {}}
                world.nodes[nid] = node
                created = created + ((nid, node),)
                salient = (nid,)
            elif k.get("id"):
                salient = (k["id"],)
            if k["kind"] == "style":
                topic = ("propriedade", k["property"])
    return Context(salient, topic, n, created)


def interpretations(text: str, world, ctx: Context | None = None, courtesy: bool = False) -> list[Interpretation]:
    """The readings of a sentence, cheapest first. With `courtesy`, a clause that is only talk ("me faz um favor")
    is an empty reading (used for the parts of a sentence split at its commas)."""
    ctx = ctx or Context()
    out = []
    best = None
    for a in alternatives.analyses(text):
        # branch and bound: a reading never costs less than its analysis; once the analyses cost more than the best
        # reading plus the rival margin, none of them can win or rival it (the result is the same as reading all)
        if best is not None and a.cost > best + RIVAL_MARGIN:
            break
        s = lf.build(a.tokens)
        if not s.predicates:
            continue
        w = _world_with(world, ctx)
        total, cons, chosen, facts = a.cost, [], [], []
        local = ctx
        ok = True
        for p in s.predicates:
            rs = readings(p, w, a.tokens, local)
            if p.act == "assertion":
                # information: what it says is noted, and what it is about becomes the topic; nothing is done
                # (it pays for what it leaves ungrounded, as a request does: information is not a cheaper way out)
                if rs:
                    facts.append(rs[0])
                    total += rs[0].cost
                    local = _after([rs[0]], local, w)
                else:
                    total += u_limit()
                continue
            if not rs or rs[0].cost > u_limit():
                if _courtesy(p, a.tokens):
                    # talk around the request: left out, at the cost of its words unused
                    total += UNUSED * len(_content_tokens(p))
                    continue
            if not rs:
                ok = False
                break
            total += rs[0].cost
            cons += rs[0].constraints
            chosen.append(rs[0])
            local = _after([rs[0]], local, w)
            w = _world_with(w, local)
        # words of the sentence that no predicate covers (an analysis that hung a phrase outside every clause)
        covered = set().union(*(_content_tokens(p) for p in s.predicates)) if s.predicates else set()
        for t in a.tokens:
            if t.i in covered or t.upos == "PRON" or t.i in {q.head.i for q in s.predicates}:
                continue
            if t.upos in ("NOUN", "PROPN", "ADJ", "VERB", "ADV", "NUM", "X") or is_literal(t.form):
                total += MEANINGFUL_UNUSED if _meaningful(t) else UNUSED
        if ok and (chosen or facts):
            best = total if best is None else min(best, total)
            out.append(Interpretation(total, cons, chosen, a, s,
                                      "assertion" if facts and not chosen else s.predicates[0].act, local, facts))
        elif ok and courtesy:
            out.append(Interpretation(total, [], [], a, s, "courtesy", local, []))
        if courtesy and (chosen or facts) and all(_courtesy(p, a.tokens) for p in s.predicates):
            # a clause that is only talk may also be read as talk ("Valeu!"), against what its words could do
            out.append(Interpretation(a.cost + COURTESY, [], [], a, s, "courtesy", ctx, []))
    return sorted(out, key=lambda i: i.cost)


CLAUSE_SPLIT = 1.0  # reading a comma as the end of a clause the parser did not end
COURTESY = 1.0  # reading as mere talk a clause whose words could also mean a change


def _clauses(sentence: str) -> list[str]:
    """The comma-separated parts of a sentence (not inside quotes), each a possible clause."""
    parts, buf, quote = [], "", None
    for ch in sentence:
        if ch in "\"“”" and quote is None:
            quote = "”" if ch == "“" else ch
        elif quote is not None and ch == quote:
            quote = None
        if ch == "," and quote is None:
            parts.append(buf)
            buf = ""
            continue
        buf += ch
    parts.append(buf)
    return [p.strip() for p in parts if p.strip()]


def _coordinated(sentence: str) -> list[str]:
    """The clauses of a coordination ("e", "and", "depois"): split at the coordinating conjunctions the tagger
    finds; a part with no verb takes the verb of the part before it (gapping: "deixa X em negrito e Y em
    itálico" = "deixa X em negrito" + "deixa Y em itálico")."""
    toks = alternatives.analyses(sentence)[0].tokens if sentence.strip() else []
    if not toks:
        return []
    parts, cur = [], []
    for t in toks:
        if t.upos == "CCONJ" and cur:
            parts.append(cur)
            cur = []
            continue
        cur.append(t)
    if cur:
        parts.append(cur)
    if len(parts) < 2:
        return []
    out, verb = [], None
    for part in parts:
        text = " ".join(t.form for t in part)
        # (a verb by its tag, or by the lexicon when it knows the word only as a verb: "renomeie")
        has_verb = any(t.upos in ("VERB", "AUX") and t.deprel.split(":")[0] in ("root", "conj") or
                       alternatives.categories(t.form, langs.current()) == frozenset({"VERB"}) for t in part)
        if has_verb:
            verb = next((t.form for t in part if t.upos in ("VERB", "AUX")), verb)
        elif verb is not None:
            text = f"{verb} {text}"
        else:
            return []
        out.append(text)
    return out


def _wh_question(sentence: str, text: str, lang: str) -> bool:
    """A sentence asked with an interrogative word ("qual", "o que", "what", "where", "how many"), marked as a
    question: it asks for information. (A polite request in question form, "você pode...?", has none.)"""
    from .questions import INTERROGATIVES
    from .tokenize import tokenize

    k = text.find(sentence)
    end = text[k + len(sentence):k + len(sentence) + 2] if k >= 0 else ""
    if "?" not in end and not sentence.rstrip().endswith("?"):
        return False
    words = [w.lower() for w in tokenize(sentence)]
    joined = " " + " ".join(words) + " "
    wh = INTERROGATIVES.get(lang, {})
    return any(f" {w} " in joined for kind in ("what", "count", "where", "why") for w in wh.get(kind, ()))


def u_limit() -> float:
    return _u().LIMIT


def _sentences(text: str) -> list[str]:
    """The sentences of a text, at their final punctuation (not inside quotes or numbers)."""
    import re

    parts, buf, quote = [], "", None
    for k, ch in enumerate(text):
        buf += ch
        if ch in "\"“”" and quote is None:
            quote = "”" if ch == "“" else ch
        elif quote is not None and ch == quote:
            quote = None
        elif quote is None and ch in ".!?;" and (k + 1 == len(text) or text[k + 1].isspace()):
            # (a point inside a number or a name, "0.5", "1.5rem", is not the end of a sentence)
            parts.append(buf)
            buf = ""
    if buf.strip():
        parts.append(buf)
    out = [re.sub(r"[.;]$", "", p.strip()).strip() for p in parts]
    return [p for p in out if re.search(r"\w", p)]


def understand(text: str, world, lang: str | None = None, ctx: Context | None = None):
    """The new engine's understanding of a text, in the same shape as the old one's (``understand.Understanding``):
    each sentence in order, with what the earlier ones made salient."""
    u = _u()
    lang = lang or langs.detect(text)
    with langs.use(lang):
        sentences = _sentences(text) or [text]
        ctx = ctx or Context()
        work = _world_with(world, Context())
        results = []
        for sent in sentences:
            if _wh_question(sent, text, lang):
                # "qual é a cor do botão?", "what color is the button?": information asked, nothing to change
                results.append(u.Understanding(sent, [], [], "pergunta", langs.msg("question_not_request", lang),
                                               lang))
                continue
            # (a sentence that is only talk, "Valeu!", "Thanks!", is a reading of its own: nothing to do)
            its = interpretations(sent, work, ctx, courtesy=len(sentences) > 1)
            # other segmentations of the sentence into clauses, each read on its own at the cost of the split: at its
            # commas ("me faz um favor, centraliza o parágrafo") and at its coordinations, a clause without a verb
            # taking the previous one's (gapping: "deixa X em negrito e Y em itálico")
            chosen_split = None
            for segs in (_clauses(sent), _coordinated(sent)):
                if len(segs) < 2:
                    continue
                parts, c2, total = [], ctx, CLAUSE_SPLIT * (len(segs) - 1)
                for seg in segs:
                    seg_its = interpretations(seg, work, c2, courtesy=True)
                    if not seg_its:
                        parts = None
                        break
                    parts.append((seg, seg_its))
                    total += seg_its[0].cost
                    c2 = seg_its[0].context or c2
                if not parts or its and its[0].cost <= u.LIMIT and total >= its[0].cost:
                    continue
                if chosen_split is not None and total >= chosen_split[1]:
                    continue
                rs = [_decide(seg, seg_its, work, lang) for seg, seg_its in parts]
                acting = [r for r in rs if r.decision not in ("fato", "cortesia")]
                if acting and all(r.decision == "executar" for r in acting):
                    chosen_split = (rs, total, c2)
            if chosen_split is not None:
                rs, total, c2 = chosen_split
                acting = [r for r in rs if r.decision not in ("fato", "cortesia")]
                cons = [c for r in acting for c in r.best.constraints]
                best = u.Reading("texto", cons, total, [], u.paraphrase(cons, world))
                results.append(u.Understanding(sent, [t for r in rs for t in r.tokens], [best], "executar",
                                               best.paraphrase, lang))
                ctx = c2
                continue
            r = _decide(sent, its, work, lang)
            results.append(r)
            if its:
                ctx = its[0].context or ctx
        if len(results) == 1:
            results[0].text = text
            return results[0]
        acting = [r for r in results if r.decision not in ("fato", "cortesia")]
        if not acting:
            return u.Understanding(text, results[0].tokens, [], "fato", results[0].message, lang)
        failed = next((r for r in acting if r.decision != "executar"), None)
        if failed is not None:
            failed.text = text
            return failed
        cons = [c for r in acting for c in r.best.constraints]
        best = u.Reading("texto", cons, sum(r.best.cost for r in acting), [], u.paraphrase(cons, world))
        return u.Understanding(text, [t for r in results for t in r.tokens], [best], "executar", best.paraphrase, lang)


def _decide(text, its, world, lang):
    """The decision for one sentence: execute, ask (a rival meaning, an ambiguous element, a missing amount, an
    unknown verb), say it was not understood, or note it as information."""
    u = _u()
    if not its:
        return u.Understanding(text, [], [], "nao_entendi", langs.msg("not_understood", why=""), lang)
    best = its[0]
    para = u.paraphrase(best.constraints, world)

    def reading(i):
        return u.Reading("+".join(c.state for c in i.cands) or "fato", i.constraints, i.cost,
                         [n for c in i.cands for n in c.notes], u.paraphrase(i.constraints, world),
                         [n for c in i.cands for n in c.ambiguous], any(c.unknown_verb for c in i.cands),
                         i.sentence.predicates[0].lemma)

    rs = [reading(i) for i in its[:10]]
    tokens = best.analysis.tokens
    if best.act == "assertion" and not best.cands:
        return u.Understanding(text, tokens, rs, "fato", langs.msg("not_understood", why="afirmação"), lang)
    if best.act == "courtesy":
        return u.Understanding(text, tokens, rs, "cortesia", "", lang)
    if any(p.negated for p in best.sentence.predicates if p.act != "assertion"):
        # "não apague o título", "don't delete the heading": a prohibition; nothing is done
        return u.Understanding(text, tokens, rs, "negado", langs.msg("not_doing", lang), lang)
    if rs[0].unknown_verb and best.cost - u.COST["verbo_fora_do_quadro"] > 1.0:
        # the verb means nothing known and the rest does not decide: ask what the verb does (it is then learned)
        return u.Understanding(text, tokens, rs, "perguntar", langs.msg("ask_unknown_verb", verb=rs[0].verb), lang)
    if best.cost > u.LIMIT and not (rs[0].unknown_verb and best.cost - u.COST["verbo_fora_do_quadro"] <= 1.0):
        why = "; ".join(rs[0].assumptions)
        return u.Understanding(text, tokens, rs, "nao_entendi", langs.msg("not_understood", why=why), lang)
    if rs[0].unknown_verb:
        single = all(c["kind"] in ("style", "field") for c in best.constraints)
        second = next((i for i in its[1:] if i.constraints != best.constraints), None)
        if single and (second is None or second.cost - best.cost >= RIVAL_MARGIN):
            return u.Understanding(text, tokens, rs, "executar",
                                   langs.msg("unknown_verb_guess", what=para, verb=rs[0].verb), lang)
        return u.Understanding(text, tokens, rs, "perguntar", langs.msg("ask_unknown_verb", verb=rs[0].verb), lang)
    if any(c.uncertain for c in best.cands):
        why = ""
        return u.Understanding(text, tokens, rs, "perguntar", langs.msg("confirm", why=why, what=para), lang)
    ask = next((c.ask_value for c in best.cands if c.ask_value), None)
    if ask:
        node, prop = ask
        name = (world.nodes.get(node) or {}).get("name") or node
        return u.Understanding(text, tokens, rs, "perguntar",
                               langs.msg("ask_amount", prop=u._label("propriedade", prop).lower(), name=name), lang)
    amb = rs[0].ambiguous
    if amb:
        names = ", ".join(f"«{world.nodes[n]['name']}»" for n in amb[:6] if n in world.nodes)
        return u.Understanding(text, tokens, rs, "perguntar", langs.msg("which", names=names), lang)
    rivals = [i for i in its[1:] if i.cost - best.cost < RIVAL_MARGIN and
              _effect(i.constraints) != _effect(best.constraints) and i.constraints]  # (doing nothing is no rival)
    if rivals:
        options = langs.msg("or").join(f"«{u.paraphrase(i.constraints, world)}»" for i in [best] + rivals[:2])
        return u.Understanding(text, tokens, rs, "perguntar", langs.msg("did_you_mean", options=options), lang)
    return u.Understanding(text, tokens, rs, "executar", para, lang)


def _effect(constraints: list) -> tuple:
    return tuple(sorted(repr(sorted(c.items())) for c in constraints))


def understand_request(text: str, world, by: str = "usuario", lang: str | None = None):
    """What the application calls (plan C6): a definition the user teaches ("blorfar significa ...") is learned;
    a verb the user taught is read through its definition; everything else is understood by this engine."""
    u = _u()
    lang = lang or langs.detect(text)
    with langs.use(lang):
        tokens = u.analyse(text)
        taught = u._definition(tokens, text, world, by)
        if taught is not None:
            taught.lang = lang
            return taught
        pred = u._predicate(tokens)
        if pred is not None and not u._in_frame(pred.lemma):
            definitions = learned_verbs()
            for cand in [pred.lemma] + u._regular_infinitives(pred.form):
                if cand in definitions:
                    rest = " ".join(t.form for t in tokens if t.i > pred.i and t.upos != "PUNCT")
                    body = definitions[cand]["definicao"]
                    out = understand(f"{body} de {rest}" if rest else body, world, lang)
                    out.text = text
                    if out.decision == "executar":
                        out.message = f"{out.message} (pois «{cand}» = «{body}»)"
                    return out
    return understand(text, world, lang)


def learned_verbs() -> dict:
    from . import learned

    return learned.verbs()
