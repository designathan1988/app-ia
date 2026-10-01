"""X3: how often the right tree is among the k best (plan §3.4).

The greedy parser keeps one tree. Robustness by reinterpretation needs the right tree to be among the
alternatives the parser can offer. This experiment measures, on the UD test sets (all sentences, and the
imperatives alone):
- the greedy UAS;
- the beam's best UAS;
- the oracle UAS of the best of k (tag sequences x trees).

Usage: python experiments/x3_kbest.py [pt|en] [k]
"""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from nucleo.lang.syntax import load_models  # noqa: E402
from nucleo.lang.ud import load  # noqa: E402
from nucleo.session import low_priority  # noqa: E402


def candidates(tagger, parser, words, k):
    out = []
    for ts, tags in tagger.tag_kbest(words, k=2):
        for ps, heads in parser.parse_kbest(words, tags, k=k):
            out.append((ts + ps, tags, heads))
    return sorted(out, key=lambda x: -x[0])


def measure(tagger, parser, sentences, k):
    tot = greedy = beam = oracle = 0
    for s in sentences:
        words = [w.form for w in s.words]
        gold = [w.head for w in s.words]
        scored = [i for i, w in enumerate(s.words) if w.upos != "PUNCT"]
        g = parser.parse_heads(words, tagger.tag(words))
        cands = candidates(tagger, parser, words, k)
        tot += len(scored)
        greedy += sum(g[i] == gold[i] for i in scored)
        beam += sum(cands[0][2][i] == gold[i] for i in scored)
        oracle += max(sum(h[i] == gold[i] for i in scored) for _, _, h in cands)
    return greedy / tot, beam / tot, oracle / tot


if __name__ == "__main__":
    low_priority()
    lang = sys.argv[1] if len(sys.argv) > 1 else "pt"
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    tagger, parser, _, _ = load_models(lang)
    test = load("test", ("ewt",)) if lang == "en" else load("test")
    imp = [s for s in test if any("Mood=Imp" in w.feats for w in s.words)]
    t0 = time.time()
    for name, ss in (("imperativas", imp), ("todas (300)", test[:300])):
        g, b, o = measure(tagger, parser, ss, k)
        print(f"{lang} {name} ({len(ss)}): UAS guloso {g:.2%} | feixe {b:.2%} | oráculo k={k} {o:.2%}")
    print(f"{time.time() - t0:.0f}s")
