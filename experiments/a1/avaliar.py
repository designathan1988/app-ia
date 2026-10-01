"""A1 report: list and rank grounded actions on the builder's own pages; Top-K recall of the correct action on the
TEST split, by category and language, and simulation of the chosen interpretation in a sandbox copy of the builder.

Steps (all reproducible: python experiments/a1/avaliar.py [epochs]):
1. Every gold plan of TRAIN/DEV/TEST is executed in the headless builder: a gold that the builder refuses is a
   corpus error and is reported (it never counts as a model error).
2. TEST novelty: no TEST utterance may repeat or nearly repeat a TRAIN one (Jaccard of folded words >= 0.8); for
   items marked ``sinonimo``, the words of the utterance absent from all of TRAIN are listed.
3. The ranker is trained on TRAIN only (structured perceptron, averaged).
4. DEV and TEST: an item is correct at K when every gold action is among the K best candidates (the empty plan is
   the candidate NONE). Top-1 means the |gold| first candidates are exactly the gold actions.
5. Simulation (TEST): the top |gold| candidates are grounded and executed in a copy of the page; the resulting
   document is compared with the one the gold produces.
"""
from __future__ import annotations

import collections
import ctypes
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from dev import DEV  # noqa: E402
from paginas import PAGES  # noqa: E402
from teste import TEST  # noqa: E402
from treino import TRAIN  # noqa: E402

from nucleo.lang import ir  # noqa: E402
from nucleo.lang.acoes_ranker import Ranker  # noqa: E402
from nucleo.lang.mundo import Discourse, Page, Sandbox, dispatches, same_state  # noqa: E402
from nucleo.lang.values import fold  # noqa: E402

KS = (1, 3, 5, 10)


def history(item, pg) -> list:
    """The previous turn, executed before the item in the sandbox (the conversation's history)."""
    last = (item[5] or {}).get("last") or []
    return dispatches(ir.Plan(tuple(last)), pg, Discourse()) or [] if last else []


def context(item):
    lang, page, text, gold, cats, ctx = item
    ctx = ctx or {}
    pg = Page(PAGES[page], list(ctx.get("sel", [])))
    disc = Discourse(ctx.get("ref"), ir.Plan(tuple(ctx.get("last", []))) if ctx.get("last") else None)
    return pg, disc


def words(text: str) -> set:
    return {fold(w) for w in text.lower().replace("?", " ").replace(",", " ").split() if w}


def check_gold(sandbox, items, name) -> list:
    bad = []
    for it in items:
        pg, disc = context(it)
        steps = dispatches(ir.Plan(tuple(it[3])), pg, disc)
        if steps is None:
            bad.append((name, it[2], "not grounded"))
            continue
        _, _, ok = sandbox.run(pg.doc, pg.selection, history(it, pg) + steps)
        if not ok:
            bad.append((name, it[2], f"builder refused: {steps}"))
    return bad


def train(ranker: Ranker, items, epochs: int) -> dict:
    stats = collections.Counter()
    for ep in range(epochs):
        for it in items:
            pg, disc = context(it)
            cx = ranker.context(it[2], it[0], pg, disc)
            ranked = ranker.rank_cx(cx)
            golds = {a.canonical() for a in it[3]} or {"NONE"}
            if ep == epochs - 1:
                stats["gold_generated_last_epoch"] += all(g in {c.canonical() for c in ranked} for g in golds)
            wrong = [c for c in ranked if c.canonical() not in golds]
            for g in (it[3] or [None]):
                gc = ranker.gold(cx, g)
                if wrong and ranker.score(wrong[0].feats) >= ranker.score(gc.feats):
                    ranker.update(gc, wrong[0])
                    stats["updates"] += 1
    ranker.average()
    return dict(stats)


def evaluate(ranker: Ranker, items, sandbox=None) -> dict:
    by_cat = collections.defaultdict(collections.Counter)
    rows = []
    for it in items:
        lang, page, text, gold, cats, ctx = it
        pg, disc = context(it)
        ranked = ranker.rank_cx(ranker.context(text, lang, pg, disc))
        golds = [a.canonical() for a in gold] or ["NONE"]
        order = [c.canonical() for c in ranked]
        pos = [order.index(g) + 1 if g in order else None for g in golds]
        res = {"text": text, "lang": lang, "cats": cats.split(), "gold": golds, "rank": pos,
               "top": order[:5]}
        for k in KS:
            res[f"top{k}"] = all(p is not None and p <= (k if k > 1 else len(golds)) for p in pos)
        res["generated"] = all(p is not None for p in pos)
        if sandbox is not None:
            chosen = [c for c in ranked[:len(golds)]]
            plan = ir.Plan(tuple(c.action for c in chosen if c.action is not None))
            want = dispatches(ir.Plan(tuple(gold)), pg, disc)
            got = dispatches(plan, pg, disc)
            ok = False
            if want is not None and got is not None:
                pre = history(it, pg)
                d1, _, _ = sandbox.run(pg.doc, pg.selection, pre + want)
                d2, _, _ = sandbox.run(pg.doc, pg.selection, pre + got)
                ok = same_state(d1, d2, pg.doc)
            res["state"] = ok
        rows.append(res)
        for c in res["cats"] + [f"lang:{lang}", "ALL"]:
            by_cat[c]["n"] += 1
            for k in KS:
                by_cat[c][f"top{k}"] += res[f"top{k}"]
            by_cat[c]["generated"] += res["generated"]
            if "state" in res:
                by_cat[c]["state"] += res["state"]
    table = {c: {k: (round(100 * v / cnt["n"], 1) if k != "n" else v) for k, v in cnt.items()}
             for c, cnt in sorted(by_cat.items())}
    return {"table": table, "rows": rows}


def novelty(train_items, test_items) -> dict:
    tw = [words(it[2]) for it in train_items]
    vocab = set().union(*tw)
    near = []
    for it in test_items:
        w = words(it[2])
        for t, s in zip(train_items, tw):
            j = len(w & s) / max(1, len(w | s))
            if j >= 0.8:
                near.append((it[2], t[2], round(j, 2)))
                break
    unseen = {it[2]: sorted(words(it[2]) - vocab) for it in test_items if "sinonimo" in it[4].split()}
    return {"near_duplicates": near, "sinonimo_unseen_words": unseen}


if __name__ == "__main__":
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    epochs = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    t0 = time.time()
    sb = Sandbox()
    try:
        bad = check_gold(sb, TRAIN, "train") + check_gold(sb, DEV, "dev") + check_gold(sb, TEST, "test")
        print(json.dumps({"gold_errors": bad}, ensure_ascii=False, indent=1), flush=True)
        nov = novelty(TRAIN, TEST)
        print(json.dumps({"near_duplicates": nov["near_duplicates"]}, ensure_ascii=False), flush=True)
        r = Ranker()
        st = train(r, TRAIN, epochs)
        print(json.dumps({"train": st, "secs": round(time.time() - t0)}), flush=True)
        dev = evaluate(r, DEV)
        print("DEV", json.dumps(dev["table"].get("ALL"), ensure_ascii=False), flush=True)
        test = evaluate(r, TEST, sb)
        print("TEST", json.dumps(test["table"], ensure_ascii=False, indent=0), flush=True)
    finally:
        sb.close()
    out = {"counts": {"train": len(TRAIN), "dev": len(DEV), "test": len(TEST)}, "gold_errors": bad,
           "novelty": nov, "train": st, "dev": dev, "test": test, "epochs": epochs, "secs": round(time.time() - t0)}
    (ROOT / "data" / "cache" / "a1_relatorio.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                                              encoding="utf-8")
    print("secs", round(time.time() - t0))
