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
from dataclasses import dataclass, field

from . import alternatives, grounding, langs, lexicon
from . import ground as gr
from . import logic_form as lf
from .tokenize import is_literal
from .values import fold

RIVAL_MARGIN = 1.0
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


def _themes(p: lf.Predicate, args: list[Arg]) -> list[tuple[Arg, gr.Den]]:
    """The element(s) the predicate is about: the object of an event, else its subject (a copular, obligation or
    passive clause: "o botão tem que ficar verde")."""
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
    return {t.i for t in m.words if t.upos == "ADP" and t.head == m.head.i}


# -- the kinds of state -----------------------------------------------------------------------------------------
def _style(p, args, ev, world) -> list[Cand]:
    u = _u()
    from .values import _builder_properties

    builder = _builder_properties()
    values_ = [(a, d) for a in args for d in a.of("val", "lit", "measure", "cmp")
               if a.role in ("result", "attr", "obj", "obl", "adv") and (_value_case(a.case) or a.role != "obl")]
    if ev.cmp:
        values_.append((None, gr.Den("cmp", ev.cmp, 0.0, frozenset({p.head.i}))))
    for pr in ev.pairs:
        values_.append((None, gr.Den("val", (pr,), 0.0, frozenset({p.head.i}))))
    # a property said, or the text of an element ("o texto do botão branco": the owner's text)
    props = [(a, d) for a in args for d in a.of("prop")] + \
        [(a, d) for a in args for d in a.of("field") if d.data[1] == "text" and d.data[2] is not None] + [(None, None)]
    themes = _themes(p, args)
    places = [(a, d) for a in args for d in a.of("place") if d.data[0] == "dentro"]
    out = []
    for (va, v), (pa, pd) in itertools.product(values_, props):
        if pd is not None and (v.words & pd.words) and v.kind != "measure":
            continue
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
                said, v_lit = v.data[:2], v.data[2]
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
                # the verb's own meaning is about properties ("alinhar", "align": alignment): one of them
                options = [o for o in options if o[0] in ev.props]
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
            options = [o for o in options if o[0] in builder]
            if not options:
                continue
            best = min(c for _, _, c in options)
            chosen = [o for o in options if o[2] == best]
            prop, value, prior = chosen[0]
            bp, st = world.layer
            ask = None
            if v.kind == "cmp":
                value, ask = _scaled(world, nodes[0], prop, v.data)
            cons = [{"kind": "style", "id": n, "breakpoint": bp, "state": st, "property": prop,
                     "value": u._as_keyword(value, prop)} for n in nodes]
            explained = set(v.words) | set(t.words) | ({p.head.i} if "style" in ev.kinds else set()) | \
                ev.particles | explained_side
            cost = v.cost + t.cost + prior + ev.kinds.get("style", 9.0)
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
        return [(q, lit, u._prior(q, ntype)) for q in pid if u._value_fits(q, lit) and
                u._value_kind(lit) in u.ACCEPTS.get(builder.get(q, {}).get("valueType"), {u._value_kind(lit)})]
    if kind == "familia":
        out += [(q, lit, u._prior(q, ntype)) for q, info in builder.items()
                if info.get("valueType") == pid and u._value_fits(q, lit)]
        return out
    vtype = builder.get(pid, {}).get("valueType")
    takes = u._value_kind(lit) in u.ACCEPTS.get(vtype, ()) if vtype in u.ACCEPTS else u._value_fits(pid, lit)
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


def _commands(p, args, ev, world, sentence_lemmas) -> list[Cand]:
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
            themes = _themes(p, args)
        for a, t in themes:
            cons = [{"kind": "command", "command": cv.command, "id": n, "label": cv.label,
                     "already": bool(cv.flag and world.nodes[n].get("flags", {}).get(cv.flag))} for n in t.data]
            out.append(Cand("command", cons, t.cost + vcost, set(t.words) | words | rest_tokens |
                            _case_tokens(a.mention), list(t.notes), list(t.data) if t.ambiguous else []))
    return out


def _structural(p, args, ev, world) -> list[Cand]:
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
            own = [(Arg("obl", c, x, []), d) for c, x in a.mention.attached for d in gr.place(c, x, world)]
            opts = [(pa, pd) for pa, pd in places if pa is not a] + own or [(None, None)]
            for pa, pd in opts:
                cost = k.cost + ev.kinds.get("added", 9.0)
                explained = set(k.words) | {p.head.i}
                parent = index = None
                notes = []
                amb = []
                if pd is not None:
                    rel, anchors = pd.data
                    parent, index = u._placement(rel, anchors[0], world)
                    cost += pd.cost
                    explained |= set(pd.words) | _case_tokens(pa.mention)
                    amb = list(anchors) if pd.ambiguous else []
                else:
                    cost += u.COST["local_ausente"]
                    notes.append("sem local: onde o editor puser")
                if a.mention.det == "definite":
                    cost += u.COST["definido_com_referente"]
                out.append(Cand("added", [{"kind": "added", "type": k.data, "parent": parent, "index": index}],
                                cost, explained, notes, amb))
    for a, t in _themes(p, args):
        # removed
        out.append(Cand("removed", [{"kind": "removed", "id": n} for n in t.data],
                        t.cost + ev.kinds.get("removed", 9.0), set(t.words) | {p.head.i}, list(t.notes),
                        list(t.data) if t.ambiguous else []))
        # moved: to a place said by another phrase
        for pa, pd in places:
            if pa is a:
                continue
            rel, anchors = pd.data
            if any(n in anchors for n in t.data):
                continue
            cons = []
            for n in t.data:
                parent, index = u._placement(rel, anchors[0], world, moving=n)
                cons.append({"kind": "moved", "id": n, "parent": parent, "index": index})
            out.append(Cand("moved", cons, t.cost + pd.cost + ev.kinds.get("moved", 9.0),
                            set(t.words) | set(pd.words) | {p.head.i} | _case_tokens(pa.mention), list(t.notes),
                            list(t.data) if t.ambiguous else list(anchors) if pd.ambiguous else []))
    return out


def _fields(p, args, ev, world) -> list[Cand]:
    out = []
    lits = [(a, d) for a in args for d in a.of("lit") if a.role in ("obj", "result", "attr", "obl", "content")
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
        targets = _themes(p, args) + [(a, d) for a in args for d in a.of("place") if d.data[0] == "dentro"]
        for (ta, t), (la, lit) in itertools.product(targets, lits):
            if la is ta or t.kind == "place" and la.role == "obl":
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
    return {i for i, t in toks.items() if t is None or (t.upos in ("NOUN", "PROPN", "ADJ", "VERB", "ADV", "NUM", "X")
                                                         or is_literal(t.form)) and t.upos != "PRON"}


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
def readings(p: lf.Predicate, world, tokens) -> list[Cand]:
    ev = gr.verb_evidence(p, tokens)
    args = _args(p, world, ev.particles)
    lemmas = {t.i: lexicon.lemma_of(t.form) for t in tokens}
    lemmas.update({t.i: fold(t.lemma) for t in tokens if t.upos in ("VERB", "ADP", "ADV")})
    cands = _style(p, args, ev, world) + _commands(p, args, ev, world, lemmas) + \
        _structural(p, args, ev, world) + _fields(p, args, ev, world)
    # a causative ("faz o parágrafo sumir", "make the image disappear"): the caused event, its theme the causee
    for r, w, q in p.roles:
        if isinstance(q, lf.Predicate) and r in ("content", "result"):
            causee = [x for rl, _, x in p.roles if rl == "obj" and isinstance(x, lf.Mention)]
            q2 = lf.Predicate(q.head, q.lemma, q.kind, q.act, q.negated,
                              list(q.roles) + ([("obj", "", causee[0])] if causee and not q.role("obj") else []))
            for c in readings(q2, world, tokens):
                c.cost += 0.5
                c.explained |= {p.head.i}
                cands.append(c)
    for c in cands:
        c.explained |= set(ev.particles)  # the particle is part of the verb ("jogar fora", "get rid of")
        extra, left = _unexplained(p, c, tokens)
        c.cost += extra
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


def interpretations(text: str, world) -> list[Interpretation]:
    out = []
    for a in alternatives.analyses(text):
        s = lf.build(a.tokens)
        if not s.predicates:
            continue
        total, cons, chosen = a.cost, [], []
        ok = True
        for p in s.predicates:
            rs = readings(p, world, a.tokens)
            if not rs:
                ok = False
                break
            total += rs[0].cost
            cons += rs[0].constraints
            chosen.append(rs[0])
        if ok:
            out.append(Interpretation(total, cons, chosen, a, s, s.predicates[0].act))
    return sorted(out, key=lambda i: i.cost)


def understand(text: str, world, lang: str | None = None):
    """The new engine's understanding, in the same shape as the old one's (``understand.Understanding``)."""
    u = _u()
    lang = lang or langs.detect(text)
    with langs.use(lang):
        its = interpretations(text, world)
        if not its:
            return u.Understanding(text, [], [], "nao_entendi", langs.msg("not_understood", why=""), lang)
        best = its[0]
        para = u.paraphrase(best.constraints, world)

        def reading(i):
            r = u.Reading("+".join(c.state for c in i.cands), i.constraints, i.cost,
                          [n for c in i.cands for n in c.notes], u.paraphrase(i.constraints, world),
                          [n for c in i.cands for n in c.ambiguous], any(c.unknown_verb for c in i.cands),
                          i.sentence.predicates[0].lemma)
            return r

        rs = [reading(i) for i in its[:10]]
        tokens = best.analysis.tokens
        if best.act == "assertion":
            return u.Understanding(text, tokens, rs, "fato", langs.msg("not_understood", why="afirmação"), lang)
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
        ask = next((c.ask_value for c in best.cands if c.ask_value), None)
        if ask:
            node, prop = ask
            return u.Understanding(text, tokens, rs, "perguntar",
                                   langs.msg("ask_amount", prop=u._label("propriedade", prop).lower(),
                                             name=world.nodes[node]["name"] or node), lang)
        amb = rs[0].ambiguous
        if amb:
            names = ", ".join(f"«{world.nodes[n]['name']}»" for n in amb[:6] if n in world.nodes)
            return u.Understanding(text, tokens, rs, "perguntar", langs.msg("which", names=names), lang)
        rivals = [i for i in its[1:] if i.cost - best.cost < RIVAL_MARGIN and
                  _effect(i.constraints) != _effect(best.constraints)]
        if rivals:
            options = langs.msg("or").join(f"«{u.paraphrase(i.constraints, world)}»" for i in [best] + rivals[:2])
            return u.Understanding(text, tokens, rs, "perguntar", langs.msg("did_you_mean", options=options), lang)
        return u.Understanding(text, tokens, rs, "executar", para, lang)


def _effect(constraints: list) -> tuple:
    return tuple(sorted(repr(sorted(c.items())) for c in constraints))
