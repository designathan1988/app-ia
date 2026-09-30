"""X2: how good is a linear (non-neural) tagger + dependency parser for Portuguese, trained on the UD treebanks?

Judged on the treebanks' own test splits (human annotation), with gold tokenization, as UD evaluations usually are.
Reports UPOS accuracy, UAS and LAS per treebank, and LAS on imperative sentences (the form of requests), which are
rare in news text. Reference: UDPipe 2 and Stanza (neural) reach LAS ~84-95 / ~80-93 on these treebanks.

Usage: python experiments/x2_parser.py [epochs]
"""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from nucleo.lang.syntax import Lemmatizer, Parser, Tagger, save  # noqa: E402
from nucleo.lang.ud import contractions, load  # noqa: E402


def evaluate(tagger, parser, sentences, predicted_tags=True):
    tot = pos_ok = uas = las = 0
    for s in sentences:
        words = [w.form for w in s.words]
        tags = tagger.tag(words) if predicted_tags else [w.upos for w in s.words]
        arcs = parser.parse(words, tags)
        for w, t, (h, lab) in zip(s.words, tags, arcs):
            if w.upos == "PUNCT":
                continue  # the usual convention: punctuation is not scored
            tot += 1
            pos_ok += t == w.upos
            uas += h == w.head
            las += h == w.head and lab == w.deprel
    return pos_ok / tot, uas / tot, las / tot


if __name__ == "__main__":
    epochs = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    train, test = load("train"), {b: load("test", (b,)) for b in ("bosque", "petrogold", "porttinari")}
    t0 = time.time()
    tagger = Tagger()
    tagger.train(train, epochs=epochs)
    t1 = time.time()
    # the parser learns from the tags the tagger will actually produce (jackknifing would be better; recorded)
    parser = Parser()
    parser.train(train, lambda s: tagger.tag([w.form for w in s.words]), epochs=epochs)
    t2 = time.time()
    lem = Lemmatizer()
    lem.train(train)
    save(tagger, parser, lem, contractions(train))
    print(f"treino: etiquetador {t1 - t0:.0f}s, analisador {t2 - t1:.0f}s ({len(train)} frases, {epochs} épocas)")
    for bank, sents in test.items():
        pos, u, l = evaluate(tagger, parser, sents)
        _, ug, lg = evaluate(tagger, parser, sents, predicted_tags=False)
        print(f"{bank:11s} UPOS {pos:.2%}  UAS {u:.2%}  LAS {l:.2%}   (etiquetas-ouro: UAS {ug:.2%} LAS {lg:.2%})")
    imp = [s for b in test.values() for s in b if any("Mood=Imp" in w.feats for w in s.words)]
    pos, u, l = evaluate(tagger, parser, imp)
    print(f"imperativas ({len(imp)} frases de teste): UPOS {pos:.2%}  UAS {u:.2%}  LAS {l:.2%}")
