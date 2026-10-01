"""Plano D, stage D2: semantic roles (who did what to whom, from where, to where), learned from human annotation.

- **Frames:** PropBank 3.4 frame files. Every roleset has numbered roles, each with its *function* (PAG agent, PPT
  patient/theme, GOL goal, SRC source, DIR direction, LOC location, VSP attribute, ...), and links to VerbNet classes
  and FrameNet frames.
- **Rolesets of a lemma:** counted in the Universal Propositions training data (EWT, gold; Bosque, Portuguese verbs
  annotated with English rolesets: "encontrar" -> meet.03). No hand-written verb list.
- **Labeller:** two averaged perceptrons in the style of Björkelund et al. (2009): predicate identification per
  word, and argument labelling per (predicate, candidate) with the dependency path, position, voice, the predicate's
  lemma and the candidate's word, category, relation and preposition. Candidates are pruned as Xue & Palmer (2004)
  do for dependencies: the dependents of the predicate and of its ancestors.

Trained on the trees the engine's own parser produces, so it learns from what it will see.
"""

from __future__ import annotations

import json
import pathlib
import random
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache

from .perceptron import AveragedPerceptron

ROOT = pathlib.Path(__file__).resolve().parents[2]
FRAMES_DIR = ROOT / "data" / "externo" / "propbank" / "propbank-frames-main" / "frames"
UP = ROOT / "data" / "externo" / "up2"
MODELS = ROOT / "data" / "models"
NONE = "_"
FRAME_ID = re.compile(r"^[^\s.]+\.\d\d$")


# -- frames ----------------------------------------------------------------------------------------------------------
@dataclass
class Roleset:
    id: str
    name: str
    roles: dict = field(default_factory=dict)  # "0" -> (function, description)
    verbnet: frozenset = frozenset()
    framenet: frozenset = frozenset()


@lru_cache(maxsize=1)
def rolesets() -> dict[str, Roleset]:
    out = {}
    for path in sorted(FRAMES_DIR.glob("*.xml")):
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        for rs in root.iter("roleset"):
            r = Roleset(rs.get("id"), rs.get("name") or "")
            vn, fn = set(), set()
            for role in rs.iter("role"):
                r.roles[role.get("n", "").upper()] = ((role.get("f") or "").upper(), role.get("descr") or "")
                for link in role.iter("rolelink"):
                    (vn if link.get("resource") == "VerbNet" else fn).add(link.get("class"))
            r.verbnet, r.framenet = frozenset(vn), frozenset(fn)
            out[r.id] = r
    return out


def function_of(roleset_id: str, label: str) -> str:
    """The function of a numbered argument in a roleset (ARG2 of move.01 -> GOL); modifiers keep their own name
    (ARGM-LOC -> LOC)."""
    lab = label.upper().replace("ARG", "A")
    if lab.startswith("AM-"):
        return lab[3:]
    rs = rolesets().get(roleset_id)
    if rs is None:
        return ""
    return rs.roles.get(lab[1:], ("", ""))[0]


# -- data ------------------------------------------------------------------------------------------------------------
@dataclass
class UPSentence:
    words: list
    preds: list  # [{"i": 1-based, "frame": str, "args": {i: label}}]


def read_up(path: pathlib.Path) -> list[UPSentence]:
    sents, rows = [], []
    for line in path.read_text(encoding="utf-8").splitlines() + [""]:
        if not line.strip():
            if rows:
                sents.append(_up_sentence(rows))
            rows = []
        elif not line.startswith("#"):
            cols = line.split("\t")
            if "-" in cols[0] or "." in cols[0]:
                continue
            rows.append(cols)
    return sents


def _up_sentence(rows) -> UPSentence:
    fcol = next((j for r in rows for j in range(8, len(r)) if FRAME_ID.match(r[j])), None)
    preds = []
    if fcol is not None:
        idx = [k for k, r in enumerate(rows) if len(r) > fcol and FRAME_ID.match(r[fcol])]
        for n, k in enumerate(idx):
            col = fcol + 1 + n
            args = {m + 1: _norm(r[col]) for m, r in enumerate(rows)
                    if len(r) > col and r[col] not in ("_", "", "V") and m != k}
            preds.append({"i": k + 1, "frame": rows[k][fcol], "args": args})
    return UPSentence([r[1] for r in rows], preds)


def _norm(label: str) -> str:
    """One inventory for both releases: A0/ARG0 -> A0, AM-TMP/ARGM-TMP -> AM-TMP; continuation and reference
    prefixes (C-, R-) kept."""
    lab = label.upper()
    pre = ""
    if lab[:2] in ("C-", "R-"):
        pre, lab = lab[:2], lab[2:]
    lab = lab.replace("ARGM", "AM").replace("ARG", "A")
    return pre + lab


# -- features --------------------------------------------------------------------------------------------------------
def _path(tokens, a: int, b: int) -> tuple[str, int]:
    """The dependency path between two tokens (relations up to the common ancestor, then down) and its length."""
    by = {t.i: t for t in tokens}

    def up(i):
        chain = [i]
        while i in by and by[i].head != 0 and len(chain) < 40:
            i = by[i].head
            chain.append(i)
        return chain

    ua, ub = up(a), up(b)
    common = next((x for x in ua if x in set(ub)), None)
    if common is None:
        return "?", 9
    rel = lambda i: by[i].deprel.split(":")[0] if i in by else "root"  # noqa: E731
    left = [rel(i) for i in ua[:ua.index(common)]]
    right = [rel(i) for i in ub[:ub.index(common)]]
    return "^".join(left) + "|" + "v".join(reversed(right)), len(left) + len(right)


def _candidates(tokens, p: int) -> list[int]:
    """Xue & Palmer pruning over dependencies: the dependents of the predicate, then of each of its ancestors."""
    by = {t.i: t for t in tokens}
    kids = defaultdict(list)
    for t in tokens:
        kids[t.head].append(t.i)
    out, cur, seen = [], p, set()
    while cur and cur not in seen:
        seen.add(cur)
        out += [k for k in kids[cur] if k != p]
        cur = by[cur].head if cur in by else 0
    return [i for i in dict.fromkeys(out) if by[i].upos != "PUNCT"]


def _case(tokens, i: int) -> str:
    for t in tokens:
        if t.head == i and t.deprel.split(":")[0] in ("case", "mark"):
            return t.form.lower()
    return "-"


def _passive(tokens, p: int) -> bool:
    return any(t.head == p and t.deprel in ("aux:pass", "nsubj:pass", "expl:pass") for t in tokens)


def pred_features(tokens, t) -> list[str]:
    by = {x.i: x for x in tokens}
    h = by.get(t.head)
    nk = sum(1 for x in tokens if x.head == t.i)
    return ["b", "l" + t.lemma.lower(), "u" + t.upos, "r" + t.deprel, "lu" + t.lemma.lower() + t.upos,
            "hu" + (h.upos if h else "ROOT"), "ur" + t.upos + t.deprel, "nk" + str(min(nk, 4)),
            "f" + t.form.lower()[-3:]]


def arg_features(tokens, p, a, lemma: str) -> list[str]:
    path, n = _path(tokens, a.i, p.i)
    side = "L" if a.i < p.i else "R"
    voice = "pass" if _passive(tokens, p.i) else "act"
    case = _case(tokens, a.i)
    rel = a.deprel
    return ["b", "path" + path, "pathv" + path + voice, "plen" + str(min(n, 5)), "side" + side,
            "sv" + side + voice, "rel" + rel, "relv" + rel + voice + side, "au" + a.upos, "aw" + a.form.lower(),
            "al" + a.lemma.lower(), "pl" + lemma, "pl.rel" + lemma + "/" + rel, "pl.case" + lemma + "/" + case,
            "case" + case, "case.rel" + case + rel, "pl.path" + lemma + path, "pu" + p.upos,
            "direct" + str(a.head == p.i), "aw.case" + a.lemma.lower() + "/" + case]


# -- the labeller ----------------------------------------------------------------------------------------------------
class RoleLabeller:
    def __init__(self) -> None:
        self.pred = AveragedPerceptron()
        self.pred.classes = {"P", NONE}
        self.args = AveragedPerceptron()
        self.lexicon: dict[str, dict[str, int]] = {}  # lemma -> roleset -> count

    def roleset(self, lemma: str) -> str | None:
        c = self.lexicon.get(lemma.lower())
        if c:
            return max(c.items(), key=lambda kv: (kv[1], kv[0]))[0]
        cand = f"{lemma.lower()}.01"
        return cand if cand in rolesets() else None

    def label(self, tokens) -> list[dict]:
        """[{"i", "lemma", "roleset", "args": {i: (label, function)}}] for every predicate found."""
        out = []
        for t in tokens:
            if t.upos not in ("VERB", "AUX", "NOUN", "ADJ"):
                continue
            if self.pred.predict(pred_features(tokens, t)) != "P":
                continue
            rs = self.roleset(t.lemma)
            args = {}
            for i in _candidates(tokens, t.i):
                a = next(x for x in tokens if x.i == i)
                lab = self.args.predict(arg_features(tokens, t, a, t.lemma.lower()))
                if lab != NONE:
                    args[i] = (lab, function_of(rs, lab) if rs else "")
            out.append({"i": t.i, "lemma": t.lemma, "roleset": rs, "args": args})
        return out

    def train(self, data: list[tuple[list, UPSentence]], epochs: int = 8, seed: int = 0, log=None) -> None:
        """``data``: (tokens from the engine's parser, the UP annotation of the same words)."""
        rng = random.Random(seed)
        labels = {NONE}
        for toks, s in data:
            by = {t.i: t for t in toks}
            for p in s.preds:
                labels |= set(p["args"].values())
                if p["i"] in by:
                    self.lexicon.setdefault(by[p["i"]].lemma.lower(), Counter())[p["frame"]] += 1
        self.args.classes = labels
        self.lexicon = {k: dict(v) for k, v in self.lexicon.items()}
        data = list(data)
        for ep in range(epochs):
            rng.shuffle(data)
            for toks, s in data:
                gold = {p["i"]: p for p in s.preds}
                for t in toks:
                    if t.upos not in ("VERB", "AUX", "NOUN", "ADJ"):
                        continue
                    f = pred_features(toks, t)
                    g = self.pred.predict(f)
                    truth = "P" if t.i in gold else NONE
                    self.pred.update(truth, g, f)
                    if truth != "P":
                        continue
                    for i in _candidates(toks, t.i):
                        a = next(x for x in toks if x.i == i)
                        fa = arg_features(toks, t, a, t.lemma.lower())
                        self.args.update(gold[t.i]["args"].get(i, NONE), self.args.predict(fa), fa)
            if log:
                log(ep)
        self.pred.average()
        self.args.average()

    def save(self, folder: pathlib.Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        self.pred.save(folder / "papeis_pred.json")
        self.args.save(folder / "papeis_args.json")
        (folder / "papeis_lexico.json").write_text(json.dumps(self.lexicon, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, folder: pathlib.Path) -> "RoleLabeller":
        r = cls()
        r.pred = AveragedPerceptron.load(folder / "papeis_pred.json")
        r.args = AveragedPerceptron.load(folder / "papeis_args.json")
        r.lexicon = json.loads((folder / "papeis_lexico.json").read_text(encoding="utf-8"))
        return r
