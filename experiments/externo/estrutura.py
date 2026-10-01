"""Plano D, structure layer: the engine's trees and logical forms against human annotation it never saw.

1. **Trees** — UAS/LAS of the engine's own tagger and parser on the UD test splits (Bosque, PetroGold, Porttinari
   for pt; EWT for en), gold tokenization, punctuation not scored (the usual convention).
2. **Who did what to whom** — the predicates and arguments of the logical form (``logic_form.build`` on the engine's
   own tree) against the Universal Propositions (Akbik et al. 2015; PropBank roles over UD): EWT (English, gold) and
   Bosque (Portuguese, projected from English: silver, recall of raised arguments known to be low).
   - predicate identification: the logical form's predicate heads vs the tokens UP gives a frame (P/R/F1);
   - argument identification, unlabeled: for each predicate found by both, the heads of its roles vs the heads UP
     marks with a role (P/R/F1);
   - core roles: of the arguments found by both, how often the logical form's subj is UP's ARG0/A0 and its obj is
     UP's ARG1/A1 (a fixed adapter between the two inventories, documented here, not tuned).

Splits: ``dev`` while working, ``test`` only at the gates.

Usage: python experiments/externo/estrutura.py [dev|test] [limit]
"""
from __future__ import annotations

import ctypes
import json
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))
UP = ROOT / "data" / "externo" / "up2"
UD_BANKS = {"pt": ("bosque", "petrogold", "porttinari"), "en": ("ewt",)}
UP_FILES = {"en": "en_ewt-up-{}.conllu", "pt": "pt_bosque-up-{}.conllu"}
FRAME = re.compile(r"^[^\s.]+\.\d\d$")


def trees(split: str, lang: str) -> dict:
    from x2_parser import evaluate

    from nucleo.lang.syntax import load_models
    from nucleo.lang.ud import load

    tagger, parser, _, _ = load_models(lang)
    out = {}
    for bank in UD_BANKS[lang]:
        pos, u, l = evaluate(tagger, parser, load(split, (bank,)))
        out[bank] = {"UPOS": round(pos, 4), "UAS": round(u, 4), "LAS": round(l, 4)}
    return out


def read_up(path: pathlib.Path) -> list[dict]:
    """Sentences of a UP file: words, and for each predicate (in order) its token and its arguments {token: role}.
    The frame column is found per file (the English and Portuguese releases lay the columns out differently)."""
    sents, rows = [], []
    for line in path.read_text(encoding="utf-8").splitlines() + [""]:
        if not line.strip():
            if rows:
                sents.append(_sentence(rows))
            rows = []
        elif not line.startswith("#"):
            cols = line.split("\t")
            if "-" in cols[0] or "." in cols[0]:
                continue  # multiword token lines and empty nodes: the words are listed on their own lines
            rows.append(cols)
    return sents


def _sentence(rows) -> dict:
    fcol = next((j for r in rows for j in range(8, len(r)) if FRAME.match(r[j])), None)
    words = [r[1] for r in rows]
    preds = []
    if fcol is not None:
        pred_rows = [k for k, r in enumerate(rows) if len(r) > fcol and FRAME.match(r[fcol])]
        for n, k in enumerate(pred_rows):
            col = fcol + 1 + n
            args = {}
            for m, r in enumerate(rows):
                role = r[col] if len(r) > col else "_"
                if role not in ("_", "", "V") and m != k:
                    args[m + 1] = role
            preds.append({"i": k + 1, "frame": rows[k][fcol], "args": args})
    return {"words": words, "preds": preds}


def _walk(preds, seen=None):
    """Every predicate of a logical form, also the ones nested as roles (content clauses) or coordinated."""
    from nucleo.lang import logic_form as lf

    seen = set() if seen is None else seen
    for p in preds:
        if id(p) in seen:
            continue
        seen.add(id(p))
        yield p
        yield from _walk(p.conj, seen)
        yield from _walk([x for _, _, x in p.roles if isinstance(x, lf.Predicate)], seen)


def _head_of(x) -> int | None:
    h = getattr(x, "head", None)
    return getattr(h, "i", None)


def roles(split: str, lang: str, limit: int | None) -> dict:
    from nucleo.lang import langs
    from nucleo.lang import logic_form as lf
    from nucleo.lang.base import make_tokens
    from nucleo.lang.syntax import load_models

    sents = read_up(UP / UP_FILES[lang].format(split))[:limit]
    tagger, parser, _, _ = load_models(lang)
    pt = pp = pg = 0  # predicates: matched, predicted, gold
    at = ap = ag = 0  # arguments of matched predicates
    core_ok = core_n = 0
    errors = 0
    a0 = ("ARG0", "A0")
    a1 = ("ARG1", "A1")
    with langs.use(lang):
        for s in sents:
            words = s["words"]
            gold = {p["i"]: p for p in s["preds"]}
            try:
                tags = tagger.tag(words)
                arcs = parser.parse(words, tags)
                form = lf.build(make_tokens(words, tags, arcs))
                mine = {}
                for p in _walk(form.predicates):
                    mine.setdefault(p.head.i, p)
            except Exception:  # noqa: BLE001 — a crash counts as finding nothing, and is counted
                errors += 1
                mine = {}
            pp += len(mine)
            pg += len(gold)
            for i in set(mine) & set(gold):
                pt += 1
                said = {}
                for role, _, x in mine[i].roles:
                    h = _head_of(x)
                    if h is not None and h != i:
                        said.setdefault(h, role)
                g = gold[i]["args"]
                ap += len(said)
                ag += len(g)
                for h in set(said) & set(g):
                    at += 1
                    if said[h] in ("subj", "obj"):
                        core_n += 1
                        core_ok += said[h] == "subj" and g[h] in a0 or said[h] == "obj" and g[h] in a1

    def prf(t, p, g):
        pr, rc = t / max(1, p), t / max(1, g)
        return {"P": round(pr, 4), "R": round(rc, 4), "F1": round(2 * pr * rc / max(1e-9, pr + rc), 4)}

    return {"frases": len(sents), "predicados": prf(pt, pp, pg), "argumentos": prf(at, ap, ag),
            "papeis_nucleares": round(core_ok / max(1, core_n), 4), "nucleares_n": core_n, "excecoes": errors}


if __name__ == "__main__":
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    args = sys.argv[1:]
    split = args[0] if args else "dev"
    limit = int(args[1]) if len(args) > 1 else None
    out = {}
    for lang in ("pt", "en"):
        t = time.time()
        out[lang] = {"arvores": trees(split, lang) if limit is None else None, "papeis": roles(split, lang, limit)}
        out[lang]["segundos"] = round(time.time() - t, 1)
        print(lang, json.dumps(out[lang], ensure_ascii=False))
    if limit is None:
        dest = ROOT / "data" / "cache" / f"externo_estrutura_{split}.json"
        dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print("gravado em", dest)
