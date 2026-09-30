"""Averaged perceptron over sparse features: the only learning machinery of the language layer.

It is a linear model, with no neural network. Every decision is the sum of a few weights per active feature, so a
decision can be explained by listing the features that voted for it. The weights are averaged over all updates
(Collins 2002), which is what makes a plain perceptron competitive.
"""

from __future__ import annotations

import json
import pathlib
from collections import defaultdict


class AveragedPerceptron:
    def __init__(self) -> None:
        self.weights: dict[str, dict[str, float]] = {}
        self.classes: set[str] = set()
        self._totals: dict[tuple[str, str], float] = defaultdict(float)
        self._stamps: dict[tuple[str, str], int] = defaultdict(int)
        self.i = 0

    def scores(self, features) -> dict[str, float]:
        s: dict[str, float] = defaultdict(float)
        for f in features:
            w = self.weights.get(f)
            if w:
                for c, v in w.items():
                    s[c] += v
        return s

    def predict(self, features, allowed=None) -> str:
        s = self.scores(features)
        cands = allowed if allowed is not None else self.classes
        return max(cands, key=lambda c: (s.get(c, 0.0), c))

    def update(self, truth: str, guess: str, features) -> None:
        self.i += 1
        if truth == guess:
            return
        for f in features:
            w = self.weights.setdefault(f, {})
            for c, delta in ((truth, 1.0), (guess, -1.0)):
                key = (f, c)
                old = w.get(c, 0.0)
                self._totals[key] += (self.i - self._stamps[key]) * old
                self._stamps[key] = self.i
                w[c] = old + delta

    def average(self) -> None:
        for f, w in self.weights.items():
            for c, v in list(w.items()):
                key = (f, c)
                total = self._totals[key] + (self.i - self._stamps[key]) * v
                avg = round(total / max(self.i, 1), 4)
                if avg:
                    w[c] = avg
                else:
                    del w[c]
        self.weights = {f: w for f, w in self.weights.items() if w}
        self._totals.clear()
        self._stamps.clear()

    def save(self, path: pathlib.Path) -> None:
        path.write_text(json.dumps({"classes": sorted(self.classes), "weights": self.weights}), encoding="utf-8")

    @classmethod
    def load(cls, path: pathlib.Path) -> "AveragedPerceptron":
        d = json.loads(path.read_text(encoding="utf-8"))
        m = cls()
        m.classes = set(d["classes"])
        m.weights = d["weights"]
        return m
