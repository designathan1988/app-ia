"""Plano D, stage D1: a labelled transition parser (linear, trained on the UD treebanks).

What changes from ``syntax.Parser`` and why (each point is a measured weakness or a published gain):
- **Each arc is labelled when it is made**, with the parser state (the relations already given to the head's and
  the dependent's children, the words around), instead of afterwards from the two words alone. Later decisions see
  the labels already given (the children's relations are features: Zhang & Nivre 2011, "rich non-local
  features"). The move (SHIFT / LEFT / RIGHT) and the label are two perceptrons: making the label part of the move
  multiplies the classes by ~45 and the training time with them (pure Python).
- **Richer features** (Zhang & Nivre 2011): third-order context, valency, the label sets of the left and right
  children, distance, word suffixes for unknown words.
- **Dynamic oracle with error exploration** (Goldberg & Nivre 2012/2013): after the first epoch the parser
  follows its own mistakes during training and learns to recover from them.

It is an averaged perceptron, the same machinery as the rest of the language layer: no neural network.
"""

from __future__ import annotations

import random

from .perceptron import AveragedPerceptron
from .ud import Sentence

S, L, R = "S", "L", "R"


class LabelledParser:
    def __init__(self) -> None:
        self.model = AveragedPerceptron()  # SHIFT / LEFT / RIGHT
        self.model.classes = {S, L, R}
        self.labeler = AveragedPerceptron()  # the relation of each arc, when it is made

    # -- state ---------------------------------------------------------------------------------------------------
    @staticmethod
    def _valid(i: int, n: int, depth: int) -> list[str]:
        out = []
        if i < n - 1:
            out.append(S)
        if depth >= 2:
            out.append(R)
        if depth >= 1:
            out.append(L)
        return out

    @staticmethod
    def _zero_cost(i: int, n: int, stack: list[int], gold: list) -> list[str]:
        """Arc-hybrid dynamic oracle (Goldberg & Nivre 2013): the moves that lose no reachable gold arc."""
        valid = LabelledParser._valid(i, n, len(stack))

        def deps_between(target, others):
            return any(gold[o] == target or gold[target] == o for o in others)

        if not stack or (S in valid and gold[i] == stack[-1]):
            return [S]
        if gold[stack[-1]] == i:
            return [L]
        costly = {m for m in (S, L, R) if m not in valid}
        if len(stack) >= 2 and gold[stack[-1]] == stack[-2]:
            costly.add(L)
        if S not in costly and deps_between(i, stack):
            costly.add(S)
        if deps_between(stack[-1], range(i + 1, n - 1)):
            costly.add(L)
            costly.add(R)
        return [m for m in (S, L, R) if m not in costly]

    @staticmethod
    def _inputs(words, tags):
        W = [w.lower() for w in words] + ["<root>"]
        T = list(tags) + ["ROOT"]
        X = [w.lower()[-3:] for w in words] + ["<root>"]
        return W, T, X

    def _features(self, W, T, X, i, n, stack, kids, lab) -> list[str]:
        def g(seq, k):
            return seq[k] if 0 <= k < len(seq) else "<>"

        def child(h, side, nth=0):
            if h < 0 or h >= n:
                return -1
            ks = kids[h][side]
            return ks[-1 - nth] if len(ks) > nth else -1

        def lb(k):
            return lab[k] if k >= 0 and lab[k] else "<>"

        s0 = stack[-1] if stack else -1
        s1 = stack[-2] if len(stack) > 1 else -1
        s2 = stack[-3] if len(stack) > 2 else -1
        n0, n1, n2 = i, i + 1, i + 2
        s0l, s0l2, s0r, s0r2 = child(s0, 0), child(s0, 0, 1), child(s0, 1), child(s0, 1, 1)
        n0l, n0l2 = child(n0, 0), child(n0, 0, 1)
        s1r = child(s1, 1)
        w, t, x = (lambda k: g(W, k)), (lambda k: g(T, k)), (lambda k: g(X, k))
        d = str(min(n0 - s0, 6)) if s0 >= 0 else "-"
        s0vl = str(len(kids[s0][0])) if s0 >= 0 else "0"
        s0vr = str(len(kids[s0][1])) if s0 >= 0 else "0"
        n0vl = str(len(kids[n0][0])) if n0 < n else "0"
        s0ll = "|".join(sorted({lab[k] for k in kids[s0][0]})) if s0 >= 0 else ""
        s0rl = "|".join(sorted({lab[k] for k in kids[s0][1]})) if s0 >= 0 else ""
        n0ll = "|".join(sorted({lab[k] for k in kids[n0][0]})) if n0 < n else ""
        return [
            "b",
            "s0w" + w(s0), "s0t" + t(s0), "s0wt" + w(s0) + "/" + t(s0), "s0x" + x(s0),
            "n0w" + w(n0), "n0t" + t(n0), "n0wt" + w(n0) + "/" + t(n0), "n0x" + x(n0),
            "n1w" + w(n1), "n1t" + t(n1), "n1wt" + w(n1) + "/" + t(n1), "n2t" + t(n2), "n2w" + w(n2),
            "s1w" + w(s1), "s1t" + t(s1), "s1wt" + w(s1) + "/" + t(s1), "s2t" + t(s2),
            "s0wt.n0wt" + w(s0) + t(s0) + "/" + w(n0) + t(n0), "s0wt.n0w" + w(s0) + t(s0) + "/" + w(n0),
            "s0w.n0wt" + w(s0) + "/" + w(n0) + t(n0), "s0wt.n0t" + w(s0) + t(s0) + "/" + t(n0),
            "s0t.n0wt" + t(s0) + "/" + w(n0) + t(n0), "s0w.n0w" + w(s0) + "/" + w(n0), "s0t.n0t" + t(s0) + t(n0),
            "n0t.n1t" + t(n0) + t(n1), "s1t.s0t" + t(s1) + t(s0), "s1w.s0w" + w(s1) + "/" + w(s0),
            "s1wt.s0t" + w(s1) + t(s1) + "/" + t(s0), "s1t.s0wt" + t(s1) + "/" + w(s0) + t(s0),
            "n0t.n1t.n2t" + t(n0) + t(n1) + t(n2), "s0t.n0t.n1t" + t(s0) + t(n0) + t(n1),
            "s1t.s0t.n0t" + t(s1) + t(s0) + t(n0), "s2t.s1t.s0t" + t(s2) + t(s1) + t(s0),
            "s0t.s0lt.n0t" + t(s0) + t(s0l) + t(n0), "s0t.s0rt.n0t" + t(s0) + t(s0r) + t(n0),
            "s0t.n0t.n0lt" + t(s0) + t(n0) + t(n0l), "s1t.s1rt.s0t" + t(s1) + t(s1r) + t(s0),
            "s0w.d" + w(s0) + d, "s0t.d" + t(s0) + d, "n0w.d" + w(n0) + d, "n0t.d" + t(n0) + d,
            "s0t.n0t.d" + t(s0) + t(n0) + d, "s0w.n0w.d" + w(s0) + "/" + w(n0) + d,
            "s0w.vl" + w(s0) + s0vl, "s0t.vl" + t(s0) + s0vl, "s0w.vr" + w(s0) + s0vr, "s0t.vr" + t(s0) + s0vr,
            "n0w.vl" + w(n0) + n0vl, "n0t.vl" + t(n0) + n0vl,
            "s0lw" + w(s0l), "s0lt" + t(s0l), "s0ll" + lb(s0l), "s0rw" + w(s0r), "s0rt" + t(s0r), "s0rl" + lb(s0r),
            "n0lw" + w(n0l), "n0lt" + t(n0l), "n0ll" + lb(n0l), "s0l2t" + t(s0l2), "s0l2l" + lb(s0l2),
            "s0r2t" + t(s0r2), "s0r2l" + lb(s0r2), "n0l2t" + t(n0l2), "n0l2l" + lb(n0l2),
            "s0t.s0ll.s0l2l" + t(s0) + lb(s0l) + lb(s0l2), "s0t.s0rl.s0r2l" + t(s0) + lb(s0r) + lb(s0r2),
            "n0t.n0ll.n0l2l" + t(n0) + lb(n0l) + lb(n0l2),
            "s0w.sl" + w(s0) + s0ll, "s0t.sl" + t(s0) + s0ll, "s0w.sr" + w(s0) + s0rl, "s0t.sr" + t(s0) + s0rl,
            "n0w.sl" + w(n0) + n0ll, "n0t.sl" + t(n0) + n0ll,
        ]

    @staticmethod
    def _label_features(W, T, X, dep, head, n, kids, lab) -> list[str]:
        """The relation of a new arc, from both words, their neighbours, and the relations already given to the
        dependent's and the head's children."""
        def g(seq, k):
            return seq[k] if 0 <= k < len(seq) else "<>"

        hw, ht = (W[head], T[head]) if head < n - 1 else ("<root>", "ROOT")
        dw, dt, dx = W[dep], T[dep], X[dep]
        side = "L" if head > dep else "R"
        dist = str(min(abs(head - dep), 6)) if head < n - 1 else "r"
        dl = "|".join(sorted({lab[k] for k in kids[dep][0] + kids[dep][1]}))
        hl = "|".join(sorted({lab[k] for k in kids[head][0] + kids[head][1]})) if head < n else ""
        dkt = "|".join(sorted({T[k] for k in kids[dep][0] + kids[dep][1]}))
        return ["b", "ht" + ht, "dt" + dt, "hd" + ht + dt + side, "dw" + dw, "hw" + hw, "dx" + dx,
                "hwdt" + hw + "/" + dt, "dwht" + dw + "/" + ht, "hwdw" + hw + "/" + dw, "side" + side,
                "dist" + dist, "hd.dist" + ht + dt + dist, "dt.side" + dt + side,
                "ctx" + g(T, dep - 1) + dt + g(T, dep + 1), "hctx" + g(T, head - 1) + ht + g(T, head + 1),
                "dl" + dl, "dt.dl" + dt + dl, "dw.dl" + dw + dl, "hl" + ht + hl, "hd.hl" + ht + dt + side + hl,
                "dkt" + dt + dkt, "dw.side" + dw + side, "hw.side" + hw + side, "first" + str(dep == 0),
                "prevw" + g(W, dep - 1) + "/" + dt, "nextw" + g(W, dep + 1) + "/" + dt]

    @staticmethod
    def _apply(m, i, stack, heads, kids):
        if m == S:
            stack.append(i)
            return i + 1, None, None
        dep = stack.pop()
        head = stack[-1] if m == R else i
        heads[dep] = head
        kids[head][1 if head < dep else 0].append(dep)
        return i, dep, head

    def parse(self, words: list[str], tags: list[str]) -> list[tuple[int, str]]:
        n = len(words) + 1
        W, T, X = self._inputs(words, tags)
        heads, lab = [None] * n, [""] * n
        kids = [[[], []] for _ in range(n)]
        stack: list[int] = []
        i = 0
        while stack or i < n - 1:
            m = self.model.predict(self._features(W, T, X, i, n, stack, kids, lab), self._valid(i, n, len(stack)))
            i, dep, head = self._apply(m, i, stack, heads, kids)
            if dep is not None:
                lab[dep] = "root" if head == n - 1 else self.labeler.predict(
                    self._label_features(W, T, X, dep, head, n, kids, lab))
        return [(0, "root") if h is None or h == n - 1 else (h + 1, lab[d] or "dep") for d, h in
                enumerate(heads[: n - 1])]

    def train(self, sentences: list[Sentence], tag_of, epochs: int = 10, seed: int = 0, explore: float = 0.9,
              log=None) -> None:
        rng = random.Random(seed)
        self.labeler.classes = {w.deprel for s in sentences for w in s.words if w.head > 0}
        data = list(sentences)
        for ep in range(epochs):
            rng.shuffle(data)
            for s in data:
                words = [w.form for w in s.words]
                n = len(words) + 1
                gold = [(w.head - 1 if w.head > 0 else n - 1) for w in s.words] + [None]
                glab = [w.deprel for w in s.words] + [""]
                W, T, X = self._inputs(words, tag_of(s))
                heads, lab = [None] * n, [""] * n
                kids = [[[], []] for _ in range(n)]
                stack: list[int] = []
                i = 0
                while stack or i < n - 1:
                    feats = self._features(W, T, X, i, n, stack, kids, lab)
                    valid = self._valid(i, n, len(stack))
                    sc = self.model.scores(feats)
                    guess = max(valid, key=lambda c: (sc.get(c, 0.0), c))
                    zero = self._zero_cost(i, n, stack, gold) or valid
                    best = max(zero, key=lambda c: (sc.get(c, 0.0), c))
                    self.model.update(best, guess, feats)
                    follow = guess if guess in zero or ep > 0 and rng.random() < explore else best
                    i, dep, head = self._apply(follow, i, stack, heads, kids)
                    if dep is None:
                        continue
                    if head == n - 1:
                        lab[dep] = "root"
                        continue
                    lf = self._label_features(W, T, X, dep, head, n, kids, lab)
                    g = self.labeler.predict(lf)
                    if head == gold[dep]:  # a label is learned only on a correct arc
                        self.labeler.update(glab[dep], g, lf)
                        lab[dep] = glab[dep]
                    else:
                        lab[dep] = g
            if log:
                log(ep)
        self.model.average()
        self.labeler.average()

    def save(self, folder) -> None:
        import pathlib

        folder = pathlib.Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        self.model.save(folder / "parser_d1.json")
        self.labeler.save(folder / "labeler_d1.json")

    @classmethod
    def load(cls, folder) -> "LabelledParser":
        import pathlib

        folder = pathlib.Path(folder)
        p = cls()
        p.model = AveragedPerceptron.load(folder / "parser_d1.json")
        p.labeler = AveragedPerceptron.load(folder / "labeler_d1.json")
        return p
