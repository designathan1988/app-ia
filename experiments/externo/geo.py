"""Roteiro CCG, E0: replicate lexicon induction on GeoQuery (Geo880, lambda calculus) before using it on the builder.

Data: XSemPLR ``dataset/mgeoquery`` (Zelle & Mooney 1996; lambda forms of Zettlemoyer & Collins 2005; translations
by Jones et al. 2012): 548 train + 49 dev (= the standard 600) and 277 test (the standard 280 minus duplicates).
Training uses train+dev; the test is measured once per configuration. Metric (UBL §7): exact match of the logical
form — recall = correct / all, precision = correct / answered, F1. Published (Geo880 test, lambda): UBL P 94.1
R 85.0 F1 89.3 (EMNLP 2010, Table 3); FUBL F1 88.6 (EMNLP 2011, Table 3). Goal O1: F1 >= 85.0.

The entity names (UBL's NP list) are derived from the constants' own names ("new_york:s" -> "new york";
"austin_tx:c" -> "austin"; "mississippi_river:r" -> "mississippi river" and "mississippi").

Usage: python experiments/externo/geo.py [lang=en] [epochs=10] [limit_train] [limit_test] [beam=40]
"""
from __future__ import annotations

import ctypes
import json
import pathlib
import random
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data" / "externo" / "xsemplr" / "mgeoquery"


def load(split: str, lang: str) -> list:
    from nucleo.lang.ccg import logica as L

    out = []
    for r in json.loads((DATA / f"{split}.json").read_text(encoding="utf-8")):
        words = [w for w in r["question"][lang].lower().replace("?", " ").replace(",", " ").split() if w]
        out.append((words, L.parse(r["mr"]["lambda"])))
    return out


def names(pairs) -> list:
    from nucleo.lang.ccg import logica as L

    out, seen = [], set()
    for _, z in pairs:
        for c in L.constants(z):
            if L.is_fn(c.type) or c.name.isdigit():
                continue
            parts = c.name.split("_")
            variants = [parts]
            if L.type_str(c.type) == "c" and len(parts) > 1 and len(parts[-1]) == 2:
                variants = [parts[:-1]]
            if parts[-1] in ("river",) and len(parts) > 1:
                variants.append(parts[:-1])
            for v in variants:
                k = (tuple(v), str(c))
                if k not in seen:
                    seen.add(k)
                    out.append((v, c))
    return out


def evaluate(model, test) -> dict:
    from nucleo.lang.ccg import logica as L

    right = answered = 0
    for words, z in test:
        it, _ = model.predict(words)
        if it is None:
            continue
        answered += 1
        right += L.canonical(it.lf) == L.canonical(z)
    n = len(test)
    p = right / answered if answered else 0.0
    r = right / n if n else 0.0
    return {"n": n, "answered": answered, "right": right, "P": round(100 * p, 1), "R": round(100 * r, 1),
            "F1": round(100 * 2 * p * r / (p + r), 1) if p + r else 0.0}


if __name__ == "__main__":
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    from nucleo.lang.ccg import logica as L
    from nucleo.lang.ccg import ubl

    a = sys.argv[1:]
    lang = a[0] if a else "en"
    epochs = int(a[1]) if len(a) > 1 else 10
    lim_tr = int(a[2]) if len(a) > 2 and a[2] != "-" else None
    lim_te = int(a[3]) if len(a) > 3 and a[3] != "-" else None
    beam = int(a[4]) if len(a) > 4 else 40
    train = (load("train", lang) + load("dev", lang))[:lim_tr]
    test = load("test", lang)[:lim_te]
    every = load("train", lang) + load("dev", lang) + load("test", lang)
    t0 = time.time()
    ibm = ubl.ibm1([(w, [str(c) for c in L.constants(z)]) for w, z in train])
    lex = ubl.Lexicon()
    model = ubl.Model(lex, ibm, beam=beam)
    ubl.seed(lex, model, train, names(every))
    rng = random.Random(0)
    log = []
    for ep in range(epochs):
        order = list(train)
        rng.shuffle(order)
        found = 0
        for words, z in order:
            found += model.update(words, z)
        line = {"epoch": ep + 1, "correct_parse_found": found, "lexemes": len(lex.lexemes),
                "templates": len(lex.templates), "secs": round(time.time() - t0)}
        print(json.dumps(line), flush=True)
        log.append(line)
    res = evaluate(model, test)
    res.update({"lang": lang, "epochs": epochs, "train": len(train), "beam": beam,
                "secs": round(time.time() - t0)})
    print(json.dumps(res), flush=True)
    dest = ROOT / "data" / "cache" / f"externo_geo_{lang}.json"
    dest.write_text(json.dumps({"result": res, "log": log}, indent=1), encoding="utf-8")
