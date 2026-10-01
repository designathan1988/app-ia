"""C2 (docs/plano_compreensao.md §5a): grounding each node of the logical form in what the machine knows.

A mention gets typed denotations, each with a cost (an assumption) and the tokens it explains:

- ``ref``: nodes of the page (by name, type, pronoun, ordinal, universal; restricted by attached phrases, "do
  cartão", "in the header");
- ``kind``: an element type to create (an indefinite or something said new);
- ``prop``: a property or a field, with an optional owner (the "de/of" phrase attached to it);
- ``val``: (property, value) pairs: a named value ("negrito", "blue"), or a measure ("320px de largura");
- ``lit``: a literal (a CSS-like value, a quoted text, a name);
- ``place``: a relation (dentro, antes, depois, inicio, fim) with its anchor.

A predicate gets evidence about the kinds of state it asks for (``verb_evidence``).

The vocabulary is the data's: the builder's catalog (``lexicon``), the W3C value index (``values``), the concept
graph and the dictionary (``grounding``), the language profile's closed classes (``langs``). Nothing here lists
words of a language.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from . import grounding, langs, lexicon
from .logic_form import Mention, Predicate
from .tokenize import is_literal, literal_value
from .values import fold

KINDS_LABELLED = {"tipo", "propriedade", "atributo", "campo", "estado", "breakpoint"}


@dataclass(frozen=True)
class Den:
    kind: str  # ref | kind | prop | field | val | lit | place
    data: object
    cost: float = 0.0
    words: frozenset = frozenset()  # token indices this denotation explains
    notes: tuple = ()
    ambiguous: bool = False  # a reference with several candidates that was not asked for


# -- helpers --------------------------------------------------------------------------------------------------
def _u():
    from . import base as understand

    return understand


def _content(m: Mention) -> list:
    """The mention's own content tokens (not determiners, case markers or attached phrases)."""
    attached = {t.i for _, a in m.attached for t in a.words} | {t.i for c in m.conj for t in c.words}
    prof = langs.profile()
    return [t for t in m.words if t.i not in attached and t.upos not in ("DET", "ADP", "PUNCT", "CCONJ", "SCONJ")
            and fold(t.form.lower()) not in prof["articles"]]


def _lemmas(tokens) -> tuple:
    return tuple(lexicon.lemma_of(t.form) for t in tokens)


def _of_words() -> set:
    prof = langs.profile()
    return {prof["of"]} | ({prof["from"]} if prof.get("from") else set())


@lru_cache(maxsize=8)
def _places(lang: str) -> dict:
    """Normalized place locutions -> relation: the profile's locutions without articles and without the final
    "de/of" (which introduces the anchor)."""
    from .base import FRAMES

    with langs.use(lang):
        of = {fold(langs.profile()["of"])}
        out = {}
        for rel, locs in FRAMES["locais"].items():
            for loc in locs:
                key = tuple(w for w in _words(loc) if w not in of)
                if key:
                    out.setdefault(key, rel)
        return out


def _words(text: str) -> tuple:
    """Folded words of a phrase, contractions expanded, articles left out (function words are not lemmatized)."""
    from .tokenize import contractions

    table = contractions()
    out = []
    for w in text.lower().split():
        out += list(table.get(w, (w,)))
    arts = langs.profile()["articles"]
    return tuple(fold(w) for w in out if fold(w) not in arts and w not in arts)


def place_relation(words: tuple) -> str | None:
    return _places(langs.current()).get(tuple(fold(w) for w in words if w))


def _case_words(case: str) -> tuple:
    """The words of a phrase's preposition(s), without the final "de/of" that introduces the anchor."""
    words = _words(case) if case else ()
    of = fold(langs.profile()["of"])
    return words[:-1] if len(words) > 1 and words[-1] == of else words


# -- references -------------------------------------------------------------------------------------------------
def _named(texts, world) -> list:
    out = []
    for nid, n in world.nodes.items():
        name = (n["name"] or "").lower()
        if name and any(x.lower() == name for x in texts):
            out.append(nid)
    return out


@lru_cache(maxsize=256)
def _type_labels(etype: str) -> frozenset:
    """The folded labels of an element type in every language's catalog ("parágrafo", "paragraph")."""
    from .lexicon import _load

    out = set()
    for lang in ("pt", "en"):
        out |= {fold(e.label.lower()) for e in _load(lang) if e.kind == "tipo" and e.id == etype}
    return frozenset(out)


def _bare_name(name: str) -> str:
    import re

    return fold(re.sub(r"\s+\d+$", "", name or "").lower())


def _default_name(nid: str, world) -> bool:
    """The element still has the name the editor gives (its type's label, maybe with a number: "Parágrafo 2"), and
    another element of its type has one too: the word that matches it is the type word, which does not single the
    element out ("o título" with two titles)."""
    node = world.nodes.get(nid) or {}
    labels = _type_labels(node.get("type") or "")
    if not node.get("name") or _bare_name(node.get("name")) not in labels:
        return False
    return any(o != nid and v.get("type") == node.get("type") and _bare_name(v.get("name")) in labels
               for o, v in world.nodes.items())


def _name_key(text: str) -> tuple:
    """A name as folded words, contractions expanded and articles left out ("Texto do cartão" -> texto de cartao)."""
    return tuple(w for w in _words(text) if w)


def _phrase_names(m: Mention, world) -> list:
    """Elements whose name is said as words of the phrase, a name of several words included ("o título Café
    Aurora", "o texto do cartão" for an element named "Texto do cartão"): (node, token indices)."""
    toks = [t for t in m.words if t.upos != "PUNCT" and fold(t.form.lower()) not in langs.profile()["articles"]]
    seq = []
    for t in toks:
        seq += [(w, t.i) for w in _words(t.form)]
    words = tuple(w for w, _ in seq)
    out = []
    for nid, n in world.nodes.items():
        key = _name_key(n["name"] or "")
        if len(key) < 2:
            continue
        for k in range(len(words) - len(key) + 1):
            if words[k:k + len(key)] == key:
                out.append((nid, frozenset(i for _, i in seq[k:k + len(key)])))
                break
    return out


SENSES = 5  # the senses of a word compared across the languages (a common word has several: "book", "livro")


@lru_cache(maxsize=20_000)
def _word_concepts(word: str, lang: str) -> frozenset:
    from . import concepts

    with langs.use(lang):
        # (a name is a noun: its noun senses first, so that a verb's senses do not crowd them out, "cover")
        lemma = lexicon.lemma_of(word)
        return frozenset(c for c, cost in concepts.concepts_of(lemma, lang, "n")[:SENSES]) |             frozenset(c for c, cost in concepts.concepts_of(lemma, lang)[:3])


def _plural(t) -> bool:
    """Whether a noun is in the plural (its lemma is another form: "títulos", "books")."""
    return fold(lexicon.lemma_of(t.form)) != fold(t.form.lower()) and t.upos == "NOUN"


def _name_class(m: Mention, world) -> list:
    """The elements whose multiword names begin with the mention's head noun, in this language or (through the
    wordnets' shared concepts) the other one: «Livro Um», «Livro Dois» for "livro", "livros", "books"."""
    if m.head.upos not in ("NOUN",) or is_literal(m.head.form):
        return []
    lang = langs.current()
    head = fold(lexicon.lemma_of(m.head.form))
    mine = _word_concepts(m.head.form, lang)
    groups: dict = {}  # the first word of the multiword names -> the elements so named
    for nid, n in world.nodes.items():
        words = (n.get("name") or "").split()
        if len(words) >= 2:
            groups.setdefault(fold(words[0].lower()), []).append(nid)
    out = []
    for first, nids in groups.items():
        if len(nids) < 2:
            continue  # (a class is several elements sharing the word)
        same = fold(lexicon.lemma_of(first)) == head
        if not same:
            with langs.use("pt"):
                same = fold(lexicon.lemma_of(first)) == head
        if same or mine & (_word_concepts(first, "pt") | _word_concepts(first, "en")):
            out += nids
    return out


def _cross_named(m: Mention, world) -> list:
    """Elements named in the other language: an English word that shares its concept with a Portuguese name
    ("the photo" for an element named "Foto", "credits" for "Créditos"), through the wordnets' shared concepts.
    (node, token indices, cost)."""
    from . import concepts

    lang = langs.current()
    other = "pt" if lang == "en" else "en"
    toks = [t for t in m.words if t.upos in ("NOUN", "PROPN", "ADJ") and not is_literal(t.form)]
    mine = {t.i: set(_word_concepts(t.form, lang)) for t in toks}
    with langs.use(other):
        stop = set(langs.profile(other)["articles"]) | {fold(langs.profile(other)["of"])}
    out = []
    for nid, n in world.nodes.items():
        if _default_name(nid, world):
            continue
        words = [w for w in _name_key(n["name"] or "") if w not in stop]
        if not words:
            continue
        used = set()
        for w in words:  # every content word of the name, said in this language, in any order ("card text")
            theirs = _word_concepts(w, other)
            hit = next((i for i, cs in mine.items() if i not in used and cs & theirs), None)
            if hit is None:
                break
            used.add(hit)
        else:
            out.append((nid, frozenset(used), 0.5))
    # the name that explains the most words of the phrase ("card text" is «Texto do cartão», not «Cartão»)
    if out:
        most = max(len(ws) for _, ws, _ in out)
        out = [x for x in out if len(x[1]) == most]
    return out


def _types(tokens, head=None) -> list:
    """Element types the tokens name: a catalog label (possibly of several words) that includes the phrase's head,
    else the head word's meanings in the concept graph (a modifier does not give the type: "the title paragraph"
    is a title). (type, cost, explained token indices)."""
    seq = _lemmas(tokens)
    out = []
    for start in range(len(seq)):
        for e, n in lexicon.match(seq, {"tipo"}, start):
            span = tokens[start:start + n]
            if head is None or any(t.i == head.i for t in span):
                out.append((e.id, 0.0, frozenset(t.i for t in span)))
        if out:
            return out
    for t in tokens if head is None else [t for t in tokens if t.i == head.i]:
        # (a proper name is no common noun: "Promoção" names something, it is not the type "progress")
        if t.upos in ("NOUN", "X", "ADJ") and not is_literal(t.form) and not (t.form[:1].isupper() and t.i > 1):
            for m in grounding.meanings(t.form, "N"):
                if m.kind == "tipo" and m.cost <= 1.5:
                    out.append((m.target, m.cost, frozenset({t.i})))
            if out:
                return out
    return out


def _descends(node, anchor, world) -> bool:
    return _u()._descends(node, anchor, world)


def references(m: Mention, world, restrict: bool = True) -> list[Den]:
    """What page nodes a mention refers to; a coordination refers to all its terms ("o cabeçalho e o rodapé",
    "the header and the footer": the change is distributed over both)."""
    own = _references_one(m, world, restrict)
    if not m.conj or not own:
        return own
    first = own[0]
    nodes, cost, words, amb = list(first.data), first.cost, set(first.words), first.ambiguous
    for c in m.conj:
        sub = references(c, world, restrict)
        if not sub:
            return own  # a term that refers to nothing: the coordination is not of elements
        nodes += [n for n in sub[0].data if n not in nodes]
        cost += sub[0].cost
        words |= set(sub[0].words)
        amb = amb or sub[0].ambiguous
    words |= {t.i for t in m.words if t.upos == "CCONJ"}
    return [Den("ref", tuple(nodes), cost, frozenset(words), first.notes, amb)] + own[1:]


def _interrogative(word: str) -> bool:
    """An interrogative word of the current language (its closed class, ``questions.INTERROGATIVES``)."""
    from .questions import INTERROGATIVES

    w = fold(word.lower())
    return any(w == fold(x) for kind, xs in INTERROGATIVES.get(langs.current(), {}).items() if kind != "exist"
               for x in xs if " " not in x)


def _references_one(m: Mention, world, restrict: bool = True) -> list[Den]:
    """What page nodes a mention (its head phrase, without its coordinated terms) refers to."""
    u = _u()
    COST = u.COST
    prof = langs.profile()
    content = _content(m)
    out = []
    # a pronoun heads its phrase ("isso", "it"); a demonstrative before a noun ("essa imagem", "that image") is a
    # determiner of a description
    if m.det == "pronoun" and _interrogative(m.head.form):
        return []  # ("qual", "onde", "what": the unknown a question asks for, not an element already talked about)
    if m.det == "pronoun" and (m.head.upos == "PRON" or fold(m.head.form.lower()) in prof["pronouns"]):
        # (a personal pronoun takes no description: a word the analysis hung on it, "deixa ele azul", says something
        # else and must be explained by something else)
        if world.selection:
            out.append(Den("ref", tuple(world.selection), COST["referente_pela_selecao"],
                           frozenset(t.i for t in content if t.i == m.head.i or t.upos in ("DET", "ADP")
                                     or t.head != m.head.i), ("o que está selecionado",)))
        return out
    if m.new:
        return []  # something said to be new has no referent
    texts = [literal_value(t.form) for t in m.words if t.i not in {x.i for _, a in m.attached for x in a.words}]
    # (an element with its type's default name is not named by the type word itself, "o título"; it is when the name
    # is said besides the type word, "a página Page")
    head_text = literal_value(m.head.form).lower()
    names = [n for n in _named(texts + m.names, world)
             if not (_default_name(n, world) and (world.nodes[n]["name"] or "").lower() == head_text)]
    phrase = [(n, ws) for n, ws in _phrase_names(m, world) if not (_default_name(n, world) and m.head.i in ws)]
    cross_cost = 0.0
    if phrase:
        names = [nid for nid, _ in phrase]
    types = _types(_chain(m), m.head)  # (a type label can run over its phrase: "bloco de link")
    if not phrase and not names and not types and (m.ordinal is not None or m.det == "universal") and \
            _name_class(m, world):
        pass  # (an ordinal or "every" picks among things of a kind: "the second book" is of the books, «Livro Um»,
        # «Livro Dois», not the one element a name in the other language may mean)
    elif not phrase and not names and not (types and (m.det == "universal" or _plural(m.head))):
        # a name said in the other language; when the word is also a type word, the element must be of that type
        # ("header" names no footer, whatever concept the two words share). (A plural or "todos" phrase is about a
        # set: "todos os títulos" are the headings, not the one named «Title».)
        present = {v["type"] for v in world.nodes.values()}
        type_ids = {ty for ty, _, _ in types} & present  # (a type the page has: its elements are what the word means)
        cross = [x for x in _cross_named(m, world) if not type_ids or world.nodes[x[0]]["type"] in type_ids]
        if cross:
            names = [nid for nid, _, _ in cross]
            cross_cost = min(c for _, _, c in cross)
    elif names and not phrase and types and m.head.i not in {t.i for t in m.words if literal_value(t.form).lower()
                                                             in {(world.nodes[n]["name"] or "").lower() for n in names}}:
        # a name whose element is not of the type said ("the menu section": the nav is «Menu»): the element of that
        # type the name may mean in the other language («Cardápio»), when there is one
        present = {v["type"] for v in world.nodes.values()}
        type_ids = {ty for ty, _, _ in types} & present
        if not any(world.nodes[n]["type"] in type_ids for n in names):
            cross = [x for x in _cross_named(m, world) if world.nodes[x[0]]["type"] in type_ids]
            if cross:
                names = [nid for nid, _, _ in cross]
                cross_cost = min(c for _, _, c in cross)
    cands: list = []
    cost = 0.0
    notes: tuple = ()
    explained = set()
    if names:
        # (when the head itself is the name, "the card" for «Cartão», there is no separate type word to check)
        head_is_name = cross_cost > 0 or any(m.head.i in ws for _, ws in phrase)
        typed = [n for n in names if head_is_name or not types or
                 any(world.nodes[n]["type"] == ty for ty, _, _ in types)]
        cands = typed or names
        cost = 0.0 if typed else COST["tipo_diferente_do_nome"]
        explained |= {t.i for t in m.words if literal_value(t.form).lower() in
                      {(world.nodes[n]["name"] or "").lower() for n in names}}
        explained |= set().union(*(ws for _, ws in phrase)) if phrase else set()
        if cross_cost:
            explained |= set().union(*(ws for _, ws, _ in _cross_named(m, world)))
            cost += cross_cost
        for _, _, ws in types:
            explained |= ws
    elif types:
        # a definite phrase presupposes its referent (DRT): among the types the words can mean ("title": header or
        # heading), those the page has
        present = {v["type"] for v in world.nodes.values()}
        types = [x for x in types if x[0] in present] or types
        best = min(c for _, c, _ in types)
        typs = [ty for ty, c, _ in types if c == best]
        explained |= set().union(*(ws for ty, c, ws in types if c == best))
        cands = [n for n, v in world.nodes.items() if v["type"] in typs]
        cost = best
    elif is_literal(m.head.form) and m.mods:
        # a literal head with a noun before it ("the image 400px" parsed as one phrase): the noun is the element,
        # the literal its value
        for t in m.mods:
            if t.upos in ("NOUN", "PROPN"):
                sub = references(Mention(t, [t]), world)
                if sub:
                    return [Den("ref", sub[0].data, sub[0].cost + 0.5, sub[0].words, sub[0].notes,
                                sub[0].ambiguous)]
        return []
    else:
        cands = _name_class(m, world)
        if not cands:
            return []
        # a common noun that is the word the names of several elements share ("o segundo livro", "how many books"
        # for «Livro Um», «Livro Dois»): those elements
        cost = COST["referente_por_tipo"]
        explained |= {m.head.i}
    # attached phrases restrict by containment: "o título do cartão", "the image in the header"
    for case, a in m.attached:
        if not restrict:
            break
        sub = references(a, world)
        if not sub:
            continue
        anchors = set(sub[0].data)
        inside = [n for n in cands if any(n == x or _descends(n, x, world) for x in anchors)]
        if not inside and names and types:
            # the element a name in the other language gave is not there ("o título do CardA": «Title» is not in
            # CardA): the elements of the type said inside it
            kinds = {ty for ty, _, _ in types}
            inside = [n for n, v in world.nodes.items() if v["type"] in kinds and
                      any(_descends(n, x, world) for x in anchors)]
            if inside:
                names, cost = [], min(c for _, c, _ in types)
                explained |= set().union(*(ws for _, _, ws in types))
        if inside:
            cands = inside
            explained |= set(sub[0].words) | {t.i for t in a.words if t.upos == "ADP"}
            cost += sub[0].cost
    # a noun before the head that refers to an element restricts by containment, as an attached phrase does ("the
    # card title" = the title of the card, English noun compounds); the elements of the type said inside it when the
    # name read first is not there
    for t in m.mods:
        if not restrict or t.upos not in ("NOUN", "PROPN"):
            continue
        sub = references(Mention(t, [t]), world)
        if not sub:
            continue
        anchors = set(sub[0].data)
        inside = [n for n in cands if n not in anchors and any(_descends(n, x, world) for x in anchors)]
        if not inside and types:
            kinds = {ty for ty, _, _ in types}
            inside = [n for n, v in world.nodes.items() if v["type"] in kinds and
                      any(_descends(n, x, world) for x in anchors)]
            if inside:
                names, cost = [], min(c for _, c, _ in types)
                explained |= set().union(*(ws for _, _, ws in types))
        if inside:
            cands = inside
            explained |= set(sub[0].words)
            cost += sub[0].cost
    explained |= {t.i for t in m.words if fold(t.form.lower()) in prof.get("whole", set())}
    # determiners and ordinals pick among the candidates
    if m.ordinal is not None and cands:
        k = m.ordinal
        ordered = [n for n in world.nodes if n in cands]
        if -len(ordered) <= k < len(ordered):
            explained |= {t.i for t in m.words if fold(t.form.lower()) in prof["ordinals"]}
            return [Den("ref", (ordered[k],), cost + COST["referente_por_tipo"], frozenset(explained), notes)]
    if len(cands) == 1:
        return [Den("ref", tuple(cands), cost + (0.0 if names else COST["referente_por_tipo"]), frozenset(explained),
                    notes)]
    if m.det == "universal":
        explained |= {t.i for t in m.words if fold(t.form.lower()) in prof["universal"]}
        return [Den("ref", tuple(cands), cost + COST["referente_por_tipo"], frozenset(explained), notes)]
    sel = [n for n in cands if n in world.selection]
    if len(sel) == 1:
        return [Den("ref", tuple(sel), cost + COST["referente_por_tipo"], frozenset(explained),
                    ("o selecionado entre vários",))]
    if cands:
        return [Den("ref", tuple(cands), cost + COST["referente_ambiguo"], frozenset(explained),
                    (f"{len(cands)} candidatos",), ambiguous=True)]
    return []


# -- properties, values, literals, places -----------------------------------------------------------------------
def _chain(m: Mention) -> list:
    """The mention's content tokens followed by those of its "de/of" phrases, in order: the words a multiword label
    can span ("cor de fundo", "tamanho da fonte")."""
    out = list(_content(m))
    for case, a in m.attached:
        out += [t for t in a.words if t.upos == "ADP" and t.head == a.head.i] + _chain(a)
        break  # (the first phrase attached: a label runs on contiguously)
    return sorted(out, key=lambda t: t.i)


def properties(m: Mention, world) -> list[Den]:
    """Properties, attributes and fields the mention names, with the owner (a reference) when one is attached."""
    from .base import FRAMES

    out = []
    head_name = literal_value(m.head.form).lower()
    if m.head.form[:1].isupper() and m.head.i > 1 and             any((n.get("name") or "").lower() == head_name for n in world.nodes.values()):
        return []  # (the name of an element of the page, "a seção Topo", is not the label it spells: "Topo" = top)
    toks = _chain(m)
    seq = _lemmas(toks)
    for start in range(len(seq)):
        for e, n in lexicon.match(seq, {"propriedade", "atributo", "campo"}, start):
            ws = frozenset(t.i for t in toks[start:start + n])
            # (the label heads the phrase; or the phrase is a literal classified by the label before it, "the text
            # 'Sale'", "the name 'Hero'": the literal is that field's value)
            if m.head.i in ws or is_literal(m.head.form) and toks[start + n - 1].head == m.head.i:
                kind = "field" if e.kind == "campo" else "prop"
                out.append(Den(kind, (e.kind, e.id), 0.0, ws))
    if out:
        # the label that explains the most words is the one said ("largura máxima": max-width, not width)
        longest = max(len(d.words) for d in out)
        out = [d for d in out if len(d.words) == longest]
    campos = {fold(k): v for k, v in FRAMES["campos"].items()}
    if fold(m.head.form.lower()) in campos or lexicon.lemma_of(m.head.form) in campos:
        f = campos.get(fold(m.head.form.lower())) or campos[lexicon.lemma_of(m.head.form)]
        out.append(Den("field", ("campo", f), 0.0, frozenset({m.head.i})))
    # (a word that is exactly the catalog's label of an element type means that type: "título" is a heading, not
    # "right" through a sense of "title" in the concept graph)
    head_lemma = lexicon.lemma_of(m.head.form)
    if not out and not any(e.lemmas == (head_lemma,) for e, _ in lexicon.match((head_lemma,), {"tipo"})):
        for g in grounding.meanings(m.head.form, "N"):
            if g.kind == "propriedade" and g.cost <= 1.0:
                out.append(Den("prop", ("propriedade", g.target), g.cost, frozenset({m.head.i})))
            elif g.kind == "familia" and g.cost <= 1.0:
                headed = _headed(m.head.form)
                out.append(Den("prop", ("lista", headed) if headed else ("familia", g.target), g.cost,
                               frozenset({m.head.i})))
    # the owner: the first attached phrase not used by the label that refers to page nodes; or a noun modifier that
    # names an element ("the paragraph font", "the button text": English noun compounds)
    res = []
    for d in out:
        owner = None
        stack = list(m.attached)
        while stack:
            case, a = stack.pop(0)
            if {t.i for t in a.words} <= d.words:
                continue
            if a.head.i in d.words:
                # the phrase is part of the label ("altura da linha do parágrafo"): the owner is attached to it
                stack = list(a.attached) + stack
                continue
            refs = references(a, world)
            if refs:
                owner = refs[0]
                break
        if owner is None:
            # (the nouns before the label, together: "the menu section background" is the background of the menu
            # section, not of «Menu» and of a section)
            nouns = [t for t in m.mods if t.upos in ("NOUN", "PROPN") and t.i not in d.words]
            from .logic_form import mention as _mention

            whole = [_mention(nouns[-1], {nouns[-1].i: nouns[:-1]})] if len(nouns) > 1 else []
            for sub in whole + [Mention(t, [t]) for t in nouns]:
                refs = references(sub, world)
                if refs:
                    owner = refs[0]
                    break
        data = d.data + ((owner,) if owner else (None,))
        words = d.words | (owner.words if owner else frozenset())
        res.append(Den(d.kind, data, d.cost + (owner.cost if owner else 0.0), words, d.notes,
                       owner.ambiguous if owner else False))
    return res


def values(m: Mention) -> list[Den]:
    """(property, value) pairs the mention's words name, and literals."""
    from .values import index as value_index

    out = []
    ix = value_index()
    content = _content(m)
    # literals: CSS-like values, quoted texts
    attached = {t.i for _, a in m.attached for t in a.words}
    for t in m.words:
        if is_literal(t.form) and t.i not in attached:
            head = next((x for x in m.words if x.i == t.head), None)
            if t.form.isdigit() and head is not None and head.form[:1].isupper() and head.i > 1 and                     not is_literal(head.form):
                # a number after a name ("Livro 3", "Capa 2", "Book 3"): the name with its number, as said
                phrase = [x for x in m.words if x.i not in attached and x.upos not in ("DET", "ADP", "PUNCT", "PART")
                          and x.deprel.split(":")[0] not in ("case", "mark", "det", "cc", "punct")]
                out.append(Den("lit", " ".join(literal_value(x.form) for x in phrase), 0.25,
                               frozenset(x.i for x in phrase)))
                out.append(Den("lit", literal_value(t.form), 1.0, frozenset({t.i})))
                continue
            out.append(Den("lit", literal_value(t.form), 0.0, frozenset({t.i})))
    # (a capitalised word inside the sentence is a name, whatever category the tagger gave it: "para Comprar")
    words = [t for t in content if (t.upos in ("NOUN", "PROPN", "ADJ", "X", "NUM") or literal_value(t.form) in m.names)
             and not _function_word(t)]
    named = [t for t in words if literal_value(t.form) in m.names]
    if not any(d.kind == "lit" for d in out):
        if named and len(named) == len(words):
            # a name said bare ("para Destaque", "por Café Serra", "to Hero"): a literal text as said
            out.append(Den("lit", " ".join(literal_value(t.form) for t in named), 0.5,
                           frozenset(t.i for t in named)))
        elif len(words) > 1 and len(words) == len(content) and not m.attached:
            # a phrase as said ("Olá mundo"): a text; reading words that mean something as a text costs more
            extra = 2.0 if any(meaningful(t) for t in words if t not in named) else 0.0
            out.append(Den("lit", " ".join(t.form for t in words), 1.0 + extra, frozenset(t.i for t in words),
                           ("texto com palavras de significado",) if extra else ()))
        if m.attached and all(not c for c, _ in m.attached):
            # the whole phrase with its caseless parts ("Olá" + "mundo" parsed apart): a text as said
            whole = [t for t in m.words if t.upos in ("NOUN", "PROPN", "ADJ", "X", "NUM") and not _function_word(t)]
            if len(whole) == len([t for t in m.words if t.upos not in ("DET", "PUNCT", "ADP")]):
                extra = 2.0 if any(meaningful(t) for t in whole if literal_value(t.form) not in m.names) else 0.0
                out.append(Den("lit", " ".join(t.form for t in whole), 1.0 + extra, frozenset(t.i for t in whole),
                               ("texto com palavras de significado",) if extra else ()))
        if named and not any(d.kind == "lit" for d in out):
            out.append(Den("lit", " ".join(literal_value(t.form) for t in named), 0.5,
                           frozenset(t.i for t in named)))
    ix = value_index()
    if m.det == "indefinite":
        # the head of a phrase that introduces something ("uma cópia", "a copy") is not a value said; its
        # modifiers can be ("a white background", "um fundo preto")
        content = [t for t in content if t.i != m.head.i]
    prof = langs.profile()
    for t in list(content):
        # a comparative ("maior", "bigger"): a change relative to the element's own current value, never a CSS
        # keyword ("larger" is relative to the parent)
        low = fold(t.form.lower())
        if low in prof["more"] or low in prof["less"]:
            out.append(Den("cmp", 1 if low in prof["more"] else -1, 0.0, frozenset({t.i})))
            content.remove(t)
    # a color and its shade said apart ("azul claro", "light blue"): one named color
    from .values import color_properties, compound_color, named_colors

    shaded = set()
    for t in content:
        pairs = ix.get(fold(lexicon.lemma_of(t.form)), []) or ix.get(fold(t.form.lower()), [])
        color = next((v for _, v in pairs if v in named_colors()), None)
        if color is None:
            continue
        for x in m.words:
            if abs(x.i - t.i) == 1 and x.i not in shaded and not is_literal(x.form) and x.upos in ("ADJ", "ADV", "NOUN"):
                named = compound_color(color, x.form, langs.current())
                if named:
                    out.append(Den("val", tuple((q, named) for q in color_properties()), 0.0, frozenset({t.i, x.i})))
                    shaded |= {t.i, x.i}
    content = [t for t in content if t.i not in shaded]
    for t in content:
        if is_literal(t.form):
            continue
        pairs = ix.get(fold(lexicon.lemma_of(t.form)), []) or ix.get(fold(t.form.lower()), [])
        if not pairs and t.i == m.head.i and m.det in ("definite", "demonstrative") and any(
                e.lemmas != (e.id,) for e, n in lexicon.match((lexicon.lemma_of(t.form),), {"propriedade"}) if n == 1):
            continue  # "o fundo" names the property background; it is not (through the graph) the value bottom
        if pairs:
            out.append(Den("val", tuple(pairs), 0.0, frozenset({t.i})))
            continue
        gs = [g for g in grounding.meanings(t.form, "A" if t.upos == "ADJ" else None) if g.kind == "valor"
              and g.cost <= 1.0]  # (a far meaning is no value said: "mundo" is not font-size: large)
        if gs:
            best = min(g.cost for g in gs)
            out.append(Den("val", tuple(g.target for g in gs if g.cost <= best + 0.5), best, frozenset({t.i})))
    return out


def measure(m: Mention, world) -> list[Den]:
    """A literal and a property word in one phrase, whichever is the head: "320px de largura", "uma margem de
    10px", "400px wide", "24px of margin" -> (property said, literal)."""
    inner = [(c, a) for c, a in m.attached]
    lits = [t for t in m.words if is_literal(t.form)]
    if not lits:
        return []
    lit = lits[0]
    out = []
    sources = []
    if not is_literal(m.head.form):
        sources.append((m, frozenset()))  # the head names the property, the literal depends on it
    for c, a in inner:
        if not is_literal(a.head.form):
            sources.append((a, frozenset(t.i for t in a.words if t.upos == "ADP")))
    for src, extra in sources:
        for d in properties(src, world) if src is not m else _bare_properties(m):
            if d.kind != "prop":
                continue
            out.append(Den("measure", (d.data[0], d.data[1], literal_value(lit.form)), d.cost,
                           d.words | {lit.i} | extra | {t.i for t in m.words if t.upos == "ADP" and t.head == lit.i}))
    return out


@lru_cache(maxsize=4096)
def _headed_for(lemma: str, lang: str) -> tuple:
    # the head of a label: first in Portuguese ("cor do texto"); in the English catalog at either end ("text colour",
    # "Padding top")
    ends = (0,) if lang == "pt" else (0, -1)
    return tuple(sorted({e.id for e in lexicon.load() if e.kind == "propriedade" and len(e.lemmas) >= 2
                         and any(e.lemmas[k] == lemma for k in ends)}))


def _headed(word: str) -> tuple:
    """The properties whose label this word heads ("margem": margem superior, margem direita...)."""
    return _headed_for(lexicon.lemma_of(word), langs.current())


def _bare_properties(m: Mention) -> list[Den]:
    """The properties the head itself names (no owner): for a measure whose literal depends on the property word."""
    out = []
    for g in grounding.meanings(m.head.form, None):
        if g.kind == "propriedade" and g.cost <= 1.0:
            out.append(Den("prop", ("propriedade", g.target), g.cost, frozenset({m.head.i})))
        elif g.kind == "familia" and g.cost <= 1.0:
            headed = _headed(m.head.form)
            out.append(Den("prop", ("lista", headed) if headed else ("familia", g.target), g.cost,
                           frozenset({m.head.i})))
    seq = (lexicon.lemma_of(m.head.form),)
    for e, n in lexicon.match(seq, {"propriedade"}):
        out.append(Den("prop", ("propriedade", e.id), 0.0, frozenset({m.head.i})))
    return out


def place(case: str, m: Mention, world) -> list[Den]:
    """A place said by a phrase: the relation and its anchor (page nodes)."""
    cw = _case_words(case)
    out = []
    head = fold(m.head.form.lower())
    own = tuple(fold(t.form.lower()) for t in _content(m))
    if len(own) > 1 and place_relation(own):
        # a place said with its whole locution ("logo depois do título", "right after the title")
        rel = place_relation(own)
        anchor = next((r for c2, a in m.attached for r in references(a, world)[:1]), None)
        if anchor is not None:
            ws = frozenset(t.i for t in _content(m)) | anchor.words | \
                {t.i for _, a in m.attached for t in a.words if t.upos == "ADP"}
            out.append(Den("place", (rel, anchor.data), anchor.cost, ws, (), anchor.ambiguous))
    # a place noun or adverb with its own anchor ("no fim da seção", "antes do título", "at the end of the card")
    rel = place_relation(cw + (head,)) or place_relation((head,))
    if rel:
        anchor = None
        for c2, a in m.attached:
            refs = references(a, world)
            if refs:
                anchor = refs[0]
                break
        ws = frozenset({m.head.i} | {t.i for t in m.words if t.upos == "ADP" and t.head == m.head.i})
        if anchor is not None:
            out.append(Den("place", (rel, anchor.data), anchor.cost, ws | anchor.words |
                           {t.i for _, a in m.attached for t in a.words if t.upos == "ADP"}, (), anchor.ambiguous))
        elif rel in ("inicio", "fim"):
            root = next((n for n, v in world.nodes.items() if v["parent"] is None), None)
            if root is not None:
                out.append(Den("place", (rel, (root,)), 0.5, ws, ("no início/fim da página",)))
    # the case word alone is the relation and the mention its anchor ("no cabeçalho", "into the footer")
    rel = place_relation(cw) if cw else None
    if rel:
        between = set(cw) & {fold(x) for x in langs.profile().get("between", set())}
        if between and not any(t.upos == "CCONJ" for t in m.words):
            return out  # "entre", "between" needs its two terms: the place is after the first, before the second
        for r in references(m, world):
            ws = r.words | {m.head.i} | (frozenset(t.i for t in m.words) if between else frozenset())
            out.append(Den("place", (rel, r.data), r.cost, ws, r.notes, r.ambiguous))
    return out


def kinds(m: Mention) -> list[Den]:
    """An element type to create: an indefinite phrase or one said new."""
    if m.det not in ("indefinite", "") and not m.new:
        return []
    out = []
    prof = langs.profile()
    numbers = langs.profile().get("numbers", {})
    count, count_ws = 1, set()
    for t in m.words:
        if t.head == m.head.i and t.deprel.split(":")[0] == "nummod":
            low = fold(t.form.lower())
            if low.isdigit():
                count, count_ws = int(low), {t.i}
            elif low in numbers:
                count, count_ws = numbers[low], {t.i}
    for ty, c, ws in _types(_chain(m), m.head):
        newness = {t.i for t in m.words if fold(t.form.lower()) in prof["new"]}
        out.append(Den("kind", ty, c, ws | newness | count_ws, (f"n={count}",) if count > 1 else ()))
    return out


def ground(m: Mention, world) -> list[Den]:
    """All typed denotations of a mention, cheapest first."""
    out = references(m, world) + kinds(m) + properties(m, world) + values(m) + measure(m, world)
    seen, uniq = set(), []
    for d in sorted(out, key=lambda d: d.cost):
        k = (d.kind, repr(d.data))
        if k not in seen:
            seen.add(k)
            uniq.append(d)
    return uniq


def meaningful(t) -> bool:
    """A word that means something to the machine: a literal, a label, or a near meaning in the concept graph."""
    from .values import index as value_index

    if is_literal(t.form) or place_relation((fold(t.form.lower()),)):
        return True  # (a place word, "depois", "below", is the grammar of places)
    if t.form[:1].isupper() and t.i > 1:
        return True  # (a name said inside the sentence, "chama ele de Endereço": information a reading must use)
    if t.upos in ("VERB", "AUX") and _u()._in_frame(t.lemma):
        return True  # (a verb of a known frame, "chamar" = to name: leaving it out leaves out what it asks)
    if grounding.direct(t.form) or lexicon.match((lexicon.lemma_of(t.form),), KINDS_LABELLED) or \
            value_index().get(fold(lexicon.lemma_of(t.form))):
        return True
    return any(m.cost <= 1.0 for m in grounding.meanings(t.form))


# -- predicates ---------------------------------------------------------------------------------------------------
@dataclass
class Evidence:
    """What a verb says about the state asked for: a cost per kind of state (lower = more expected), the commands it
    names, the (property, value) pairs it names itself ("centralizar"), the properties its meaning is about
    ("alinhar": alignment), and the particle tokens that are part of it ("jogar fora", "get rid of")."""
    kinds: dict = field(default_factory=dict)
    commands: list = field(default_factory=list)
    pairs: list = field(default_factory=list)
    props: dict = field(default_factory=dict)
    known: bool = True
    light: bool = False  # a light, copular or volitive verb: the arguments decide
    lemma: str = ""
    particles: frozenset = frozenset()
    whole: set = field(default_factory=set)  # commands the verb means as a whole ("descer" = "mover para baixo")
    cmp: int = 0  # a verb of more or less ("aumentar", "increase"): +1 / -1


STATE_OF_FRAME = {"existir": "added", "remover": "removed", "mover": "moved", "estilo": "style",
                  "estilo_por_valor": "style", "texto": "field:text", "escrever": "field:text", "nome": "field:name",
                  "renomear": "field:name", "atributo": "field:attributes"}
ALL_STATES = ("style", "command", "added", "removed", "moved", "field:text", "field:name", "field:attributes")
GRAPH_LIMIT = 3.0
# a synonym's participle naming values of more properties than this names none in particular (an indirect path;
# the same rule as values.MAX_KEYWORDS for words)
MAX_VALUE_PROPS = 2


def _verb_candidates(p: Predicate, tokens) -> list[tuple[str, frozenset]]:
    """(lemma, particle tokens) the predicate's verb can be: a verb with the particle after it that the lexicon
    lexicalizes together ("jogar fora", "throw away", "get rid of"); its lemma and homographs; the infinitives a
    form unknown to the morphology has by the regular conjugation ("deleta" -> deletar)."""
    from . import concepts

    u = _u()
    out = []
    if tokens:
        k = next((i for i, t in enumerate(tokens) if t.i == p.head.i), None)
        for n in (2, 1):
            tail = tokens[k + 1:k + 1 + n] if k is not None else []
            if len(tail) != n or tail[0].upos not in ("ADV", "ADP", "PART", "ADJ", "NOUN"):
                continue
            phrase = " ".join([p.lemma] + [t.form.lower() for t in tail])
            if concepts.concepts_of(phrase, langs.current(), "v"):
                out.append((phrase, frozenset(t.i for t in tail)))
    out += [(lem, frozenset()) for lem in [p.lemma] + list(getattr(p.head, "alts", ()))]
    if langs.current() == "pt":
        out += [(lem, frozenset()) for lem in u._regular_infinitives(p.head.form)]
    seen, uniq = set(), []
    for lem, parts in out:
        if lem not in seen:
            seen.add(lem)
            uniq.append((lem, parts))
    return uniq


def _from_lexicon(lem: str, ev: Evidence) -> None:
    """The verb's frames, the builder commands it labels and the values its participle names."""
    u = _u()
    from . import command_verbs
    from .builder_commands import FRAME_COMMANDS

    for f in u.FRAMES["quadros"]:
        if u._in_frame(lem, f):
            st = STATE_OF_FRAME.get(f["id"])
            if st:
                ev.kinds[st] = 0.0
    if "added" in ev.kinds and "style" not in ev.kinds:
        # an insertion verb whose object is an amount of a property gives that property ("add a 10px margin",
        # "acrescenta 8px de espaço"): a style, at the cost of the construction
        ev.kinds["style"] = 1.0
    for cv in command_verbs.table().get(lem, []):
        if cv.command in FRAME_COMMANDS.values():
            continue  # the command that performs a frame's change ("Excluir"): that change is the state itself
        ev.commands.append(cv)
        ev.kinds["command"] = 0.0
    if not ev.kinds:
        # a verb whose participle names a value: the state it leaves ("centralizar": centralizado -> text-align:
        # center; "underline": underlined) - only for verbs outside the frames: a frame verb's participle
        # ("deixado") names nothing about the change
        pairs = list(u._verb_value_pairs(lem))
        for form in participles(lem):
            pairs += [g.target for g in grounding.meanings(form, "A") if g.kind == "valor" and g.cost == 0.0
                      and g.target not in pairs]

        for pr in pairs:
            ev.pairs.append(pr)
            ev.kinds["style"] = 0.0


@lru_cache(maxsize=4096)
def _participles(lem: str, lang: str) -> tuple:
    """The past participle of a verb, by the regular formation, kept only when the morphology confirms it is that
    verb's participle (MorphoBr; the English lemmatizer)."""
    if lang == "en":
        cands = [lem + "ed", lem + "d", lem[:-1] + "ied", lem + lem[-1:] + "ed"]
        return tuple(c for c in cands if langs.english_lemma(c, "VERB") == lem)
    from .morph import analyses

    stem, end = lem[:-2], lem[-2:]
    cands = [stem + "ado"] if end == "ar" else [stem + "ido"] if end in ("er", "ir") else []
    return tuple(c for c in cands if any(le == lem and tg.startswith("V+PTPST") for le, tg in analyses(c)))


def participles(lem: str) -> tuple:
    return _participles(lem, langs.current())


def _from_graph(lem: str, ev: Evidence, only_props: bool = False) -> None:
    """What the verb means for the machine through the concept graph and the dictionary. A CSS keyword reached
    from a verb this way ("descer" ~ cursor: move) is too indirect to be the value said: it only says the change is
    a style."""
    u = _u()
    from . import command_verbs
    from .builder_commands import FRAME_COMMANDS

    frame_of_command = {c: f for f, c in FRAME_COMMANDS.items()}
    for g in grounding.meanings(lem, "V"):
        if g.cost > GRAPH_LIMIT:
            continue
        if g.kind in ("propriedade",) and g.cost <= 1.5:
            ev.props[g.target] = min(ev.props.get(g.target, 9.0), g.cost)
        if only_props:
            continue
        if g.kind == "comando" and g.target in frame_of_command:
            # the command that performs a frame's change ("erase" ~ Excluir): the frame's state
            st = STATE_OF_FRAME.get(frame_of_command[g.target])
            if st:
                ev.kinds[st] = min(ev.kinds.get(st, 9.0), g.cost)
        elif g.kind == "comando":
            # the verb means the command as a whole, label and all ("descer" ~ "Mover para baixo")
            for verbs in command_verbs.table().values():
                for cv in verbs:
                    if cv.command == g.target and cv not in ev.commands:
                        ev.commands.append(cv)
                        ev.whole.add(cv.command)
            if ev.commands:
                ev.kinds["command"] = min(ev.kinds.get("command", 9.0), g.cost)
        elif g.kind in ("verbo", "acao"):
            for f in u.FRAMES["quadros"]:
                if u._in_frame(g.target, f) or f["id"] == g.target:
                    st = STATE_OF_FRAME.get(f["id"])
                    if st:
                        ev.kinds[st] = min(ev.kinds.get(st, 9.0), g.cost)
        elif g.kind in ("valor", "propriedade", "familia"):
            lexical = bool(g.path) and g.path[0][0] in ("sinonimo", "traducao")
            if g.kind == "valor" and lexical and g.cost <= 1.0:
                # a synonym or translation that names the value ("grifar" ~ sublinhar -> underline): said as such
                ev.pairs.append(g.target)
                ev.kinds["style"] = min(ev.kinds.get("style", 9.0), g.cost)
            else:
                ev.kinds["style"] = min(ev.kinds.get("style", 9.0), g.cost + (1.0 if g.kind == "valor" else 0.0))


def verb_evidence(p: Predicate, tokens=None) -> Evidence:
    u = _u()
    ev = Evidence(lemma=p.lemma)
    prof = langs.profile()
    if fold(p.lemma) in prof["more"] or fold(p.lemma) in prof["less"]:
        # "aumenta a fonte", "increase the margin": a change of amount, relative to the current value
        ev.cmp = 1 if fold(p.lemma) in prof["more"] else -1
        ev.kinds = {"style": 0.0}
        return ev
    multi = [(lem, parts) for lem, parts in _verb_candidates(p, tokens) if parts]
    if (p.kind == "state" or p.lemma in u.COPULAS or p.lemma in u.MODALS) and not multi:
        # a copula, or a volitive with no verbal complement ("quero o título azul", "I'd like it in bold"): the
        # state is what the arguments say
        ev.light = True
        ev.kinds = {"style": 0.0, "added": 1.0}
        return ev
    for lem, parts in _verb_candidates(p, tokens):
        _from_lexicon(lem, ev)
        if not ev.kinds:
            _from_graph(lem, ev)
        if ev.kinds:
            ev.lemma, ev.particles = lem, parts
            _from_graph(lem, ev, only_props=True)
            break
    if not ev.pairs and set(ev.kinds) <= {"style"} and langs.current() == "pt" and not u._in_frame(p.lemma):
        # a dictionary synonym whose participle names a value ("grifar" ~ sublinhar: sublinhado -> underline)
        from . import dictionary

        for syn in dictionary.synonyms(p.lemma)[:4]:
            for form in participles(syn):
                pairs = [g.target for g in grounding.meanings(form, "A") if g.kind == "valor" and g.cost == 0.0]
                if pairs and len({prop for prop, _ in pairs}) <= MAX_VALUE_PROPS:
                    ev.pairs += [pr for pr in pairs if pr not in ev.pairs]
                    ev.kinds["style"] = 1.0
    if not ev.kinds:
        ev.known = False
        ev.kinds = {s: u.COST["verbo_fora_do_quadro"] for s in ALL_STATES}
    return ev


def _function_word(t) -> bool:
    """A preposition, article or pronoun of the language, whatever category the tagger gave it ("como none": "como"
    is no part of the value)."""
    from .alternatives import _closed_word

    return _closed_word(t.form, langs.current())
