"""X2 for English: the same linear tagger and parser, trained on UD English-EWT (no rule changes), for the
English side of the language-independent pipeline (docs/significado.md). Usage: python experiments/x2_parser_en.py"""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from x2_parser import evaluate  # noqa: E402
from nucleo.lang.syntax import Lemmatizer, Parser, Tagger, save  # noqa: E402
from nucleo.lang.ud import contractions, load  # noqa: E402
from nucleo.session import low_priority  # noqa: E402

if __name__ == "__main__":
    low_priority()
    epochs = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    train, test = load("train", ("ewt",)), load("test", ("ewt",))
    t0 = time.time()
    tagger = Tagger()
    tagger.train(train, epochs=epochs)
    parser = Parser()
    parser.train(train, lambda s: tagger.tag([w.form for w in s.words]), epochs=epochs)
    lem = Lemmatizer()
    lem.train(train)
    save(tagger, parser, lem, contractions(train), lang="en")
    pos, u, l = evaluate(tagger, parser, test)
    print(f"EWT: UPOS {pos:.2%} UAS {u:.2%} LAS {l:.2%} ({len(train)} frases, {time.time() - t0:.0f}s)")
    imp = [s for s in test if any("Mood=Imp" in w.feats for w in s.words)]
    pos, u, l = evaluate(tagger, parser, imp)
    print(f"imperativas ({len(imp)}): UPOS {pos:.2%} UAS {u:.2%} LAS {l:.2%}")
