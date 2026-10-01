"""A1: hierarchical generation and learned ranking of grounded actions (roteiro CCG; Branavan et al. 2009; Artzi &
Zettlemoyer 2013).

Search, never a full cartesian product:

    utterance -> lexical evidence (data: nucleo/lang/evidencia.py) + the learned lexicon (an inverted index of the
    learned weights) -> plausible operations (by their own evidence and by the evidence for the *types* of their
    slots) -> plausible targets (page nodes and discourse entities) -> only the slots each operation's ActionSchema
    declares, filled only with values of the right type that apply to the target (W3C grammar; the builder's own
    element predicates) -> composition -> ranking.

The **generator** orders its candidates with the component features (each slot scored on its own); the **ranker**
re-scores them with the cross features as well (operation x target type, property x target type, value
operation x property, operation x kind of reference, continuity of the property). The same weight vector serves
both; it is learned with an averaged structured perceptron (Collins 2002) on TRAIN, with the gold's features
computed directly (forced decoding) — in DEV/TEST nothing about the gold is ever used.

Feature families (an ablation drops one): ``lex`` (word x atom: the learned lexicon), ``ev`` (data evidence, by
origin), ``struct`` (ranks, ancestors, positions, cross features, applicability), ``ctx`` (selection and discourse).
No word, phrase or synonym is written in this file.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache

from . import esquema as E
from . import evidencia as EV
from . import ir
from .mundo import Discourse, Page, holds_children
from .values import fold

SUPPORTED = {"node", "nodes", "property", "string", "palette-entry", "integer", "json", "enum", "number", "color",
             "boolean"}
NUM = re.compile(r"^-?\d+(?:[.,]\d+)?$")
NUM_UNIT = re.compile(r"^(-?\d+(?:[.,]\d+)?)([a-z%]+)$")
STEP = "1.25"  # the relative step of "a bit more/less" (a major third of the type scale): a candidate, not a rule
UNITS = ("px", "%", "em", "rem", "")
WIDTH = {"ops": 14, "targets": 6, "pairs": 24, "types": 4, "dests": 4, "spans": 6, "beam": 12}
# word classes (from the trained tagger) whose words may describe an entity, or a change of quantity: a
# syntactic restriction of which words a feature pairs with, never a list of words
NOMINAL = frozenset({"NOUN", "PROPN", "ADJ", "NUM", "DET", "PRON", "X"})
PREDICATIVE = frozenset({"VERB", "AUX", "ADJ", "ADV"})
ACTING = frozenset({"VERB", "AUX", "ADV", "PART", "INTJ"})  # words that may name or deny an action
CONTENT = frozenset({"NOUN", "ADJ", "VERB", "ADV", "X"})  # words that may name a property or a value

# Initial weights of *kinds* of data evidence (never of a word): they only start positive, as UBL's lexical weights
# start from co-occurrence; learning changes them. Audited in experiments/a1/auditoria.py.
INIT = {("op-lab",): 1.0, ("prop-lab",): 1.0, ("val-lab",): 1.0, ("type-lab",): 1.0, ("lit",): 1.0}
for _o in EV.ORIGINS:
    for _k in EV.KINDS:
        INIT[("ev", _o, _k)] = 1.0
for _r in ("tgt", "dest", "ref"):
    INIT.update({(f"{_r}-name",): 3.0, (f"{_r}-text",): 3.0, (f"{_r}-desc-text",): 1.5, (f"{_r}-anc-name",): 1.0})


def family(k: tuple) -> str:
    """The family of a feature, for the ablations."""
    h = k[0]
    if h in ("ev", "op-lab", "prop-lab", "val-lab", "type-lab") or h.endswith("-ev"):
        return "ev"
    if h.startswith("x-") or "-rank" in h or "-anc" in h or "-last" in h or h.startswith("pos") or \
            h.startswith("before") or h in ("na-soft", "unique") or h.endswith("-unique"):
        return "struct"
    if h.endswith(("-sel", "-ctx", "-other", "-recent", "-created", "-group", "-w-sel", "-w-ctx", "-w-other")) or \
            h in ("rep", "rep-bias", "same-prop"):
        return "ctx"
    return "lex"


# -- the utterance ------------------------------------------------------------------------------------------------
@dataclass
class Tok:
    i: int
    form: str
    keys: tuple  # lemma(s), folded form, typo corrections
    upos: str
    head: int = 0
    deprel: str = ""
    case: str = "-"  # the preposition that marks the word's phrase ("para o rodapé": "para")


def _catalog_words() -> frozenset:
    return frozenset(EV.catalog_index().keys())


def _known(word: str, lang: str, vocab: frozenset) -> bool:
    if word in vocab or len(word) <= 3:
        return True
    try:
        if lang == "pt":
            from .morph import analyses
            return bool(analyses(word))
        from . import langs
        return word in langs._english_words()
    except Exception:  # noqa: BLE001
        return True


def _edit1(a: str, b: str) -> bool:
    if abs(len(a) - len(b)) > 1 or a == b:
        return False
    if len(a) == len(b):
        d = [i for i in range(len(a)) if a[i] != b[i]]
        return len(d) == 1 or (len(d) == 2 and d[1] == d[0] + 1 and a[d[0]] == b[d[1]] and a[d[1]] == b[d[0]])
    s, lng = (a, b) if len(a) < len(b) else (b, a)
    return any(lng[:i] + lng[i + 1:] == s for i in range(len(lng)))


def analyse(text: str, lang: str, vocab: frozenset) -> list[Tok]:
    """Tokens with tags from the trained tagger and every lemma the morphology allows (MorphoBr for Portuguese, the
    EWT lemma table for English): ambiguity is kept for learning to resolve, never decided by a word list."""
    from . import langs
    from .base import _models_for
    from .tokenize import tokenize_data

    with langs.use(lang):
        tagger, parser, lem, _ = _models_for(lang)
        words = tokenize_data(text, lang)
        tags = tagger.tag(words)
        arcs = parser.parse(words, tags) if words else []
        out = []
        for i, (w, t) in enumerate(zip(words, tags), 1):
            form = fold(w.lower())
            keys = [fold(lem.lemma(w, t).lower()), form]
            if lang == "pt":
                from .morph import analyses
                keys += [fold(le) for le, _ in analyses(w.lower())][:4]
            else:
                keys.append(fold(langs.english_lemma(w.lower(), t)))
            if t not in ("PUNCT", "NUM") and not _known(form, lang, vocab):
                keys += sorted(x for x in vocab if len(x) > 3 and _edit1(form, x))[:3]
            head, rel = arcs[i - 1] if i - 1 < len(arcs) else (0, "")
            out.append(Tok(i, w, tuple(dict.fromkeys(k for k in keys if k)), t, head, rel.split(":")[0]))
    for t_ in out:
        for c in out:
            if c.head == t_.i and c.deprel in ("case", "mark") and c.i < t_.i:
                t_.case = c.keys[0]
                break
    return out


@lru_cache(maxsize=4)
def negation_words(lang: str) -> frozenset:
    """The words the UD treebanks mark Polarity=Neg or PronType=Neg (at least 1% of those tokens): data, not a
    list."""
    from collections import Counter

    from .ud import load

    banks = ("ewt",) if lang == "en" else ("bosque", "petrogold", "porttinari")
    try:
        c = Counter(fold(w.form.lower()) for s in load("train", banks) for w in s.words
                    if "Polarity=Neg" in w.feats or "PronType=Neg" in w.feats)
    except Exception:  # noqa: BLE001
        return frozenset()
    total = sum(c.values())
    return frozenset(w for w, n in c.items() if n >= 0.01 * total)


# -- the domain's typed constants --------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _keywords() -> dict:
    from . import values as V

    allkw, colors = V._all_keywords(), set(V.named_colors())
    return {p: sorted(set(allkw.get(p, ())) | (colors if "color" in p else set())) for p in E.properties()}


@lru_cache(maxsize=1)
def _numeric_props() -> frozenset:
    from . import values as V

    kinds = V._all_literal_kinds()
    return frozenset(p for p in E.properties()
                     if set(kinds.get(p, ())) & {"length", "length-percentage", "number", "integer", "percentage"})


@lru_cache(maxsize=1)
def _label_words() -> dict:
    lw = lambda s: frozenset(fold(w) for w in re.findall(r"[^\W\d_]+", s.lower()))  # noqa: E731
    return {"op": {k: lw(" ".join(s.labels.values())) for k, s in E.schemas().items()},
            "prop": {k: lw(" ".join(v["label"].values()) + " " + k.replace("-", " ")) for k, v in
                     E.properties().items()},
            "type": {k: lw(" ".join(v["label"].values()) + " " + re.sub(r"([A-Z])", r" \1", k)) for k, v in
                     E.element_types().items()}}


def has_target(sc) -> bool:
    """Whether an operation acts on a node: it takes a target, acts on the selection, or was observed to change
    nodes without creating one (a palette-entry argument creates)."""
    if sc.acts_on_selection() or any(a.name in ("target", "targets") for a in sc.args):
        return True
    return not any(a.type == "palette-entry" for a in sc.args) and any(w.startswith("node:") for w in sc.writes)


def usable(sc) -> bool:
    return all(a.type in SUPPORTED for a in sc.args if not a.optional)


def _merge(*ds) -> dict:
    out: dict = defaultdict(float)
    for d in ds:
        for k, v in d.items():
            out[k] += v
    return out


def _words(text) -> frozenset:
    return frozenset(fold(w) for w in re.findall(r"[^\W\d_]+", (text or "").lower()))


# -- per-utterance analysis and features ---------------------------------------------------------------------------
class Context:
    def __init__(self, text: str, lang: str, page: Page, disc: Discourse, vocab: frozenset, off: frozenset):
        self.lang, self.page, self.disc, self.off = lang, page, disc, off
        self.toks = analyse(text, lang, vocab)
        self.surface = [t.form for t in self.toks]
        self.lemmas = [t.keys[0] for t in self.toks]
        self.words = frozenset(k for t in self.toks for k in t.keys)
        self.ev: dict = defaultdict(float)  # (kind, target, origin) -> strength
        if "ev" not in off:
            for t in self.toks:
                for k in t.keys[:3]:
                    for kind, target, st, origin in EV.evidence(k, lang):
                        key = (kind, target, origin)
                        self.ev[key] = max(self.ev[key], st)
        self.tok_types = []  # per token: the element types its words have evidence for
        for t in self.toks:
            ts = set()
            if "ev" not in off:
                for k in t.keys[:3]:
                    ts |= {target for kind, target, st, o in EV.evidence(k, lang) if kind == "type" and st >= 0.3}
            self.tok_types.append(ts)
        neg = negation_words(lang)
        self.negated = any(k in neg for t in self.toks for k in t.keys[:2])
        self.by_kind: dict = defaultdict(dict)  # kind -> target -> {origin: strength}
        for (kind, target, origin), st in self.ev.items():
            self.by_kind[kind].setdefault(target, {})[origin] = st
        self.nums = []
        for k, t in enumerate(self.toks):
            m = NUM_UNIT.match(t.form.lower())
            if m:
                self.nums.append((float(m.group(1).replace(",", ".")), m.group(2), k))
                continue
            # (a number word counts only where the tagger reads a numeral: "um pouco" is not the number one)
            n = EV.number(fold(t.form.lower()), lang) if t.upos == "NUM" or NUM.match(t.form) else None
            if n is not None:
                nxt = self.toks[k + 1].keys[0] if k + 1 < len(self.toks) else None
                self.nums.append((n, None, k, nxt) if nxt else (n, None, k))
        self._node: dict = {}
        # which kinds of slot evidence the utterance has (an operation learns which kinds it takes)
        self.slot_ev = {k for k, present in (("prop", bool(self.by_kind.get("prop") or self.by_kind.get("value"))),
                                             ("type", bool(self.by_kind.get("type"))), ("num", bool(self.nums)))
                        if present}

    def _f(self, d: dict) -> dict:
        return d if not self.off else {k: v for k, v in d.items() if family(k) not in self.off}

    def lex(self, prefix: str, atom, pos: frozenset | None = None) -> dict:
        """The learned lexicon: each word of the utterance (of the given word classes) paired with an atom."""
        if pos is None:
            return {(prefix, k, atom): 1.0 for k in self.lemmas}
        # (the first word of a request is its verb even when the tagger misses it: "troca", "undo")
        return {(prefix, t.keys[0], atom): 1.0 for j, t in enumerate(self.toks)
                if t.upos in pos or (pos is ACTING and j == 0)}

    def evf(self, kind: str, target) -> dict:
        return {("ev", o, kind): st for o, st in self.by_kind.get(kind, {}).get(target, {}).items()}

    def lab(self, kind: str, target) -> float:
        words = _label_words()[kind].get(target, frozenset())
        return float(min(2, sum(1 for t in self.toks if t.upos not in ("DET", "ADP", "PUNCT", "CCONJ", "PRON") and
                                any(k in words for k in t.keys))))

    # components (generator features)
    def op(self, sid: str) -> dict:
        sc = E.schemas()[sid]
        return self._f(_merge(self.lex("op", sid, ACTING), self.lex("ns", sc.namespace, ACTING), self.evf("op", sid),
                              {("op-bias", sid): 1.0, ("op-lab",): self.lab("op", sid)},
                              {("op-slotev", sid, k): 1.0 for k in sorted(self.slot_ev)}))

    def node(self, n: str, role: str) -> dict:
        key = (n, role)
        if key not in self._node:
            self._node[key] = self._f(self._node_feats(n, role))
        return self._node[key]

    def _node_feats(self, n: str, role: str) -> dict:
        page, disc = self.page, self.disc
        nd = page.nodes[n]
        f: dict = defaultdict(float)
        typ = nd["type"]
        for k in self.lex(f"{role}-type", typ, NOMINAL):
            f[k] += 1.0
        for k, v in self.evf("type", typ).items():
            f[(f"{role}-ev",) + k[1:]] += v
        f[(f"{role}-lab-type",)] += self.lab("type", typ)
        for field in ("name", "text"):
            ws = _words(nd.get(field) if isinstance(nd.get(field), str) else "")
            if ws:
                f[(f"{role}-{field}",)] += sum(1 for w in ws if w in self.words) / len(ws)
        desc, stack = set(), list(nd.get("children", []))
        while stack:
            x = stack.pop()
            if isinstance(x.get("text"), str):
                desc |= _words(x["text"])
            stack += x.get("children", [])
        if desc:
            f[(f"{role}-desc-text",)] += sum(1 for w in desc if w in self.words) / len(desc)
        own = _words(nd.get("name")) | _words(nd.get("text") if isinstance(nd.get("text"), str) else "")
        for j, tk in enumerate(self.toks):
            if (own and any(k in own for k in tk.keys)) or typ in self.tok_types[j]:
                f[(f"{role}-dep", tk.deprel)] += 1.0
                f[(f"{role}-case", tk.case)] += 1.0
                f[(f"{role}-dep-case", tk.deprel, tk.case)] += 1.0
        same = page.of_type(typ)
        rank = same.index(n) + 1
        for k in self.lex(f"{role}-rank", min(rank, 4), NOMINAL):
            f[k] += 1.0
        if rank == len(same) and len(same) > 1:
            for k in self.lex(f"{role}-last", True, NOMINAL):
                f[k] += 1.0
        if len(same) == 1:
            f[(f"{role}-unique",)] += 1.0
        anc, depth = page.parent.get(n), 1
        while anc is not None and depth <= 3:
            at = page.nodes[anc]["type"]
            for k in self.lex(f"{role}-anc-type", at, NOMINAL):
                f[k] += 1.0 / depth
            for k in self.lex(f"{role}-anc-rank", min(page.of_type(at).index(anc) + 1, 4), NOMINAL):
                f[k] += 1.0 / depth
            an = _words(page.nodes[anc].get("name"))
            if an:
                f[(f"{role}-anc-name",)] += sum(1 for w in an if w in self.words) / len(an) / depth
            for j, tk in enumerate(self.toks):
                if (an and any(k in an for k in tk.keys)) or at in self.tok_types[j]:
                    f[(f"{role}-anc-dep", tk.deprel, tk.case)] += 1.0 / depth
            anc, depth = page.parent.get(anc), depth + 1
        # selection and discourse
        if n in page.selection:
            f[(f"{role}-sel",)] += 1.0
            for k in self.lex(f"{role}-w-sel", True, NOMINAL):
                f[k] += 1.0
        if n == disc.referent:
            f[(f"{role}-ctx",)] += 1.0
            for k in self.lex(f"{role}-w-ctx", True, NOMINAL):
                f[k] += 1.0
        elif disc.referent in page.nodes and page.nodes[disc.referent]["type"] == typ:
            f[(f"{role}-other",)] += 1.0
            for k in self.lex(f"{role}-w-other", True, NOMINAL):
                f[k] += 1.0
        if n in disc.mentioned:
            f[(f"{role}-recent", min(len(disc.mentioned) - 1 - disc.mentioned[::-1].index(n) + 1, 3))] += 1.0
        if n in disc.created:
            f[(f"{role}-created",)] += 1.0
        if disc.container and page.parent.get(n) == disc.container:
            f[(f"{role}-group",)] += 1.0
        return f

    def prop(self, p: str) -> dict:
        f = _merge(self.lex("prop", p, CONTENT), self.evf("prop", p),
                   {("prop-bias", p): 1.0, ("prop-lab",): self.lab("prop", p)})
        for part in p.split("-"):
            for k in self.lex("prop-part", part, CONTENT):
                f[k] += 1.0
        return self._f(f)

    def value(self, p: str, v: ir.Value) -> dict:
        if v.op in ("MUL", "DIV"):
            return self._f(_merge(self.lex("vop", v.op, PREDICATIVE), {("step",): 1.0}))
        q = ir.quantity(v.data)
        if q is not None and p in _numeric_props() and str(v.data) not in _keywords().get(p, ()):
            num, unit = q
            f = _merge(self.lex("vop", v.op, PREDICATIVE), {("unit", unit): 1.0})
            said = [x for x in self.nums if x[0] == num]
            if said:
                f[("lit",)] += 1.0
                k = said[0][2]
                prev = self.toks[k - 1].keys[0] if k > 0 else "<s>"
                f[("lit-prev", prev, v.op)] += 1.0  # (the word that governs the number: "em 30px", "para 30px")
                if said[0][1]:
                    f[("unit-said",)] += 1.0
                    if said[0][1] != unit:
                        f[("unit-other",)] += 1.0
                elif len(said[0]) > 3:
                    f[("unit-word", said[0][3], unit)] += 1.0
            else:
                f[("lit-missing",)] += 1.0
            return self._f(f)
        kw = str(v.data)
        return self._f(_merge(self.lex("val", kw, CONTENT), self.lex("vop", v.op, PREDICATIVE), self.evf("value", (p, kw)),
                              {("val-lab",): 1.0 if fold(kw) in self.words else 0.0}))

    def new_type(self, typ: str) -> dict:
        return self._f(_merge(self.lex("new-type", typ, NOMINAL), self.evf("type", typ),
                              {("type-lab",): self.lab("type", typ)}))

    def span(self, text: str, slot: str) -> dict:
        ws = text.split()
        for a in range(len(self.surface)):
            if self.surface[a:a + len(ws)] == ws:
                b = a + len(ws)
                prev = self.toks[a - 1].keys[0] if a > 0 else "<s>"
                end = b == len(self.toks) or all(x.upos == "PUNCT" for x in self.toks[b:])
                return {("span-end",): 1.0 if end else 0.0, ("span-end-prev", prev, end): 1.0,
                        ("span-cap",): 1.0 if self.surface[a][:1].isupper() else 0.0, ("span-prev", prev, slot): 1.0}
        return {("span-missing",): 1.0}

    def position(self, dest: str, index: int) -> dict:
        kids = [c["id"] for c in self.page.nodes[dest]["children"]]
        f: dict = defaultdict(float)
        if index == 0:
            for k in self.lex("pos", "start"):
                f[k] += 1.0
        if index == len(kids):
            for k in self.lex("pos", "end"):
                f[k] += 1.0
        if 0 < index <= len(kids):
            for k, v in self.node(kids[index - 1], "ref").items():
                f[k] += 0.5 * v
            for k in self.lex("pos", "after"):
                f[k] += 1.0
        if index < len(kids):
            for k, v in self.node(kids[index], "ref").items():
                f[("before",) + k] += 0.5 * v
            for k in self.lex("pos", "before"):
                f[k] += 1.0
        return self._f(f)

    # cross features (ranker only)
    def cross(self, a: ir.Action) -> dict:
        f: dict = defaultdict(float)
        tnode = a.target.node if a.target is not None and a.target.kind == "node" else None
        ttype = self.page.nodes[tnode]["type"] if tnode in self.page.nodes else (
            a.target.type if a.target is not None else None)
        prop = a.arg("property")
        if prop is not None:
            if prop.data == self.disc.last_property:
                f[("same-prop",)] += 1.0
        dest = a.arg("parent")
        if tnode is not None and isinstance(dest, ir.Ref) and dest.node == tnode:
            f[("x-target-dest",)] += 1.0
        refkind = "none" if tnode is None else ("ctx" if tnode == self.disc.referent else
                                                 "sel" if tnode in self.page.selection else "explicit")
        f[("x-op-ref", a.op, refkind)] += 1.0
        if self.negated:
            f[("x-negated-act",)] += 1.0  # (a negated request acts on nothing: learned, from the treebanks' words)
        return self._f(f)


def components(cx: Context, a: ir.Action | None, kind: str = "act") -> dict:
    """The generator features of a grounded action (component by component)."""
    if a is None:
        return _merge(cx.lex("none", True, ACTING), {("none-bias",): 1.0,
                                                      ("none-negated",): 1.0 if cx.negated else 0.0})
    f = cx.op(a.op) if kind == "act" else cx._f(_merge(cx.lex("rep", True), {("rep-bias",): 1.0}))
    f = _merge(f, cx.lex("act", True, ACTING))
    if a.target is not None and a.target.kind == "node" and a.target.node in cx.page.nodes:
        f = _merge(f, cx.node(a.target.node, "tgt"))
    if a.target is not None and a.target.kind == "new":
        f = _merge(f, cx.new_type(a.target.type))
    if kind != "act":
        return f
    prop = a.arg("property")
    for name, v in a.args:
        if name == "property":
            f = _merge(f, cx.prop(v.data))
        elif name == "value" and prop is not None:
            f = _merge(f, cx.value(prop.data, v))
        elif isinstance(v, ir.Ref) and v.kind == "node":
            f = _merge(f, cx.node(v.node, "dest"))
        elif name == "index":
            dest = a.arg("parent")
            if isinstance(dest, ir.Ref):
                f = _merge(f, cx.position(dest.node, int(v.data)))
        elif isinstance(v, ir.Value):
            f = _merge(f, cx.span(str(v.data), name))
    return f


def featurize(cx: Context, a: ir.Action | None, kind: str = "act") -> dict:
    f = components(cx, a, kind)
    return f if a is None else _merge(f, cx.cross(a))


@dataclass
class Cand:
    action: ir.Action | None
    feats: dict  # generator features
    kind: str = "act"
    seg: int | None = None  # the conjunct it was generated for (None: the whole utterance)
    gen: float = 0.0  # generator score
    full: dict = None  # ranker features

    def canonical(self) -> str:
        """The meaning that is carried out: a negated action carries out nothing."""
        return "NONE" if self.action is None or self.action.negated else self.action.canonical()

    def ir(self) -> str:
        return "NONE" if self.action is None else self.action.canonical()


class Ranker:
    def __init__(self, off: frozenset = frozenset()) -> None:
        self.off = off  # feature families switched off (ablation)
        self.w: dict = defaultdict(float, {k: v for k, v in INIT.items() if family(k) not in off})
        self._tot: dict = defaultdict(float)
        self._ts: dict = defaultdict(int)
        self.t = 0
        self.vocab = _catalog_words()
        self.inv: dict = defaultdict(set)  # (prefix, lemma) -> atoms with a learned weight (the learned lexicon)
        self.stats = {"gen_secs": [], "rank_secs": [], "n": []}

    def score(self, feats: dict) -> float:
        return sum(self.w.get(k, 0.0) * v for k, v in feats.items())

    def context(self, text, lang, page, disc) -> Context:
        return Context(text, lang, page, disc, self.vocab, self.off)

    # -- retrieval ---------------------------------------------------------------------------------------------
    def _retrieved(self, cx: Context, prefix: str) -> set:
        out = set()
        for lm in (t.keys[0] for t in cx.toks if t.upos in CONTENT or t.upos == "PROPN"):
            out |= self.inv.get((prefix, lm), set())
        return out

    def _ops(self, cx: Context) -> list:
        schemas = E.schemas()
        pool = set(self._retrieved(cx, "op")) | set(cx.by_kind.get("op", {}))
        slot_kinds = {"prop": bool(cx.by_kind.get("prop") or cx.by_kind.get("value") or self._retrieved(cx, "prop")
                                   or self._retrieved(cx, "val") or cx.nums),
                      "type": bool(cx.by_kind.get("type") or self._retrieved(cx, "new-type"))}
        for sid, sc in schemas.items():
            types = {a.type for a in sc.args}
            if ("property" in types and slot_kinds["prop"]) or ("palette-entry" in types and slot_kinds["type"]):
                pool.add(sid)
        pool |= set(self._prior_ops())
        pool = [s for s in pool if s in schemas and usable(schemas[s])]
        scored = sorted(((s, cx.op(s)) for s in sorted(pool)), key=lambda x: (-self.score(x[1]), x[0]))
        # two retrievals: the operations with the best evidence of their own, and the best of those whose slots'
        # types have evidence (an operation named by its property or value only: "negrito no título")
        own = scored[:WIDTH["ops"]]
        wanted = ({"property"} if slot_kinds["prop"] else set()) | ({"palette-entry"} if slot_kinds["type"] else set())
        by_slot = [x for x in scored if x not in own and ({a.type for a in schemas[x[0]].args} & wanted)]
        by_slot = by_slot[:WIDTH["ops"] // 3]
        return own + by_slot

    def _prior_ops(self) -> list:
        bias = sorted(((self.w.get(("op-bias", s), 0.0), s) for s in E.schemas()), reverse=True)
        return [s for b, s in bias[:5] if b > 0]

    def _targets(self, cx: Context) -> list:
        page, disc = cx.page, cx.disc
        scored = sorted(((n, cx.node(n, "tgt")) for n in page.order), key=lambda x: (-self.score(x[1]), x[0]))
        keep = scored[:WIDTH["targets"]]
        have = {n for n, _ in keep}
        for n in [*page.selection[:1], disc.referent, *disc.created[-1:], *disc.mentioned[-3:]]:
            if n and n in page.nodes and n not in have and "ctx" not in self.off:
                keep.append((n, cx.node(n, "tgt")))
                have.add(n)
        return keep

    def _pairs(self, cx: Context, target: str | None) -> list:
        """(property, value) options that apply to the target: from evidence for properties and values, the learned
        lexicon, and numbers said; checked against the W3C grammar of the property and the builder's predicates."""
        props = set(cx.by_kind.get("prop", {})) | set(self._retrieved(cx, "prop")) | \
            {p for p, _ in cx.by_kind.get("value", {})} | {p for p, _ in self._retrieved(cx, "val-pair")} | \
            {p for _, p in sorted(((self.w.get(("prop-bias", p), 0.0), p) for p in E.properties()), reverse=True)[:5]}
        kw_ev = {pv for pv in cx.by_kind.get("value", {})} | self._retrieved(cx, "val-pair")
        blocked = cx.page.hard_na.get(target, set()) if target else set()
        per_prop = []
        for p in sorted(props):
            if p not in E.properties() or p in blocked:
                continue
            pf = cx.prop(p)
            vals = [kw for kw in _keywords().get(p, ()) if (p, kw) in kw_ev]
            opts = [ir.Value(kw) for kw in vals]
            if p in _numeric_props():
                for x in cx.nums:
                    for u in ([x[1]] if x[1] else UNITS):
                        opts += [ir.Value(ir.fmt(x[0], u), op) for op in ("SET", "ADD", "SUB")]
                opts += [ir.Value(STEP, "MUL"), ir.Value(STEP, "DIV")]
            if not opts:
                continue
            scored = sorted(((v, cx.value(p, v)) for v in opts),
                            key=lambda x: (-self.score(x[1]), x[0].canonical()))[:4]
            # (a property is as plausible as its own evidence and the best of its values)
            per_prop.append((self.score(pf) + self.score(scored[0][1]), p, pf, scored))
        per_prop.sort(key=lambda x: (-x[0], x[1]))
        out = []
        for _, p, pf, scored in per_prop[:WIDTH["pairs"] // 3]:
            out += [((p, v), _merge(pf, vf)) for v, vf in scored]
        return out

    def _types(self, cx: Context) -> list:
        pool = set(cx.by_kind.get("type", {})) | set(self._retrieved(cx, "new-type"))
        pool = {t for t in pool if t in set(E.palette().values())}
        return sorted(((t, cx.new_type(t)) for t in sorted(pool)), key=lambda x: (-self.score(x[1]), x[0]))[:WIDTH["types"]]

    def _dests(self, cx: Context) -> list:
        pool = [n for n in cx.page.order if holds_children(cx.page, n)]
        return sorted(((n, cx.node(n, "dest")) for n in pool), key=lambda x: (-self.score(x[1]), x[0]))[:WIDTH["dests"]]

    def _spans(self, cx: Context, slot: str) -> list:
        out, n = [], len(cx.surface)
        for a in range(n):
            for b in range(a + 1, min(n, a + 6) + 1):
                if any(t.upos == "PUNCT" for t in cx.toks[a:b]):
                    continue
                s = " ".join(cx.surface[a:b])
                out.append((ir.Value(s), cx._f(cx.span(s, slot))))
        for x in cx.nums:  # (a text slot may take a quantity said: "8px")
            for u in ([x[1]] if x[1] else UNITS[:1]):
                v = ir.fmt(x[0], u)
                out.append((ir.Value(v), cx._f({("span-num",): 1.0, ("unit", u): 1.0})))
        return sorted(out, key=lambda x: -self.score(x[1]))[:WIDTH["spans"]]

    # -- generation ----------------------------------------------------------------------------------------------
    def generate(self, cx: Context, _segment: bool = False, _seg: int | None = None) -> list[Cand]:
        t0 = time.perf_counter()
        extra: list = []
        if not _segment:
            cuts = [i for i, t in enumerate(cx.toks) if t.upos == "CCONJ"]
            cx.segments = 0
            if cuts:
                bounds = [0] + cuts + [len(cx.toks)]
                for a, b in zip(bounds, bounds[1:]):
                    seg = [t.form for t in cx.toks[a:b] if t.upos != "CCONJ"]
                    if len(seg) >= 2:
                        sub = Context(" ".join(seg), cx.lang, cx.page, cx.disc, self.vocab, self.off)
                        extra += self.generate(sub, True, cx.segments)
                        cx.segments += 1
        page = cx.page
        out = [Cand(None, components(cx, None), "none")]
        targets = self._targets(cx)
        if cx.disc.last and cx.disc.last.steps and "ctx" not in self.off:
            for n, _ in targets:
                for a in cx.disc.last.steps:
                    if a.target is not None and a.target.kind == "node" and a.target.node != n:
                        act = ir.Action(a.op, ir.Ref("node", n), a.args)
                        out.append(Cand(act, components(cx, act, "repeat"), "repeat"))
        types, dests = None, None
        # Context and weights stay fixed during this call. Each conjunct gets
        # its own cache when generate recurses, and the next call starts fresh.
        pairs_by_target: dict = {}
        for sid, of in self._ops(cx):
            sc = E.schemas()[sid]
            tlist = targets if has_target(sc) else [(None, {})]
            if any(a.type == "palette-entry" for a in sc.args):
                types = types if types is not None else self._types(cx)
                tlist = [(None, {})]
            for n, nf in tlist:
                creates = [(t, tf) for t, tf in (types or [])] if any(a.type == "palette-entry" for a in sc.args) \
                    else [(None, {})]
                for typ, tf in creates:
                    target = ir.Ref("node", n) if n is not None else (ir.Ref("new", type=typ) if typ else None)
                    partial = [({}, _merge(of, nf, tf, cx.lex("act", True, ACTING)))]
                    for spec in sc.args:
                        if spec.name in ("target", "targets") or spec.type == "palette-entry":
                            continue
                        if spec.type == "property":
                            if n not in pairs_by_target:
                                pairs_by_target[n] = self._pairs(cx, n)
                            opts = [({"property": ir.Value(p), "value": v}, f) for (p, v), f in pairs_by_target[n]]
                            partial = self._beam([(dict(a, **o), _merge(f, of_)) for a, f in partial
                                                  for o, of_ in opts])
                            continue
                        if sid == "style.set" and spec.name == "value":
                            continue  # (filled with its property)
                        if spec.type == "node":
                            dests = dests if dests is not None else self._dests(cx)
                            partial = self._beam([(dict(a, **{spec.name: ir.Ref("node", d)}), _merge(f, df))
                                                  for a, f in partial for d, df in dests])
                            continue
                        if spec.type == "integer" and spec.name == "index":
                            nxt = []
                            for a, f in partial:
                                d = a.get("parent")
                                if isinstance(d, ir.Ref):
                                    k = len(page.nodes[d.node]["children"])
                                    nxt += [(dict(a, index=ir.Value(i)), _merge(f, cx.position(d.node, i)))
                                            for i in range(k + 1)]
                            partial = self._beam(nxt) if nxt else partial
                            continue
                        if spec.type in ("string", "json"):
                            sp = self._spans(cx, spec.name)
                            partial = self._beam([(dict(a, **{spec.name: v}), _merge(f, vf))
                                                  for a, f in partial for v, vf in sp])
                            continue
                        if spec.type == "enum":
                            partial = self._beam([(dict(a, **{spec.name: ir.Value(v)}),
                                                   _merge(f, cx._f(cx.lex("enum", v))))
                                                  for a, f in partial for v in spec.values])
                            continue
                        if not spec.optional:
                            partial = []
                            break
                    for args, f in partial:
                        if "value" in args and "property" not in args:
                            continue
                        out.append(Cand(ir.Action(sid, target, tuple(sorted(args.items()))), f))
        # negation is an operator over actions: NOT(a) shares a's features and adds the negation's, so only the
        # negation decides between doing a and not doing it
        top = sorted((c for c in out if c.action is not None), key=lambda c: -self.score(c.feats))[:5]
        for c in top:
            neg = ir.Action(c.action.op, c.action.target, c.action.args, True)
            out.append(Cand(neg, _merge(c.feats, cx.lex("neg", True, ACTING),
                                        {("neg-bias",): 1.0, ("neg-negated",): 1.0 if cx.negated else 0.0}),
                            c.kind))
        for c in out:
            c.seg = _seg
        best: dict = {}
        for c in out + extra:
            c.gen = self.score(c.feats)
            k = c.ir()
            if k not in best or c.gen > best[k].gen:
                best[k] = c
        cands = sorted(best.values(), key=lambda c: (-c.gen, c.canonical()))
        if not _segment:
            self.stats["gen_secs"].append(time.perf_counter() - t0)
            self.stats["n"].append(len(cands))
        return cands

    def decode(self, cx: Context, ranked: list[Cand]) -> list[Cand]:
        """The plan the system chooses: nothing if nothing ranks first; else one action per conjunct of the
        utterance (the best candidate generated for it), or the best action."""
        if not ranked:
            return []
        if ranked[0].action is None or ranked[0].action.negated:
            return [ranked[0]]
        segs = getattr(cx, "segments", 0)
        if segs >= 2:
            out, seen = [], set()
            for i in range(segs):
                c = next((c for c in ranked if c.seg == i and c.action is not None and not c.action.negated and
                          c.canonical() not in seen), None)
                if c is not None:
                    out.append(c)
                    seen.add(c.canonical())
            if out:
                return out
        return [ranked[0]]

    def _beam(self, items: list) -> list:
        return sorted(items, key=lambda x: -self.score(x[1]))[:WIDTH["beam"]]

    def rank(self, cx: Context, cands: list[Cand]) -> list[Cand]:
        t0 = time.perf_counter()
        for c in cands:
            c.full = c.feats if c.action is None else _merge(c.feats, cx.cross(c.action))
        out = sorted(cands, key=lambda c: (-self.score(c.full), c.canonical()))
        self.stats["rank_secs"].append(time.perf_counter() - t0)
        return out

    # -- learning --------------------------------------------------------------------------------------------------
    def gold(self, cx: Context, a: ir.Action | None, cands: list | None = None) -> dict:
        if a is None:
            # nothing to do: the empty plan, or the negation of the action it denies (latent: the best scoring)
            opts = [featurize(cx, None)] + [c.full or c.feats for c in (cands or [])
                                             if c.action is not None and c.action.negated]
            return max(opts, key=self.score)
        opts = [featurize(cx, a, "act")]
        if cx.disc.last and any(x.op == a.op and x.args == a.args for x in cx.disc.last.steps):
            opts.append(featurize(cx, a, "repeat"))
        return max(opts, key=self.score)

    def update(self, gold: dict, guess: dict) -> None:
        self.t += 1
        for f, sign in ((gold, 1.0), (guess, -1.0)):
            for k, v in f.items():
                if family(k) in self.off:
                    continue
                self._tot[k] += (self.t - self._ts[k]) * self.w[k]
                self._ts[k] = self.t
                self.w[k] += sign * v
                if sign > 0 and len(k) == 3 and isinstance(k[1], str):
                    self.inv[(k[0], k[1])].add(k[2])  # (the learned lexicon's index: this word votes for the atom)

    def learn_pairs(self, cx: Context, a: ir.Action | None) -> None:
        """Remember (word, property-value) pairs of gold actions, so that a property/value seen with a word is
        retrieved for it again (the pair as one unit)."""
        if a is None:
            return
        p, v = a.arg("property"), a.arg("value")
        if p is not None and isinstance(v, ir.Value) and v.op == "SET" and ir.quantity(v.data) is None:
            for lm in cx.lemmas:
                self.inv[("val-pair", lm)].add((p.data, str(v.data)))

    def average(self) -> None:
        for k in list(self.w):
            self._tot[k] += (self.t - self._ts[k]) * self.w[k]
            if self.t:
                self.w[k] = self._tot[k] / self.t
