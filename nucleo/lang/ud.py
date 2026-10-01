"""Universal Dependencies treebanks (CoNLL-U): sentences as syntactic words, and the contractions they come from.

Portuguese writes "do", "na", "pelo" as one word, but syntax sees two ("de o", "em a", "por o"). CoNLL-U keeps both
views: a multiword-token line ("5-6 do") followed by its syntactic words. The reader keeps the syntactic words for
the parser, and collects every contraction (surface form -> words) as data, so the tokenizer splits contractions
the way the treebanks do rather than by a hand-written list.
"""

from __future__ import annotations

import pathlib
from collections import Counter
from dataclasses import dataclass, field

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"
TREEBANKS = {"bosque": "ud-Bosque/pt_bosque", "petrogold": "ud-PetroGold/pt_petrogold",
             "porttinari": "ud-Porttinari/pt_porttinari", "ewt": "ud-EWT/en_ewt"}


@dataclass
class Word:
    form: str
    lemma: str
    upos: str
    feats: str
    head: int  # 0 = root; words are numbered from 1
    deprel: str


@dataclass
class Sentence:
    sid: str
    text: str
    words: list[Word]
    tokens: list[tuple[str, list[int]]] = field(default_factory=list)  # surface tokens -> word indices (1-based)

    def projective(self) -> bool:
        arcs = [(min(i, w.head), max(i, w.head)) for i, w in enumerate(self.words, 1) if w.head > 0]
        for a, b in arcs:
            for c, d in arcs:
                if a < c < b < d:
                    return False
        return True


def read(path: str | pathlib.Path) -> list[Sentence]:
    out: list[Sentence] = []
    words: list[Word] = []
    tokens: list = []
    sid = text = ""
    pending_mwt: tuple[str, int, int] | None = None
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            if words:
                out.append(Sentence(sid, text, words, tokens))
            words, tokens, sid, text, pending_mwt = [], [], "", "", None
            continue
        if line.startswith("# sent_id"):
            sid = line.split("=", 1)[1].strip()
            continue
        if line.startswith("# text"):
            text = line.split("=", 1)[1].strip()
            continue
        if line.startswith("#"):
            continue
        cols = line.split("\t")
        if "." in cols[0]:
            continue  # empty nodes
        if "-" in cols[0]:
            a, b = (int(x) for x in cols[0].split("-"))
            tokens.append((cols[1], list(range(a, b + 1))))
            pending_mwt = (cols[1], a, b)
            continue
        i = int(cols[0])
        words.append(Word(cols[1], cols[2], cols[3], cols[5], int(cols[6]) if cols[6] != "_" else 0, cols[7]))
        if pending_mwt is None or i > pending_mwt[2]:
            tokens.append((cols[1], [i]))
            pending_mwt = None
    if words:
        out.append(Sentence(sid, text, words, tokens))
    return out


def load(split: str, banks=("bosque", "petrogold", "porttinari")) -> list[Sentence]:
    out = []
    for b in banks:
        out += read(DATA / f"{TREEBANKS[b]}-ud-{split}.conllu")
    return out


def contractions(sentences: list[Sentence]) -> dict[str, tuple[str, ...]]:
    """Surface contraction (lowercase) -> its most frequent expansion into syntactic words."""
    seen: dict[str, Counter] = {}
    for s in sentences:
        for form, idx in s.tokens:
            if len(idx) > 1:
                seen.setdefault(form.lower(), Counter())[tuple(s.words[i - 1].form.lower() for i in idx)] += 1
    return {k: c.most_common(1)[0][0] for k, c in seen.items()}
