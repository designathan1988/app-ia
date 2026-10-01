"""Plano D, stage D1: train the labelled parser (``nucleo/lang/parser_rotulado.py``) and compare it with the current
one on the UD dev splits (gold tokenization, predicted tags, punctuation not scored). Test splits only at the gate.

The tags the parser learns from are the current tagger's own on the training sentences (as ``x2_parser`` did), so
the comparison isolates the parser.

Usage: python experiments/externo/d1_parser.py [pt|en] [epochs] [limit_train] [--teste]
"""
from __future__ import annotations

import ctypes
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
BANKS = {"pt": ("bosque", "petrogold", "porttinari"), "en": ("ewt",)}


def score(parse, tagger, sentences) -> dict:
    tot = uas = las = 0
    for s in sentences:
        words = [w.form for w in s.words]
        arcs = parse(words, tagger.tag(words))
        for w, (h, lab) in zip(s.words, arcs):
            if w.upos == "PUNCT":
                continue
            tot += 1
            uas += h == w.head
            las += h == w.head and lab == w.deprel
    return {"UAS": round(uas / tot, 4), "LAS": round(las / tot, 4)}


if __name__ == "__main__":
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    from nucleo.lang.parser_rotulado import LabelledParser
    from nucleo.lang.syntax import load_models, models_dir
    from nucleo.lang.ud import load

    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    lang = args[0] if args else "pt"
    epochs = int(args[1]) if len(args) > 1 else 10
    limit = int(args[2]) if len(args) > 2 else None
    split = "test" if "--teste" in sys.argv else "dev"
    tagger, old, _, _ = load_models(lang)
    train = load("train", BANKS[lang])[:limit]
    evals = {b: load(split, (b,)) for b in BANKS[lang]}
    t = time.time()
    new = LabelledParser()
    new.train(train, lambda s: tagger.tag([w.form for w in s.words]), epochs=epochs,
              log=lambda ep: print(f"  época {ep + 1}/{epochs} ({time.time() - t:.0f}s)", flush=True))
    secs = time.time() - t
    if limit is None:
        new.save(models_dir(lang))
    out = {"lang": lang, "split": split, "epocas": epochs, "frases_treino": len(train), "segundos_treino": round(secs)}
    for b, sents in evals.items():
        out[b] = {"atual": score(old.parse, tagger, sents), "D1": score(new.parse, tagger, sents)}
    print(json.dumps(out, ensure_ascii=False))
    dest = ROOT / "data" / "cache" / f"externo_d1_{lang}_{split}.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
