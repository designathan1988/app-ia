"""A1: list and rank the grounded actions an utterance can mean (roteiro CCG; Branavan et al. 2009; Artzi &
Zettlemoyer 2013).

**Candidates** are grounded IR actions built *by argument type* from the ActionSchema and the page: every operation
whose required arguments can be filled, a target among the page's nodes (or the selection / the entity of the
conversation), properties and values from the builder's manifest and the W3C grammars, literal numbers and text
spans of the utterance, palette types, destinations and positions. Also: nothing (the empty plan), and the last
plan of the conversation re-applied to another node. No candidate is made from a word.

**Scoring** is a linear model over features that pair what the utterance says (lemmas, literals, positions) with
what the candidate is (operation, namespace, property and its parts, value, element type, ordinal rank, ancestors,
descendants' text, selection, discourse). Every weight is learned from (utterance, action) pairs with a structured
perceptron (averaged; Collins 2002); the features of the gold action are computed directly ("forced decoding"), so
learning never depends on the pruning. Three kinds of evidence are *data*, not rules, and their weights are learned
like the others (they only start positive, as UBL's lexical weights start from co-occurrence):
  - string identity between a word and a word of the builder's own labels (its pt-BR and en catalogs);
  - the concept graph (ILI WordNets pt/en, Wiktionary): meanings of a word that reach a schema constant, with the
    path cost as the feature value (data-derived anchors only: command labels, types, properties, values);
  - for an unknown word, its nearest known words (edit distance 1) as alternative lemmas.

There is no list of words, phrases or synonyms in this file.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache

from . import esquema as E
from . import ir
from .mundo import Discourse, Page
from .values import fold

SUPPORTED = {"node", "nodes", "property", "string", "palette-entry", "integer", "json", "enum", "number", "color",
             "boolean"}
NUM = re.compile(r"^-?\d+(?:[.,]\d+)?$")
NUM_UNIT = re.compile(r"^(-?\d+(?:[.,]\d+)?)([a-z%]+)$")
STEP = "1.25"  # the relative step of "a bit more/less" (a major third of the type scale): a candidate, not a rule
UNITS = ("px", "%", "em", "rem", "")

# initial weights of the evidence features (data-derived); learning changes them like any other weight
INIT = {("op-lab",): 1.0, ("op-g",): 1.0, ("prop-lab",): 1.0, ("prop-g",): 1.0, ("val-lab",): 2.0, ("val-g",): 1.5,
        ("lit",): 1.0, ("new-lab-type",): 1.0, ("new-g-type",): 1.0}
for _r in ("tgt", "dest", "ref"):
    INIT.update({(f"{_r}-name",): 3.0, (f"{_r}-text",): 3.0, (f"{_r}-desc-text",): 1.5, (f"{_r}-lab-type",): 1.0,
                 (f"{_r}-g-type",): 1.0, (f"{_r}-anc-name",): 1.0, (f"{_r}-anc-g-type",): 0.5})


# -- the utterance ------------------------------------------------------------------------------------------------
@dataclass
class Tok:
    i: int
    form: str
    keys: tuple  # folded lemma, folded form, alternatives (typo corrections, homographs)
    upos: str


def _catalog_words(lang: str) -> set:
    out = set()
    for v in E.catalog(lang).values():
        if isinstance(v, str):
            out.update(fold(w) for w in re.findall(r"[^\W\d_]+", v.lower()))
    return out


@lru_cache(maxsize=1)
def _label_vocab() -> frozenset:
    return frozenset(_catalog_words("pt") | _catalog_words("en"))


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
    from . import langs
    from .base import analyse as ud

    with langs.use(lang):
        toks = ud(text)
    out = []
    for t in toks:
        form = fold(t.form.lower())
        keys = [fold((t.lemma or t.form).lower()), form] + [fold(a.lower()) for a in getattr(t, "alts", ())]
        if t.upos not in ("PUNCT", "NUM") and not _known(form, lang, vocab):
            keys += sorted(w for w in vocab if len(w) > 3 and _edit1(form, w))[:3]
        out.append(Tok(t.i, t.form, tuple(dict.fromkeys(k for k in keys if k)), t.upos))
    return out


# -- data-derived priors -------------------------------------------------------------------------------------------
@lru_cache(maxsize=50_000)
def _graph(word: str, lang: str) -> tuple:
    """Meanings of a word that reach a schema constant through data (graph, dictionary, catalog): (kind, target,
    cost). The frames' hand-written verb lists are not used."""
    from . import grounding, langs

    out = []
    try:
        with langs.use(lang):
            for m in grounding.meanings(word, lang=lang):
                if m.kind in ("comando", "tipo", "propriedade", "valor") and not any(
                        how in ("quadro", "frame", "classe", "verbo") for how, _ in m.path):
                    out.append((m.kind, m.target, m.cost))
    except Exception:  # noqa: BLE001
        pass
    return tuple(out)


@lru_cache(maxsize=8192)
def _words(text: str) -> frozenset:
    return frozenset(fold(w) for w in re.findall(r"[^\W\d_]+", (text or "").lower()))


@lru_cache(maxsize=1)
def _op_label_words() -> dict:
    return {sid: _words(" ".join(s.labels.values())) for sid, s in E.schemas().items()}


@lru_cache(maxsize=1)
def _type_label_words() -> dict:
    return {t: _words(" ".join(v["label"].values()) + " " + re.sub(r"([A-Z])", r" \1", t))
            for t, v in E.element_types().items()}


@lru_cache(maxsize=1)
def _prop_label_words() -> dict:
    return {p: _words(" ".join(v["label"].values()) + " " + p.replace("-", " ")) for p, v in E.properties().items()}


@lru_cache(maxsize=1)
def _keywords() -> dict:
    """property -> its keyword values (W3C grammars via nucleo.lang.values; named colours for colour properties)."""
    from . import values as V

    allkw = V._all_keywords()
    colors = set(V.named_colors())
    out = {}
    for p in E.properties():
        kws = set(allkw.get(p, ()))
        if "color" in p:
            kws |= colors
        out[p] = sorted(kws)
    return out


@lru_cache(maxsize=1)
def _numeric_props() -> frozenset:
    from . import values as V

    kinds = V._all_literal_kinds()
    return frozenset(p for p in E.properties()
                     if set(kinds.get(p, ())) & {"length", "length-percentage", "number", "integer", "percentage"})


def has_target(sc) -> bool:
    """Whether an operation acts on a node of the page: it takes a target, it acts on the selection, or it was
    observed to change nodes without creating one (an operation with a palette-entry argument creates)."""
    if sc.acts_on_selection() or any(a.name in ("target", "targets") for a in sc.args):
        return True
    creates = any(a.type == "palette-entry" for a in sc.args)
    return not creates and any(w.startswith("node:") for w in sc.writes)


def _merge(*ds) -> dict:
    out: dict = defaultdict(float)
    for d in ds:
        for k, v in d.items():
            out[k] += v
    return out


# -- features -----------------------------------------------------------------------------------------------------
class Context:
    """The utterance and the situation, analysed once; feature functions of each kind of candidate component."""

    def __init__(self, text: str, lang: str, page: Page, disc: Discourse, vocab: frozenset):
        self.lang, self.page, self.disc = lang, page, disc
        self.toks = analyse(text, lang, vocab)
        self.surface = [t.form for t in self.toks]
        self.words = frozenset(k for t in self.toks for k in t.keys)
        self.lemmas = [t.keys[0] for t in self.toks]
        self.graph = {k: _graph(k, lang) for t in self.toks for k in t.keys[:2]}
        self.nums = []
        for k, t in enumerate(self.toks):
            m = NUM_UNIT.match(t.form.lower())
            if m:
                self.nums.append((float(m.group(1).replace(",", ".")), m.group(2), k, None))
            elif NUM.match(t.form):
                nxt = self.toks[k + 1].keys[0] if k + 1 < len(self.toks) else None
                self.nums.append((float(t.form.replace(",", ".")), None, k, nxt))
        self._node: dict = {}

    def lex(self, prefix: str, atom) -> dict:
        """The learned lexicon: each word of the utterance paired with an atom of the candidate."""
        return {(prefix, k, atom): 1.0 for k in self.lemmas}

    def g(self, kind: str, target) -> float:
        best = 0.0
        for ms in self.graph.values():
            for mk, mt, cost in ms:
                if mk == kind and mt == target:
                    best = max(best, math.exp(-cost))
        return best

    def lab(self, words: frozenset) -> float:
        return float(min(2, sum(1 for t in self.toks if t.upos not in ("DET", "ADP", "PUNCT", "CCONJ", "PRON") and
                                any(k in words for k in t.keys))))

    # components
    def op(self, sid: str) -> dict:
        sc = E.schemas()[sid]
        return _merge(self.lex("op", sid), self.lex("ns", sc.namespace),
                      {("op-bias", sid): 1.0, ("op-lab",): self.lab(_op_label_words()[sid]),
                       ("op-g",): self.g("comando", sid)})

    def node(self, n: str, role: str) -> dict:
        key = (n, role)
        if key in self._node:
            return self._node[key]
        page = self.page
        nd = page.nodes[n]
        f: dict = defaultdict(float)
        typ = nd["type"]
        for k in self.lex(f"{role}-type", typ):
            f[k] += 1.0
        f[(f"{role}-g-type",)] += self.g("tipo", typ)
        f[(f"{role}-lab-type",)] += self.lab(_type_label_words().get(typ, frozenset()))
        for field, feat in (("name", "name"), ("text", "text")):
            ws = _words(nd.get(field) if isinstance(nd.get(field), str) else "")
            if ws:
                f[(f"{role}-{feat}",)] += sum(1 for w in ws if w in self.words) / len(ws)
        desc = set()
        for c in nd.get("children", []):
            stack = [c]
            while stack:
                x = stack.pop()
                if isinstance(x.get("text"), str):
                    desc |= _words(x["text"])
                stack += x.get("children", [])
        if desc:
            f[(f"{role}-desc-text",)] += sum(1 for w in desc if w in self.words) / len(desc)
        same = page.of_type(typ)
        rank = same.index(n) + 1
        for k in self.lex(f"{role}-rank", min(rank, 4)):
            f[k] += 1.0
        if rank == len(same) and len(same) > 1:
            for k in self.lex(f"{role}-last", True):
                f[k] += 1.0
        if len(same) == 1:
            f[(f"{role}-unique",)] += 1.0
        anc, depth = page.parent.get(n), 1
        while anc is not None and depth <= 3:
            at = page.nodes[anc]["type"]
            for k in self.lex(f"{role}-anc-type", at):
                f[k] += 1.0 / depth
            ar = page.of_type(at).index(anc) + 1
            for k in self.lex(f"{role}-anc-rank", min(ar, 4)):
                f[k] += 1.0 / depth
            an = _words(page.nodes[anc].get("name"))
            if an:
                f[(f"{role}-anc-name",)] += sum(1 for w in an if w in self.words) / len(an) / depth
            f[(f"{role}-anc-g-type",)] += self.g("tipo", at) / depth
            anc, depth = page.parent.get(anc), depth + 1
        if n in page.selection:
            f[(f"{role}-sel",)] += 1.0
            for k in self.lex(f"{role}-w-sel", True):
                f[k] += 1.0
        if n == self.disc.referent:
            f[(f"{role}-ctx",)] += 1.0
            for k in self.lex(f"{role}-w-ctx", True):
                f[k] += 1.0
        elif self.disc.referent and page.nodes.get(self.disc.referent, {}).get("type") == typ:
            f[(f"{role}-other",)] += 1.0
            for k in self.lex(f"{role}-w-other", True):
                f[k] += 1.0
        self._node[key] = f
        return f

    def prop(self, p: str) -> dict:
        f = _merge(self.lex("prop", p), {("prop-bias", p): 1.0, ("prop-lab",): self.lab(_prop_label_words()[p]),
                                         ("prop-g",): self.g("propriedade", p)})
        for part in p.split("-"):
            for k in self.lex("prop-part", part):
                f[k] += 1.0
        return f

    def value(self, p: str, v: ir.Value) -> dict:
        if v.op in ("MUL", "DIV"):
            return _merge(self.lex("vop", v.op), {("step",): 1.0})
        q = ir.quantity(v.data)
        if q is not None and p in _numeric_props() and str(v.data) not in _keywords().get(p, ()):
            num, unit = q
            f = _merge(self.lex("vop", v.op), {("unit", unit): 1.0})
            said = [x for x in self.nums if x[0] == num]
            if said:
                n_, u_, k_, nxt = said[0]
                f[("lit",)] += 1.0
                f[("unit-said",)] += 1.0 if u_ else 0.0
                if u_ and u_ != unit:
                    f[("unit-other",)] += 1.0
                if nxt is not None:
                    f[("unit-word", nxt, unit)] += 1.0
            else:
                f[("lit-missing",)] += 1.0
            return f
        kw = str(v.data)
        return _merge(self.lex("val", kw), self.lex("vop", v.op),
                      {("val-lab",): 1.0 if fold(kw) in self.words else 0.0,
                       ("val-g",): self.g("valor", (p, kw))})

    def new_type(self, typ: str) -> dict:
        return _merge(self.lex("new-type", typ), {("new-g-type",): self.g("tipo", typ),
                                                  ("new-lab-type",): self.lab(
                                                      _type_label_words().get(typ, frozenset()))})

    def span(self, text: str, slot: str) -> dict:
        ws = text.split()
        for a in range(len(self.surface)):
            if self.surface[a:a + len(ws)] == ws:
                b = a + len(ws)
                prev = self.toks[a - 1].keys[0] if a > 0 else "<s>"
                return {("span-end",): 1.0 if b == len(self.toks) else 0.0, ("span-len",): float(b - a),
                        ("span-cap",): 1.0 if self.surface[a][:1].isupper() else 0.0,
                        ("span-prev", prev, slot): 1.0}
        return {("span-missing",): 1.0}

    def spans(self, slot: str) -> list:
        out = []
        n = len(self.surface)
        for a in range(n):
            for b in range(a + 1, min(n, a + 6) + 1):
                if any(t.upos == "PUNCT" for t in self.toks[a:b]):
                    continue
                s = " ".join(self.surface[a:b])
                out.append((ir.Value(s), self.span(s, slot)))
        return out

    def position(self, dest: str, index: int) -> dict:
        kids = [c["id"] for c in self.page.nodes[dest]["children"]]
        f: dict = defaultdict(float)
        if index == 0:
            for k in self.lex("pos", "start"):
                f[k] += 1.0
        if index == len(kids):
            for k in self.lex("pos", "end"):
                f[k] += 1.0
        if 0 < index <= len(kids):  # after the child before it
            for k, v in self.node(kids[index - 1], "ref").items():
                f[k] += 0.5 * v
            for k in self.lex("pos", "after"):
                f[k] += 1.0
        if index < len(kids):  # before the child at it
            for k, v in self.node(kids[index], "ref").items():
                f[("before",) + k] += 0.5 * v
            for k in self.lex("pos", "before"):
                f[k] += 1.0
        return f


def featurize(cx: Context, a: ir.Action | None, kind: str = "act") -> dict:
    """The features of any grounded action (used for the gold in learning and for every candidate)."""
    if a is None:
        return _merge(cx.lex("none", True), {("none-bias",): 1.0})
    f = cx.op(a.op) if kind == "act" else _merge(cx.lex("rep", True), {("rep-bias",): 1.0})
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


@dataclass
class Cand:
    action: ir.Action | None  # None: the empty plan
    feats: dict
    kind: str = "act"  # act | none | repeat

    def canonical(self) -> str:
        return "NONE" if self.action is None else self.action.canonical()


class Ranker:
    def __init__(self) -> None:
        self.w: dict = defaultdict(float, INIT)
        self._tot: dict = defaultdict(float)
        self._ts: dict = defaultdict(int)
        self.t = 0
        self.vocab: frozenset = _label_vocab()
        self.widths = {"target": 8, "prop": 12, "value": 10, "type": 6, "span": 6, "dest": 6}

    def score(self, feats: dict) -> float:
        return sum(self.w.get(k, 0.0) * v for k, v in feats.items())

    def _top(self, opts: list, k: int) -> list:
        return sorted(opts, key=lambda x: -self.score(x[1]))[:k]

    def context(self, text, lang, page, disc) -> Context:
        return Context(text, lang, page, disc, self.vocab)

    # candidates
    def candidates(self, cx: Context) -> list[Cand]:
        W = self.widths
        page = cx.page
        nodes = list(page.order)
        targets = self._top([(n, cx.node(n, "tgt")) for n in nodes], W["target"])
        dests = self._top([(n, cx.node(n, "dest")) for n in nodes], W["dest"])
        out = [Cand(None, featurize(cx, None), "none")]
        if cx.disc.last and cx.disc.last.steps:
            for n, _ in targets:
                for a in cx.disc.last.steps:
                    if a.target is None or a.target.kind != "node" or a.target.node == n:
                        continue
                    act = ir.Action(a.op, ir.Ref("node", n), a.args)
                    out.append(Cand(act, featurize(cx, act, "repeat"), "repeat"))
        # properties and their values are searched together: the evidence may be in either ("negrito" names a
        # value of font-weight, "largura" a property)
        pairs = []
        for p in E.properties():
            pf = cx.prop(p)
            for v, vf in self._values(cx, p):
                pairs.append(((p, v), _merge(pf, vf)))
        pairs = self._top(pairs, W["prop"] * W["value"] // 3)
        props, seenp = [], set()
        for (p, _), f in pairs:
            if p not in seenp:
                seenp.add(p)
                props.append((p, cx.prop(p)))
        types = self._top([(t, cx.new_type(t)) for t in sorted(set(E.palette().values()))], W["type"])
        for sid, sc in E.schemas().items():
            if any(a.type not in SUPPORTED for a in sc.args if not a.optional):
                continue
            of = cx.op(sid)
            tlist = targets if has_target(sc) else [(None, {})]
            # argument options by type (the value of style.set comes with its property; a position with its
            # destination)
            arg_opts = []
            for spec in sc.args:
                if spec.name in ("target", "targets"):
                    continue
                if spec.type == "property":
                    arg_opts.append((spec, [(ir.Value(p), f) for p, f in props]))
                elif sid == "style.set" and spec.name == "value":
                    arg_opts.append((spec, "value"))
                elif spec.type == "palette-entry":
                    arg_opts.append((spec, "type"))
                elif spec.type == "node":
                    arg_opts.append((spec, [(ir.Ref("node", d), f) for d, f in dests]))
                elif spec.type == "integer" and spec.name == "index":
                    arg_opts.append((spec, "position"))
                elif spec.type in ("string", "json"):
                    arg_opts.append((spec, self._top(cx.spans(spec.name), W["span"])))
                elif spec.type == "enum":
                    arg_opts.append((spec, [(ir.Value(v), cx.lex("enum", v)) for v in spec.values]))
                elif not spec.optional:
                    arg_opts = None
                    break
            if arg_opts is None:
                continue
            new_types = types if any(s.type == "palette-entry" for s in sc.args) else [(None, {})]
            for n, nf in tlist:
                for typ, tf in new_types:
                    target = ir.Ref("node", n) if n is not None else (ir.Ref("new", type=typ) if typ else None)
                    partial = [({}, _merge(of, nf, tf))]
                    for spec, opts in arg_opts:
                        if opts == "type":
                            continue
                        if opts == "value":
                            nxt = []
                            for args, f in partial:
                                p = args.get("property")
                                if p is None:
                                    continue
                                vals = [(v, vf) for (pp, v), vf in pairs if pp == p.data]
                                nxt += [(dict(args, value=v), _merge(f, cx.value(p.data, v))) for v, vf in vals]
                            partial = self._top(nxt, W["value"] * 3)
                            continue
                        if opts == "position":
                            nxt = []
                            for args, f in partial:
                                d = args.get("parent")
                                if not isinstance(d, ir.Ref):
                                    continue
                                kids = len(page.nodes[d.node]["children"])
                                nxt += [(dict(args, index=ir.Value(i)), _merge(f, cx.position(d.node, i)))
                                        for i in range(kids + 1)]
                            partial = self._top(nxt, W["value"] * 3) if nxt else partial
                            continue
                        if not opts:
                            if spec.optional:
                                continue
                            partial = []
                            break
                        partial = self._top([(dict(a, **{spec.name: v}), _merge(f, vf))
                                             for a, f in partial for v, vf in opts], W["value"] * 3)
                    for args, f in partial:
                        out.append(Cand(ir.Action(sid, target, tuple(sorted(args.items()))), f))
        return out

    def _values(self, cx: Context, p: str) -> list:
        opts = [(ir.Value(kw), cx.value(p, ir.Value(kw))) for kw in _keywords().get(p, ())]
        if p in _numeric_props():
            for num, unit, _, _ in cx.nums:
                for u in ([unit] if unit else UNITS):
                    for op in ("SET", "ADD", "SUB"):
                        v = ir.Value(ir.fmt(num, u), op)
                        opts.append((v, cx.value(p, v)))
            for op in ("MUL", "DIV"):
                v = ir.Value(STEP, op)
                opts.append((v, cx.value(p, v)))
        return opts

    def rank(self, text, lang, page, disc) -> list[Cand]:
        cx = self.context(text, lang, page, disc)
        return self.rank_cx(cx)

    def rank_cx(self, cx: Context) -> list[Cand]:
        best: dict = {}
        for c in self.candidates(cx):
            k = c.canonical()
            s = self.score(c.feats)
            if k not in best or s > best[k][0]:
                best[k] = (s, c)
        return [c for _, c in sorted(best.values(), key=lambda x: -x[0])]

    def gold(self, cx: Context, a: ir.Action | None) -> Cand:
        """The gold as a candidate: the better scoring of its readings (a fresh action, or the last plan
        repeated)."""
        if a is None:
            return Cand(None, featurize(cx, None), "none")
        opts = [Cand(a, featurize(cx, a, "act"))]
        if cx.disc.last and any(x.op == a.op and x.args == a.args for x in cx.disc.last.steps):
            opts.append(Cand(a, featurize(cx, a, "repeat"), "repeat"))
        return max(opts, key=lambda c: self.score(c.feats))

    def update(self, gold: Cand, guess: Cand) -> None:
        self.t += 1
        for f, sign in ((gold.feats, 1.0), (guess.feats, -1.0)):
            for k, v in f.items():
                self._tot[k] += (self.t - self._ts[k]) * self.w[k]
                self._ts[k] = self.t
                self.w[k] += sign * v

    def average(self) -> None:
        for k in list(self.w):
            self._tot[k] += (self.t - self._ts[k]) * self.w[k]
            self.w[k] = self._tot[k] / max(self.t, 1) if self.t else self.w[k]
