"""Alternative analyses of a sentence: robustness to parsing errors by local reinterpretation (plan §3.4).

The linear parser is wrong on about one dependency in five (LAS ~80 pt, ~75 en). A beam over its transitions does
not help: it was trained greedily, and its other trees are worse, not different (experiments/x3_kbest.py:
UAS 83% greedy, 76% beam, 82.5% oracle of 4).

Its errors on requests are of a few general kinds, the classic ones of dependency parsing:
- **category:** a word given a category its lexicon does not allow, or one the tagger hesitated about. Examples:
  "delete" or "underline" as a preposition at the start of a request; "bold" as a noun after "the title".
- **attachment:** a complement attached to the noun before it instead of the verb, or the other way round ("deixe
  o título em negrito": "em negrito" belongs to "deixe", not to "título"). Likewise an adjective as a modifier of
  the noun or as a predicate of the clause ("deixe o título verde").

So the alternatives are built from the greedy analysis:
1. re-categorize one word, or two doubtful ones, among the categories the lexicon gives it (MorphoBr; the
   WordNets), then parse again;
2. move one dependent, or two, to another head on the attachment frontier (an ancestor of its head, or a noun to
   its left), keeping the tree projective, and let the labeler name the new relation.

Each alternative carries the number of edits as its cost. Which one is meant is decided by what its logical form
means (the grounding and the abduction, plan §3.2-3.3), not here.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from functools import lru_cache

from . import langs
from .tokenize import is_literal, tokenize

CONTENT = ("NOUN", "VERB", "ADJ", "ADV")
EDIT_COST = 1.0
# relations a dependent can have, by the category of its head
UNDER_VERB = {"obl", "xcomp", "advmod", "obj", "iobj", "advcl", "nsubj", "ccomp"}
UNDER_NOUN = {"nmod", "amod", "acl", "appos", "compound", "nummod", "flat"}
MOVABLE = (UNDER_VERB | UNDER_NOUN | {"conj"}) - {"flat"}


@dataclass
class Analysis:
    tokens: list
    cost: float = 0.0
    edits: list = field(default_factory=list)  # human-readable description of each edit


# -- what categories a word can have --------------------------------------------------------------------------
_WN = {"n": "NOUN", "v": "VERB", "a": "ADJ", "s": "ADJ", "r": "ADV"}
_MORPH = {"N": "NOUN", "V": "VERB", "A": "ADJ", "ADV": "ADV"}


@lru_cache(maxsize=50_000)
def categories(word: str, lang: str) -> frozenset:
    """The content categories a word form can have, according to the lexicons (empty when no lexicon knows it)."""
    from . import concepts

    low = word.lower()
    out = set()
    con = concepts._con()
    forms = {low}
    if lang == "en":
        forms |= {langs.english_lemma(low, u) for u in ("VERB", "NOUN", "ADJ")}
    else:
        from .morph import analyses

        for lemma, tags in analyses(low):
            cat = _MORPH.get(tags.split("+")[0])
            if cat:
                out.add(cat)
    if con is not None:
        for f in forms:
            for (pos,) in con.execute("SELECT DISTINCT pos FROM lex WHERE lang = ? AND word = ?", (lang, f)):
                if pos and pos[0] in _WN:
                    out.add(_WN[pos[0]])
    return frozenset(out)


CLOSED = {"DET", "PRON", "CCONJ", "SCONJ", "AUX", "PUNCT", "NUM", "SYM"}


@lru_cache(maxsize=20_000)
def _closed_word(word: str, lang: str) -> bool:
    """A function word of the language: a preposition, article, pronoun or conjunction in the morphology
    (MorphoBr), or one of the profile's closed classes."""
    low = word.lower()
    prof = langs.profile(lang)
    from .base import FRAMES

    with langs.use(lang):
        cases = set(FRAMES["valor_casos"])  # (the language's value markers: "para", "como", "to", "as")
        # and the words of its place locutions ("antes", "depois", "before", "after", "into")
        # (not the nouns of those locutions: "topo", "fim", "início" are words of content)
        cases |= {w for locs in FRAMES["locais"].values() for loc in locs for w in loc.split()
                  if len(loc.split()) == 1 or "NOUN" not in categories(w, lang)}
    closed = set(prof["articles"]) | set(prof["pronouns"]) | cases | {prof["of"]}
    if low in closed:
        return True
    if lang == "pt":
        from .morph import analyses

        tags = {tg.split("+")[0] for _, tg in analyses(low)}
        return bool(tags) and tags <= {"PREP", "DET", "PRON", "CONJ", "ART", "ADV"} and bool(
            tags & {"PREP", "DET", "PRON", "CONJ", "ART"})
    return False


# -- tree utilities -------------------------------------------------------------------------------------------
def _base(rel: str) -> str:
    return rel.split(":")[0]


def _projective(heads: list[int]) -> bool:
    """heads[k] is the head (1-based, 0 = root) of word k+1."""
    arcs = [(min(d, h), max(d, h)) for d, h in enumerate(heads, 1) if h]
    for (a, b), (c, d) in itertools.combinations(arcs, 2):
        if a < c < b < d or c < a < d < b:
            return False
    return True


def _acyclic(heads: list[int]) -> bool:
    for d in range(1, len(heads) + 1):
        seen, x = set(), d
        while x:
            if x in seen:
                return False
            seen.add(x)
            x = heads[x - 1]
    return True


def _ancestors(heads: list[int], d: int) -> list[int]:
    out, x = [], heads[d - 1]
    while x:
        out.append(x)
        x = heads[x - 1]
    return out


# -- the alternatives -----------------------------------------------------------------------------------------
def _models():
    from .base import _models as m

    return m()


def _parsed(words, tags):
    from .base import make_tokens

    _, parser, _, _ = _models()
    return make_tokens(words, tags, parser.parse([_shown(w) for w in words], tags))


def _shown(w: str) -> str:
    """The word as the models see it: a literal as a value; a page name joined into one word as a proper noun.

    The Portuguese models read "VALOR" as the noun "valor". The English models never saw it (an unknown capitalized
    word, which they chain into a proper name with the words after it), so in English a literal is shown as a word
    of its kind that the English treebank knows: a number for a length or number, a colour word for a colour, a
    frequent proper noun for a text; and a page name as that proper noun too."""
    if langs.current() == "en":
        if is_literal(w):
            import re as _re

            if _re.match(r"-?\d", w):
                return "10"
            if w.startswith("#") or _re.match(r"(rgb|rgba|hsl|hsla|oklch|lab|lch|color)\(", w.lower()):
                return "red"
            return "John"
        return "John" if " " in w else w
    if is_literal(w):
        return "VALOR"
    return w.split(" ")[0].capitalize() if " " in w else w


def _tag_variants(words: list[str], tags: list[str]) -> list[tuple[list[str], list[str]]]:
    """Re-categorizations of one word, or of two doubtful words: (tags, edits)."""
    tagger, _, _, _ = _models()
    lang = langs.current()
    options = {}
    doubtful = set()
    for k, (w, t) in enumerate(zip(words, tags)):
        if is_literal(w) or " " in w or (w.lower() in tagger.tagdict and t not in CONTENT and t != "ADP"):
            continue  # (a literal, a page name: one unit, its category is not in doubt)
        cats = categories(w, lang)
        if not cats and w.isalpha() and w.lower() not in tagger.tagdict:
            # no lexicon knows the form: closed classes are all known, so it is an open-class word
            cats = frozenset({"NOUN", "VERB", "ADJ"})
        alts = [c for c in cats if c != t]
        if not alts or t in CLOSED or _closed_word(w, lang) or                 w.lower() in tagger.tagdict and t not in CONTENT and t not in ("ADP", "PART"):
            continue  # a function word keeps its category ("o" is no noun, "para" no verb here)
        options[k] = alts
        if cats and t not in cats:
            doubtful.add(k)  # a category the lexicon does not allow
    from . import ground

    for k, (w, t) in enumerate(zip(words, tags)):
        if t == "ADV" and k + 1 < len(words) and ground.place_relation((w.lower(),)):
            options.setdefault(k, [])
            if "ADP" not in options[k]:
                options[k].append("ADP")
    out = []
    for k, alts in options.items():
        for c in alts:
            new = list(tags)
            new[k] = c
            out.append((new, [f"{words[k]}: {tags[k]}->{c}"]))
    pairs = sorted(doubtful | {k for k in options if k == 0 or tags[k] in ("NOUN", "ADJ") and k > 0})
    for a, b in itertools.combinations(pairs, 2):
        for ca in options[a]:
            for cb in options[b]:
                new = list(tags)
                new[a], new[b] = ca, cb
                out.append((new, [f"{words[a]}: {tags[a]}->{ca}", f"{words[b]}: {tags[b]}->{cb}"]))
    return out


def _relabel(words, tags, heads, d) -> str:
    """The relation the labeler gives a moved dependent, among those its new head's category allows."""
    _, parser, _, _ = _models()
    h = heads[d - 1]
    htag = tags[h - 1] if h else "ROOT"
    allowed_base = UNDER_VERB if htag in ("VERB", "AUX", "ADJ", "ADV", "ROOT") else UNDER_NOUN
    allowed = [c for c in parser.labeler.classes if _base(c) in allowed_base]
    shown = [_shown(w) for w in words]
    return parser.labeler.predict(parser._label_features(shown, tags, d, h), allowed)


def _attachment_variants(tokens, step: bool = False) -> list[tuple[list[int], list[str], list[int], bool]]:
    """Single moves of one dependent to another head on its attachment frontier: (heads, edits, moved,
    projective). With `step`, a move that is not projective by itself is kept as a step towards a second move (a
    phrase split by the parser needs both of its parts moved: "pra Olá mundo")."""
    heads = [t.head for t in tokens]
    out = []
    roots = [t.i for t in tokens if t.head == 0]
    for t in tokens:
        # (a second root is always an error, a sentence has one: "make the note red and bold" left "red" a root;
        # it is moved under the first)
        extra_root = t.head == 0 and roots and t.i != roots[0]
        if not extra_root and (_base(t.deprel) not in MOVABLE or t.upos not in CONTENT + ("PROPN", "NUM", "X", "PRON")):
            continue
        cands = set(_ancestors(heads, t.i)[1:])  # raise: any ancestor above the current head
        if extra_root:
            cands.add(roots[0])
        # lower: a noun or verb to the left whose subtree ends right before this dependent's phrase
        cands |= {u.i for u in tokens if u.i < t.i and u.upos in ("NOUN", "PROPN", "VERB", "ADV") and u.i != t.head}
        for h in sorted(cands):
            new = list(heads)
            new[t.i - 1] = h
            if h == t.i or not _acyclic(new):
                continue
            proj = _projective(new)
            if not proj and not step:
                continue
            out.append((new, [f"{t.form}: {tokens[t.head - 1].form if t.head else 'ROOT'}->{tokens[h - 1].form}"],
                        [t.i], proj))
    return out


def _label_word(t) -> bool:
    """A word the builder's catalog uses as the label of a field, a property or an element type ("text", "fundo",
    "heading"), or a field of the frames: it names something of the element, not a state of it."""
    from . import lexicon
    from .base import FRAMES
    from .values import fold

    lem = lexicon.lemma_of(t.form)
    if fold(lem) in {fold(k) for k in FRAMES["campos"]}:
        return True
    return any(e.lemmas == (lem,) for e, _ in lexicon.match((lem,), {"campo", "propriedade", "tipo"}))


def _span_variants(tokens) -> list:
    """An object phrase that ends with a value word after a noun, however the parser headed it ("make the package 1
    heading italic" with "package" as the head): the noun before the value heads the object, the words before it
    are its modifiers, and the value word is the verb's secondary predicate. One edit: (arcs, edits)."""
    from .values import fold, index

    out = []
    kids = {}
    for t in tokens:
        kids.setdefault(t.head, []).append(t)

    def subtree(i):
        found, stack = [], [i]
        while stack:
            k = stack.pop()
            found.append(k)
            stack += [c.i for c in kids.get(k, [])]
        return sorted(found)

    by_i = {t.i: t for t in tokens}
    for o in tokens:
        verb = by_i.get(o.head)
        if verb is None or verb.upos != "VERB" or _base(o.deprel) != "obj":
            continue
        span = subtree(o.i)
        if len(span) < 3 or span[-1] - span[0] != len(span) - 1:
            continue
        e, n = by_i[span[-1]], by_i[span[-2]]
        value = e.upos == "ADJ" or bool(index().get(fold(e.form.lower())))
        if not value or _label_word(e) or is_literal(e.form) or n.upos not in ("NOUN", "PROPN") or \
                (e.head == verb.i and n.head == verb.i):
            continue
        arcs = [(t.head, t.deprel) for t in tokens]
        arcs[e.i - 1] = (verb.i, "xcomp")
        arcs[n.i - 1] = (verb.i, "obj")
        for k in span[:-2]:
            t = by_i[k]
            rel = "det" if t.upos == "DET" else "nummod" if t.upos == "NUM" else \
                t.deprel if _base(t.deprel) in ("case", "det") else "compound"
            if t.upos == "ADP" or _base(t.deprel) == "case":
                continue
            arcs[k - 1] = (n.i, rel)
        out.append((arcs, [f"{e.form}: predicado de {verb.form}; {n.form} núcleo do objeto"]))
    return out


def _rehead_variants(tokens) -> list:
    """An object whose last word the parser made its head, though it is the state the verb gives the object ("make
    the Sobre nós section background yellow", "make the Fachada image 500px wide": the head is "yellow", "wide"): the
    noun before it becomes the object's head, keeping the words before it, and the last word becomes the verb's
    secondary predicate (xcomp), keeping the words between them ("500px wide"). One edit: (arcs, edits)."""
    out = []
    by_i = {t.i: t for t in tokens}
    for h in tokens:
        kids = [t for t in tokens if t.head == h.i]
        if any(_base(t.deprel) == "cop" for t in kids) and h.upos in ("NOUN", "ADJ") and not _label_word(h):
            # a copular clause ("is the note italic?", "the note italic" parsed as one phrase): the noun before the
            # predicate word is its subject
            nouns = [t for t in kids if t.i < h.i and t.upos in ("NOUN", "PROPN") and
                     _base(t.deprel) in ("compound", "amod", "flat", "nmod")]
            if nouns:
                n = max(nouns, key=lambda t: t.i)
                arcs = [(t.head, t.deprel) for t in tokens]
                arcs[n.i - 1] = (h.i, "nsubj")
                for t in kids:
                    if t is not n and t.i < n.i and _base(t.deprel) not in ("cop", "aux"):
                        arcs[t.i - 1] = (n.i, t.deprel)
                out.append((arcs, [f"{n.form}: sujeito de {h.form}"]))
            continue
        verb = by_i.get(h.head)
        if verb is None or verb.upos != "VERB" or _base(h.deprel) != "obj" or h.upos not in ("NOUN", "ADJ", "PROPN"):
            continue
        # the mirror case: the predicate word hung after the object's head ("make the Intro paragraph 400px wide"
        # with "wide" under "paragraph"): it goes to the verb, with the words between them
        last = max(tokens, key=lambda t: t.i)
        if last.head == h.i and last.i > h.i and last.upos in ("NOUN", "ADJ") and not _label_word(last) and \
                _base(last.deprel) in ("nmod", "amod", "flat", "compound", "appos") and not is_literal(last.form):
            arcs = [(t.head, t.deprel) for t in tokens]
            arcs[last.i - 1] = (verb.i, "xcomp")
            for t in kids:
                if h.i < t.i < last.i:
                    arcs[t.i - 1] = (last.i, "obl:npmod" if is_literal(t.form) else t.deprel)
            out.append((arcs, [f"{last.form}: de {h.form} -> predicado de {verb.form}"]))
        nouns = [t for t in kids if t.i < h.i and t.upos in ("NOUN", "PROPN") and
                 _base(t.deprel) in ("compound", "amod", "flat", "nmod")]
        if not nouns or _label_word(h):
            continue  # (a word that names a part or a property, "the card text", "the section background", is no state)
        n = max(nouns, key=lambda t: t.i)  # (the noun right before the predicate word heads the object)
        arcs = [(t.head, t.deprel) for t in tokens]
        arcs[n.i - 1] = (verb.i, "obj")
        arcs[h.i - 1] = (verb.i, "xcomp")
        for t in kids:
            if t is not n and t.i < n.i:
                arcs[t.i - 1] = (n.i, t.deprel)  # (the article and the other modifiers go with the object)
        for t in tokens:
            if t.head == n.i and t.i > n.i and t.i < h.i:
                arcs[t.i - 1] = (h.i, "obl:npmod" if is_literal(t.form) else t.deprel)  # ("500px wide")
        out.append((arcs, [f"{h.form}: objeto -> predicado de {verb.form}"]))
    return out


_PAGE_NAMES: list = [()]  # the multiword names of the elements of the page being talked about (a stack)


class page_names:
    """While reading requests about a page, its elements' multiword names ("Massas frescas", "Ver mais") are lexical
    units: one proper name each, as a quoted literal is one value, whatever the words inside would be in the
    sentence's language ("make the Massas frescas heading smaller")."""

    def __init__(self, world) -> None:
        from .values import fold

        names = {(n.get("name") or "").strip() for n in world.nodes.values()} | \
            {n["text"].strip() for n in world.nodes.values()
             if isinstance(n.get("text"), str) and 1 < len(n["text"].split()) <= 6}
        self.names = tuple(sorted({tuple(fold(w.lower()) for w in tokenize(x)) for x in names
                                   if len(tokenize(x)) > 1}, key=len, reverse=True))

    def __enter__(self):
        _PAGE_NAMES.append(self.names)
        return self

    def __exit__(self, *exc):
        _PAGE_NAMES.pop()


def _fuse_names(words: list) -> list:
    """The words with each multiword name of the page joined into one word."""
    from .values import fold

    names = _PAGE_NAMES[-1]
    if not names:
        return words
    folded = [fold(w.lower()) for w in words]
    out, k = [], 0
    while k < len(words):
        hit = next((n for n in names if tuple(folded[k:k + len(n)]) == n), None)
        if hit is None:
            out.append(words[k])
            k += 1
            continue
        out.append(" ".join(words[k:k + len(hit)]))
        k += len(hit)
    return out


def analyses(text: str, limit: int = 200) -> list[Analysis]:
    """The greedy analysis first, then the alternatives in order of cost (number of edits)."""
    from .base import make_tokens

    tagger, parser, _, _ = _models()
    words = _fuse_names(tokenize(text))
    if not words:
        return []
    shown = [_shown(w) for w in words]
    tags = tagger.tag(shown)
    base = Analysis(make_tokens(words, tags, parser.parse(shown, tags)))
    found = [base]
    seen = {_key(base.tokens)}

    def add(tokens, cost, edits):
        k = _key(tokens)
        if k not in seen:
            seen.add(k)
            found.append(Analysis(tokens, cost, edits))

    tag_trees = [base]
    for new_tags, edits in _tag_variants(words, tags):
        a = Analysis(_parsed(words, new_tags), EDIT_COST * len(edits), edits)
        if _key(a.tokens) not in seen:
            add(a.tokens, a.cost, a.edits)
            tag_trees.append(a)
    # a head-final object re-headed as object + secondary predicate ("make the section background yellow")
    for a in list(tag_trees):
        for arcs, edits in _rehead_variants(a.tokens) + _span_variants(a.tokens):
            b = Analysis(make_tokens(words, [t.upos for t in a.tokens], arcs), a.cost + EDIT_COST, a.edits + edits)
            if _key(b.tokens) not in seen:
                add(b.tokens, b.cost, b.edits)
                tag_trees.append(b)
    # one move on every tree, then a second move on the trees that needed at most one edit before
    frontier = tag_trees
    stepped = set()
    for round_ in range(2):
        moved_trees = []
        for a in frontier:
            if a.cost + EDIT_COST > 2 * EDIT_COST:
                continue
            wtags = [t.upos for t in a.tokens]
            for heads, edits, moved, proj in _attachment_variants(a.tokens, step=round_ == 0):
                rels = [t.deprel for t in a.tokens]
                for d in moved:
                    rels[d - 1] = _relabel(words, wtags, heads, d)
                b = Analysis(make_tokens(words, wtags, list(zip(heads, rels))), a.cost + EDIT_COST * len(edits),
                             a.edits + edits)
                k = _key(b.tokens)
                if proj and k not in seen:
                    add(b.tokens, b.cost, b.edits)
                    moved_trees.append(b)
                elif not proj and k not in stepped:
                    stepped.add(k)
                    moved_trees.append(b)  # only a step: never an analysis by itself
        frontier = moved_trees
    found.sort(key=lambda a: a.cost)
    return found[:limit]


def _key(tokens) -> tuple:
    return tuple((t.upos, t.head, t.deprel) for t in tokens)
