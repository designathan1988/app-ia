"""Lexicon induction for a probabilistic CCG: UBL (Kwiatkowski, Zettlemoyer, Goldwater & Steedman, EMNLP 2010) with the
factored lexicon of FUBL (Kwiatkowski et al., EMNLP 2011).

- **Splitting** (UBL §4): restricted higher-order unification finds every (f, g) with h = f(g) or h = λx.f(g(x)),
  under three restrictions — no vacuous variables, at most N=4 conjuncts extracted, a new variable applied only to
  variables. Each split gives pairs of categories for the four combinators (UBL §4.2) and every split point of the
  words (§4.3).
- **Factored lexicon** (FUBL §5–6): a lexical item w ⊢ X : h is stored as a lexeme (w, [constants of h]) and a
  template (X, h with the constants abstracted). At parse time any lexeme combines with any template whose
  placeholder types match — so a word learned in one construction is usable in the others.
- **Learning** (FUBL Fig. 1): online; for each example, (1) the best correct parse y* under the current model is
  re-analysed by NEW-LEX and the best split is added, (2) a stochastic gradient step on log p(z|x) with the parse as
  a hidden variable: E_{p(y|x,z)}[φ] − E_{p(y,z|x)}[φ], estimated over the chart's beam.
- **Features** (FUBL §8): lexeme, template (value 0.1), lexeme–template pair; at the root, predicate–argument and
  predicate–argument-type indicators. Lexeme weights start from IBM Model 1 co-occurrence (×10, as in UBL §7).

No language, no domain and no construction is written here: they all come from the training pairs.
"""

from __future__ import annotations

import itertools
import math
from collections import defaultdict

from . import ccg as C
from . import logica as L

N_CONJ = 4


# -- positions in a term ------------------------------------------------------------------------------------------
def _positions(t, path=(), scope=()):
    yield path, t, scope
    if isinstance(t, L.Lam):
        yield from _positions(t.body, path + ("b",), scope + (t.var,))
    elif isinstance(t, L.App):
        yield from _positions(t.fn, path + ("f",), scope)
        for i, a in enumerate(t.args):
            yield from _positions(a, path + (i,), scope)


def _get(t, path):
    for s in path:
        t = t.body if s == "b" else t.fn if s == "f" else t.args[s]
    return t


def _replace(t, path, new):
    if not path:
        return new
    s, rest = path[0], path[1:]
    if s == "b":
        return L.Lam(t.var, _replace(t.body, rest, new))
    if s == "f":
        return L.App(_replace(t.fn, rest, new), t.args)
    args = list(t.args)
    args[s] = _replace(args[s], rest, new)
    return L.App(t.fn, tuple(args))


def _abstract(sub, scope):
    fv = [v for v in scope if v in L.free_vars(sub)]
    g = sub
    for v in reversed(fv):
        g = L.Lam(v, g)
    return g, fv


def application_splits(h) -> list:
    """(f, g) with f(g) = h (UBL §4.1)."""
    out, seen = [], set()
    hk = L.canonical(h)

    def add(f, g):
        if L.type_of(f) is None or L.type_of(g) is None:
            return
        if L.canonical(g) == hk:
            return
        k = (L.canonical(f), L.canonical(g))
        if k in seen:
            return
        try:
            if L.canonical(L.apply(f, g)) != hk:
                return
        except Exception:  # noqa: BLE001 - an ill-formed split is no split
            return
        seen.add(k)
        out.append((f, g))

    for path, sub, scope in list(_positions(h)):
        if not path or isinstance(sub, L.Var) or L.is_structural(sub):
            continue
        if path[-1] == "f":
            parent = _get(h, path[:-1])
            if not all(isinstance(a, L.Var) for a in parent.args):
                continue  # (a new variable applied to a non-variable: forbidden)
        g, fv = _abstract(sub, scope)
        gt = L.type_of(g)
        if gt is None:
            continue
        x = L.fresh(gt)
        rep = x if not fv else L.App(x, tuple(fv))
        add(L.Lam(x, _replace(h, path, rep)), g)
    for path, sub, scope in list(_positions(h)):
        if isinstance(sub, L.App) and isinstance(sub.fn, L.Const) and sub.fn.name in ("and", "or") and \
                len(sub.args) >= 3:
            m = len(sub.args)
            for k in range(2, min(N_CONJ, m - 1) + 1):
                for idx in itertools.combinations(range(m), k):
                    part = L.App(sub.fn, tuple(sub.args[i] for i in idx))
                    rest = [sub.args[i] for i in range(m) if i not in idx]
                    g, fv = _abstract(part, scope)
                    x = L.fresh(L.type_of(g))
                    rep = x if not fv else L.App(x, tuple(fv))
                    add(L.Lam(x, _replace(h, path, L.App(sub.fn, tuple(rest + [rep])))), g)
    return out


def composition_splits(h) -> list:
    """(f, g) with λy.f(g(y)) = h."""
    if not isinstance(h, L.Lam):
        return []
    y, body = h.var, h.body
    out, seen = [], set()
    hk = L.canonical(h)
    for path, sub, scope in list(_positions(body)):
        if not path or isinstance(sub, L.Var):
            continue
        fvs = L.free_vars(sub)
        if y not in fvs or any(v in scope for v in fvs):
            continue
        st = L.type_of(sub)
        if st is None:
            continue
        z = L.fresh(st)
        bz = _replace(body, path, z)
        if y in L.free_vars(bz):
            continue
        f, g = L.Lam(z, bz), L.Lam(y, sub)
        k = (L.canonical(f), L.canonical(g))
        if k in seen:
            continue
        try:
            if L.canonical(L.compose(f, g)) != hk:
                continue
        except Exception:  # noqa: BLE001
            continue
        seen.add(k)
        out.append((f, g))
    return out


def category_splits(cat, h) -> list:
    """(left category, left meaning, right category, right meaning) for the four combinators (UBL §4.2)."""
    out = []
    for f, g in application_splits(h):
        y = C.cat_of_type(L.type_of(g))
        out.append(((C.FWD, cat, y), f, y, g))
        out.append((y, g, (C.BWD, cat, y), f))
    if not isinstance(cat, str):
        s, a, ycat = cat
        for f, g in composition_splits(h):
            w = C.cat_of_type(L.type_of(g.body))
            if s in (C.FWD, C.ANY):
                out.append(((C.FWD, a, w), f, (C.FWD, w, ycat), g))
            if s in (C.BWD, C.ANY):
                out.append(((C.BWD, w, ycat), g, (C.BWD, a, w), f))
    return out


# -- factored lexicon ---------------------------------------------------------------------------------------------
def _map_consts(t, m: dict):
    if isinstance(t, L.Const):
        return m.get(t, t)
    if isinstance(t, L.Lam):
        return L.Lam(t.var, _map_consts(t.body, m))
    if isinstance(t, L.App):
        return L.App(_map_consts(t.fn, m), tuple(_map_consts(a, m) for a in t.args))
    return t


def factor(cat, lf):
    """Maximal factoring (FUBL §6.1): the lexeme's constants (each once, in traversal order) and the template."""
    cs: list = []
    for c in L.constants(lf):
        if c not in cs:
            cs.append(c)
    ph = {c: L.Const(f"#{i}", c.type) for i, c in enumerate(cs)}
    tl = _map_consts(lf, ph)
    sig = tuple(L.type_str(c.type) for c in cs)
    return tuple(cs), (cat, tl, sig)


def instantiate(template, consts):
    cat, tl, sig = template
    m = {L.Const(f"#{i}", c.type): c for i, c in enumerate(consts)}
    return cat, L.beta(_map_consts(tl, m))


class Lexicon:
    def __init__(self) -> None:
        self.lexemes: list = []  # (words, consts)
        self.lexeme_id: dict = {}
        self.by_words: dict = defaultdict(set)
        self.templates: list = []  # (cat, template lf, sig)
        self.template_id: dict = {}
        self.by_sig: dict = defaultdict(list)
        self._inst: dict = {}

    def add_lexeme(self, words: tuple, consts: tuple) -> tuple[int, bool]:
        k = (words, tuple(str(c) for c in consts))
        if k in self.lexeme_id:
            return self.lexeme_id[k], False
        i = len(self.lexemes)
        self.lexemes.append((words, consts))
        self.lexeme_id[k] = i
        self.by_words[words].add(i)
        return i, True

    def add_template(self, template) -> tuple[int, bool]:
        cat, tl, sig = template
        k = (C.cat_str(cat), L.key(tl))
        if k in self.template_id:
            return self.template_id[k], False
        i = len(self.templates)
        self.templates.append(template)
        self.template_id[k] = i
        self.by_sig[sig].append(i)
        return i, True

    def add_item(self, words, cat, lf) -> tuple:
        consts, tpl = factor(cat, lf)
        lid, new_l = self.add_lexeme(tuple(words), consts)
        tid, new_t = self.add_template(tpl)
        return lid, tid, new_l, new_t

    def item(self, lid: int, tid: int):
        k = (lid, tid)
        got = self._inst.get(k)
        if got is None:
            cat, lf = instantiate(self.templates[tid], self.lexemes[lid][1])
            got = (cat, lf, L.key(lf), tuple(L.const_str(c) for c in L.constants(lf)))
            self._inst[k] = got
        return got

    def sig(self, lid: int) -> tuple:
        return tuple(L.type_str(c.type) for c in self.lexemes[lid][1])


# -- IBM Model 1 (Brown et al. 1993), the co-occurrence initialization of UBL §7 --------------------------------
def ibm1(pairs, iterations: int = 10) -> dict:
    """t(constant | word) from (words, constants) pairs, with a NULL word."""
    t: dict = defaultdict(lambda: 1.0)
    for _ in range(iterations):
        count: dict = defaultdict(float)
        total: dict = defaultdict(float)
        for words, consts in pairs:
            ws = list(words) + ["<null>"]
            for c in consts:
                z = sum(t[(c, w)] for w in ws)
                for w in ws:
                    d = t[(c, w)] / z
                    count[(c, w)] += d
                    total[w] += d
        t = defaultdict(float, {k: v / total[k[1]] for k, v in count.items()})
    return dict(t)


# -- the model ----------------------------------------------------------------------------------------------------
class Model:
    def __init__(self, lexicon: Lexicon, ibm: dict, beam: int = 40, alpha0: float = 1.0, cool: float = 1e-5) -> None:
        self.lex = lexicon
        self.ibm = ibm
        self.w: dict = defaultdict(float)
        self.beam = beam
        self.alpha0, self.cool = alpha0, cool
        self.k = 0

    # initial weights (UBL §7, FUBL §8)
    def lexeme_init(self, lid: int) -> float:
        words, consts = self.lex.lexemes[lid]
        pairs = [self.ibm.get((str(c), w), 0.0) for w in words for c in consts]
        return 10.0 * sum(pairs) / len(pairs) if pairs else 0.0

    def template_init(self, tid: int) -> float:
        cat, tl, _ = self.lex.templates[tid]
        return -0.1 * C.slashes(cat)

    def init_item(self, lid, tid, new_l, new_t) -> None:
        if new_l:
            self.w[("lx", lid)] = self.lexeme_init(lid)
        if new_t:
            self.w[("tp", tid)] = self.template_init(tid)

    def lex_score(self, lid: int, tid: int) -> float:
        return self.w[("lx", lid)] + 0.1 * self.w[("tp", tid)] + self.w[("lt", lid, tid)]

    @staticmethod
    def lf_features(lf) -> dict:
        out: dict = defaultdict(float)

        def go(t):
            if isinstance(t, L.App):
                if isinstance(t.fn, L.Const) and not L.is_structural(t.fn):
                    for i, a in enumerate(t.args):
                        if isinstance(a, L.Const):
                            out[("pa", t.fn.name, a.name, i)] += 1.0
                        ty = L.type_of(a)
                        out[("pt", t.fn.name, L.type_str(ty) if ty is not None else "?", i)] += 1.0
                go(t.fn)
                for a in t.args:
                    go(a)
            elif isinstance(t, L.Lam):
                go(t.body)

        go(lf)
        return out

    def features(self, it: C.Item) -> dict:
        f: dict = defaultdict(float)
        for leaf in C.leaves(it):
            if leaf.lexeme is None:
                f[("skip",)] += 1.0
                continue
            lid, tid = leaf.lexeme
            f[("lx", lid)] += 1.0
            f[("tp", tid)] += 0.1
            f[("lt", lid, tid)] += 1.0
        for k, v in self.lf_features(it.lf).items():
            f[k] += v
        return f

    def total(self, it: C.Item) -> float:
        return it.score + sum(self.w[k] * v for k, v in self.lf_features(it.lf).items())

    # parsing
    def lexical(self, words, constrained: dict | None = None, skip: bool = False):
        def items(i, j):
            out = []
            for lid in self.lex.by_words.get(tuple(words[i:j]), ()):
                for tid in self.lex.by_sig.get(self.lex.sig(lid), ()):
                    cat, lf, lk, consts = self.lex.item(lid, tid)
                    if constrained is not None and not C.multiset_le(consts, constrained):
                        continue
                    out.append(C.Item(cat, lf, self.lex_score(lid, tid), (i, j), "lex", (), (lid, tid), lk, consts))
            return out
        return items

    def parse(self, words, constrained: dict | None = None):
        n = len(words)
        # (the constrained parse keeps a wider beam: its cells are already small, and losing the correct
        # derivation there loses the example)
        beam = self.beam if constrained is None else 4 * self.beam
        return C.parse(n, self.lexical(words, constrained), beam=beam, allowed=constrained)

    def roots(self, words, constrained=None) -> list:
        ch = self.parse(words, constrained)
        return ch.items(0, len(words))

    def predict(self, words, skip_cost: float = -2.0):
        """The best logical form, or None. A second pass skips one unknown word at a time (UBL-s)."""
        rs = self.roots(words)
        if rs:
            best = max(rs, key=self.total)
            return best, self.total(best)
        best = None
        for i in range(len(words)):
            rest = words[:i] + words[i + 1:]
            if not rest:
                continue
            for it in self.roots(rest):
                s = self.total(it) + skip_cost
                if best is None or s > best[1]:
                    best = (it, s)
        return best if best else (None, None)

    # learning
    def new_lex(self, ystar: C.Item, words) -> bool:
        """NEW-LEX (UBL §5): the single split of a node of y* that most improves its score is added."""
        best, best_gain = None, 0.0
        for node in C.nodes(ystar):
            i, j = node.span
            if j - i < 2:
                continue
            for lc, llf, rc, rlf in category_splits(node.cat, node.lf):
                for k in range(i + 1, j):
                    s = self._candidate_score(words[i:k], lc, llf) + self._candidate_score(words[k:j], rc, rlf)
                    gain = s - node.score
                    if gain > best_gain:
                        best_gain, best = gain, ((words[i:k], lc, llf), (words[k:j], rc, rlf))
        if best is None:
            return False
        for ws, cat, lf in best:
            self.init_item(*self.lex.add_item(ws, cat, lf))
        return True

    def _candidate_score(self, words, cat, lf) -> float:
        consts, tpl = factor(cat, lf)
        lk = (tuple(words), tuple(str(c) for c in consts))
        tk = (C.cat_str(tpl[0]), L.key(tpl[1]))
        lid = self.lex.lexeme_id.get(lk)
        tid = self.lex.template_id.get(tk)
        if lid is None:
            pairs = [self.ibm.get((str(c), w), 0.0) for w in words for c in consts]
            lx = 10.0 * sum(pairs) / len(pairs) if pairs else 0.0
        else:
            lx = self.w[("lx", lid)]
        tp = self.w[("tp", tid)] if tid is not None else -0.1 * C.slashes(tpl[0])
        lt = self.w[("lt", lid, tid)] if lid is not None and tid is not None else 0.0
        return lx + 0.1 * tp + lt

    def update(self, words, z) -> bool:
        """One FUBL step on (words, z). Returns whether a correct parse was found."""
        zk = L.canonical(z)
        allowed: dict = defaultdict(int)
        for c in L.constants(z):
            allowed[L.const_str(c)] += 1
        good = [it for it in self.roots(words, allowed) if L.canonical(it.lf) == zk]
        if not good:
            return False
        ystar = max(good, key=self.total)
        if self.new_lex(ystar, words):
            good = [it for it in self.roots(words, allowed) if L.canonical(it.lf) == zk] or good
        every = self.roots(words)
        seen = {id(x) for x in every}
        every += [g for g in good if id(g) not in seen]
        delta: dict = defaultdict(float)
        for sign, group in ((1.0, good), (-1.0, every)):
            scores = [self.total(it) for it in group]
            m = max(scores)
            ps = [math.exp(s - m) for s in scores]
            zsum = sum(ps)
            for it, p in zip(group, ps):
                for k, v in self.features(it).items():
                    delta[k] += sign * (p / zsum) * v
        self.k += 1
        gamma = self.alpha0 / (1.0 + self.cool * self.k)
        for k, v in delta.items():
            if v:
                self.w[k] += gamma * v
        return True


def seed(lexicon: Lexicon, model: Model, data, names) -> None:
    """The initial factored lexicon: one whole-sentence item per training pair (FUBL Initialization) and the
    entity names (the NP list of UBL §5)."""
    for words, z in data:
        model.init_item(*lexicon.add_item(tuple(words), C.cat_of_type(L.type_of(z)), z))
    for words, const in names:
        lid, tid, nl, nt = lexicon.add_item(tuple(words), C.cat_of_type(const.type), const)
        model.init_item(lid, tid, nl, nt)
        if nl:
            model.w[("lx", lid)] = 10.0  # (UBL §7: the seed NP entries start at the highest co-occurrence score)
