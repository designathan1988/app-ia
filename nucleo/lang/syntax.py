"""Part-of-speech tagging and dependency parsing for Portuguese, with linear models trained on human treebanks.

* **Tagger:** averaged perceptron over word, affix, shape and neighbour features, greedy left to right. A tag
  dictionary covers frequent unambiguous words.
* **Parser:** arc-hybrid transition system (stack, buffer, SHIFT / LEFT / RIGHT) with the dynamic oracle of
  Goldberg & Nivre (2013). It learns from its own mistakes and handles non-projective training trees as well as
  that system can. A second perceptron labels each arc with its UD relation.
* **Lemmas:** the treebanks' own (form, tag) -> lemma counts; otherwise the form itself.

No neural network is used; the models are dictionaries of weights, saved as JSON.
"""

from __future__ import annotations

import json
import pathlib
import random
from collections import Counter, defaultdict

from .perceptron import AveragedPerceptron
from .ud import Sentence

SHIFT, RIGHT, LEFT = 0, 1, 2
MOVES = (SHIFT, RIGHT, LEFT)


def _shape(w: str) -> str:
    if w.isdigit():
        return "d"
    if w[:1].isupper():
        return "X" if w.isupper() else "Xx"
    if any(c.isdigit() for c in w):
        return "xd"
    return "x"


def _ambiguity(word: str) -> str:
    """The set of categories MorphoBr allows for a word (its ambiguity class), e.g. "N|V" for "casa"."""
    try:
        from .morph import analyses
    except Exception:  # noqa: BLE001 - the index is optional: without it the feature is constant
        return "?"
    if word.startswith("<"):
        return word
    try:
        cats = sorted({tags.split("+")[0] for _, tags in analyses(word)})
    except Exception:  # noqa: BLE001
        return "?"
    return "|".join(cats) or "-"


class Tagger:
    def __init__(self) -> None:
        self.model = AveragedPerceptron()
        self.tagdict: dict[str, str] = {}

    def _features(self, i: int, words: list[str], prev: str, prev2: str) -> list[str]:
        w = words[i]
        lw = w.lower()
        ctx = ["<s2>", "<s1>"] + [x.lower() for x in words] + ["</s1>", "</s2>"]
        j = i + 2
        return [
            "b", "w=" + lw, "s3=" + lw[-3:], "s2=" + lw[-2:], "s1=" + lw[-1:], "p1=" + lw[:1], "p2=" + lw[:2],
            "sh=" + _shape(w), "t-1=" + prev, "t-2=" + prev2, "t-1t-2=" + prev + prev2, "t-1w=" + prev + lw,
            "w-1=" + ctx[j - 1], "s-1=" + ctx[j - 1][-3:], "w+1=" + ctx[j + 1], "s+1=" + ctx[j + 1][-3:],
            "w-2=" + ctx[j - 2], "w+2=" + ctx[j + 2], "first=" + str(i == 0),
            "mb=" + _ambiguity(lw), "mb-1=" + _ambiguity(ctx[j - 1]), "mb+1=" + _ambiguity(ctx[j + 1]),
            "mb t-1=" + _ambiguity(lw) + prev,
        ]

    def tag(self, words: list[str]) -> list[str]:
        prev, prev2 = "<s>", "<s2>"
        out = []
        for i, w in enumerate(words):
            t = self.tagdict.get(w.lower())
            if t is None:
                t = self.model.predict(self._features(i, words, prev, prev2))
            out.append(t)
            prev2, prev = prev, t
        return out

    def train(self, sentences: list[Sentence], epochs: int = 5, seed: int = 0) -> None:
        counts: dict[str, Counter] = defaultdict(Counter)
        for s in sentences:
            for w in s.words:
                counts[w.form.lower()][w.upos] += 1
                self.model.classes.add(w.upos)
        for w, c in counts.items():
            tag, n = c.most_common(1)[0]
            if sum(c.values()) >= 20 and n / sum(c.values()) >= 0.995:
                self.tagdict[w] = tag
        data = list(sentences)
        rng = random.Random(seed)
        for _ in range(epochs):
            rng.shuffle(data)
            for s in data:
                words = [w.form for w in s.words]
                prev, prev2 = "<s>", "<s2>"
                for i, w in enumerate(s.words):
                    guess = self.tagdict.get(words[i].lower())
                    if guess is None:
                        feats = self._features(i, words, prev, prev2)
                        guess = self.model.predict(feats)
                        self.model.update(w.upos, guess, feats)
                    prev2, prev = prev, guess
        self.model.average()


class Parser:
    def __init__(self) -> None:
        self.model = AveragedPerceptron()
        self.model.classes = set(MOVES)
        self.labeler = AveragedPerceptron()

    # -- transition system (Honnibal's arc-hybrid layout: a ROOT token at the end of the buffer) ---------------
    @staticmethod
    def _valid(i: int, n: int, stack_depth: int) -> list[int]:
        moves = []
        if i < n - 1:
            moves.append(SHIFT)
        if stack_depth >= 2:
            moves.append(RIGHT)
        if stack_depth >= 1:
            moves.append(LEFT)
        return moves

    @staticmethod
    def _gold_moves(i: int, n: int, stack: list[int], heads: list, gold: list) -> list[int]:
        def deps_between(target, others):
            return any(gold[o] == target or gold[target] == o for o in others)

        valid = Parser._valid(i, n, len(stack))
        if not stack or (SHIFT in valid and gold[i] == stack[-1]):
            return [SHIFT]
        if gold[stack[-1]] == i:
            return [LEFT]
        costly = {m for m in MOVES if m not in valid}
        if len(stack) >= 2 and gold[stack[-1]] == stack[-2]:
            costly.add(LEFT)
        if SHIFT not in costly and deps_between(i, stack):
            costly.add(SHIFT)
        if deps_between(stack[-1], range(i + 1, n - 1)):
            costly.add(LEFT)
            costly.add(RIGHT)
        return [m for m in MOVES if m not in costly]

    def _features(self, words, tags, i, n, stack, deps) -> list[str]:
        def get(seq, k):
            return seq[k] if 0 <= k < len(seq) else "<>"

        def kids(h, side):
            ks = deps[h][side] if 0 <= h < len(deps) else []
            return (ks[-1] if ks else -1, ks[-2] if len(ks) > 1 else -1, len(ks))

        s0 = stack[-1] if stack else -1
        s1 = stack[-2] if len(stack) > 1 else -1
        s2 = stack[-3] if len(stack) > 2 else -1
        n0, n1, n2 = i, i + 1, i + 2
        w = lambda k: get(words, k)  # noqa: E731
        t = lambda k: get(tags, k)  # noqa: E731
        s0l, s0l2, s0lv = kids(s0, 0)
        s0r, s0r2, s0rv = kids(s0, 1)
        n0l, n0l2, n0lv = kids(n0, 0)
        dist = str(min(n0 - s0, 5)) if s0 >= 0 else "-"
        f = [
            "b", "s0w=" + w(s0), "s0t=" + t(s0), "s0wt=" + w(s0) + t(s0), "n0w=" + w(n0), "n0t=" + t(n0),
            "n0wt=" + w(n0) + t(n0), "n1w=" + w(n1), "n1t=" + t(n1), "n2t=" + t(n2), "s1w=" + w(s1), "s1t=" + t(s1),
            "s2t=" + t(s2), "s0t n0t=" + t(s0) + t(n0), "s0w n0w=" + w(s0) + "|" + w(n0),
            "s0t n0t n1t=" + t(s0) + t(n0) + t(n1), "s1t s0t n0t=" + t(s1) + t(s0) + t(n0),
            "s0t s0lt s0rt=" + t(s0) + t(s0l) + t(s0r), "n0t n0lt=" + t(n0) + t(n0l), "s0t n0t d=" + t(s0) + t(n0) + dist,
            "s0w d=" + w(s0) + dist, "n0w d=" + w(n0) + dist, "s0 val=" + t(s0) + str(s0lv) + str(s0rv),
            "n0 val=" + t(n0) + str(n0lv), "s0lt=" + t(s0l), "s0rt=" + t(s0r), "s0l2t=" + t(s0l2), "s0r2t=" + t(s0r2),
            "n0lt=" + t(n0l), "n0l2t=" + t(n0l2), "s1t s0t=" + t(s1) + t(s0), "s1w s0w=" + w(s1) + "|" + w(s0),
            "n0w n1w=" + w(n0) + "|" + w(n1),
        ]
        return f

    @staticmethod
    def _apply(move, i, stack, heads, deps):
        if move == SHIFT:
            stack.append(i)
            return i + 1
        dep = stack.pop()
        head = stack[-1] if move == RIGHT else i
        heads[dep] = head
        side = 1 if head < dep else 0
        deps[head][side].append(dep)
        return i

    def parse_heads(self, words: list[str], tags: list[str]) -> list[int]:
        n = len(words) + 1  # the ROOT token sits at index n-1
        W = [x.lower() for x in words] + ["<root>"]
        T = list(tags) + ["ROOT"]
        heads = [None] * n
        deps = [[[], []] for _ in range(n)]
        stack: list[int] = []
        i = 0
        while stack or i < n - 1:
            feats = self._features(W, T, i, n, stack, deps)
            move = self.model.predict(feats, self._valid(i, n, len(stack)))
            i = self._apply(move, i, stack, heads, deps)
        # convert: index n-1 (ROOT) -> 0; words 0..n-2 -> 1..n-1
        return [0 if h is None or h == n - 1 else h + 1 for h in heads[: n - 1]]

    def _label_features(self, words, tags, dep, head) -> list[str]:
        hw = words[head - 1].lower() if head else "<root>"
        ht = tags[head - 1] if head else "ROOT"
        dw, dt = words[dep - 1].lower(), tags[dep - 1]
        direction = "L" if head and head > dep else "R"
        prev_t = tags[dep - 2] if dep > 1 else "<s>"
        next_t = tags[dep] if dep < len(tags) else "</s>"
        return ["b", "ht=" + ht, "dt=" + dt, "hd=" + ht + dt + direction, "dw=" + dw, "hw=" + hw,
                "hwdt=" + hw + dt, "dwht=" + dw + ht, "dir=" + direction, "dist=" + str(min(abs(head - dep), 6)),
                "ctx=" + prev_t + dt + next_t, "dt dir=" + dt + direction, "root=" + str(head == 0)]

    def parse(self, words: list[str], tags: list[str]) -> list[tuple[int, str]]:
        heads = self.parse_heads(words, tags)
        return [(h, self.labeler.predict(self._label_features(words, tags, d, h))) for d, h in enumerate(heads, 1)]

    def train(self, sentences: list[Sentence], tag_of, epochs: int = 5, seed: int = 0) -> None:
        rng = random.Random(seed)
        data = list(sentences)
        for s in data:
            for w in s.words:
                self.labeler.classes.add(w.deprel)
        for _ in range(epochs):
            rng.shuffle(data)
            for s in data:
                words = [w.form for w in s.words]
                tags = tag_of(s)
                n = len(words) + 1
                gold = [(w.head - 1 if w.head > 0 else n - 1) for w in s.words] + [None]
                W = [x.lower() for x in words] + ["<root>"]
                T = list(tags) + ["ROOT"]
                heads = [None] * n
                deps = [[[], []] for _ in range(n)]
                stack: list[int] = []
                i = 0
                while stack or i < n - 1:
                    feats = self._features(W, T, i, n, stack, deps)
                    valid = self._valid(i, n, len(stack))
                    scores = self.model.scores(feats)
                    guess = max(valid, key=lambda m: (scores.get(m, 0.0), m))
                    golds = self._gold_moves(i, n, stack, heads, gold) or valid
                    best = max(golds, key=lambda m: (scores.get(m, 0.0), m))
                    self.model.update(best, guess, feats)
                    i = self._apply(guess, i, stack, heads, deps)
                for d, w in enumerate(s.words, 1):
                    feats = self._label_features(words, tags, d, w.head)
                    guess = self.labeler.predict(feats)
                    self.labeler.update(w.deprel, guess, feats)
        self.model.average()
        self.labeler.average()


class Lemmatizer:
    def __init__(self) -> None:
        self.table: dict[tuple[str, str], str] = {}

    def train(self, sentences: list[Sentence]) -> None:
        c: dict[tuple[str, str], Counter] = defaultdict(Counter)
        for s in sentences:
            for w in s.words:
                c[(w.form.lower(), w.upos)][w.lemma.lower()] += 1
        self.table = {k: v.most_common(1)[0][0] for k, v in c.items()}

    def lemma(self, form: str, upos: str) -> str:
        return self.table.get((form.lower(), upos), form.lower())


MODELS = pathlib.Path(__file__).resolve().parents[2] / "data" / "models"


def save(tagger: Tagger, parser: Parser, lemmatizer: Lemmatizer, contractions: dict) -> None:
    MODELS.mkdir(parents=True, exist_ok=True)
    tagger.model.save(MODELS / "tagger.json")
    (MODELS / "tagdict.json").write_text(json.dumps(tagger.tagdict), encoding="utf-8")
    parser.model.save(MODELS / "parser.json")
    parser.labeler.save(MODELS / "labeler.json")
    (MODELS / "lemmas.json").write_text(json.dumps([[a, b, c] for (a, b), c in lemmatizer.table.items()]),
                                        encoding="utf-8")
    (MODELS / "contractions.json").write_text(json.dumps(contractions, ensure_ascii=False), encoding="utf-8")


def load_models():
    t = Tagger()
    t.model = AveragedPerceptron.load(MODELS / "tagger.json")
    t.tagdict = json.loads((MODELS / "tagdict.json").read_text(encoding="utf-8"))
    p = Parser()
    p.model = AveragedPerceptron.load(MODELS / "parser.json")
    p.model.classes = {int(c) for c in p.model.classes}
    p.model.weights = {f: {int(k): v for k, v in w.items()} for f, w in p.model.weights.items()}
    p.labeler = AveragedPerceptron.load(MODELS / "labeler.json")
    lem = Lemmatizer()
    lem.table = {(a, b): c for a, b, c in json.loads((MODELS / "lemmas.json").read_text(encoding="utf-8"))}
    contractions = json.loads((MODELS / "contractions.json").read_text(encoding="utf-8"))
    return t, p, lem, {k: tuple(v) for k, v in contractions.items()}
