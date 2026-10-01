"""A1 evaluation (reproducible): python experiments/a1/avaliar.py [epochs] [--sem-ablacao] [--recongelar]

1. **Freezing.** Every dataset is hashed (its utterances, pages, contexts and gold IR). The hashes are written to
   experiments/a1/congelado.json on the first run; any later change aborts the evaluation.
2. **Leakage** between TRAIN and every evaluation set: identical utterances; identical after normalization (case,
   punctuation); after removing accents; the same words in another order; near duplicates (Jaccard >= 0.8).
3. **Gold validation.** Every gold plan is executed in the headless builder; a refused gold is a corpus error.
4. **Training** on TRAIN only. The gold's features update the weights (forced decoding): the only place the model
   reads a gold.
5. **Evaluation** with *exactly* the pipeline a user's sentence goes through — ``generate(context)`` then
   ``rank(context, candidates)``; the gold is compared with the output only afterwards. Reported separately:
   - candidate recall@K: every gold action among the generator's K first candidates (A1 criterion, fixed before
     the run: recall@10 >= 95% of TEST);
   - ranking top-K, after re-ranking with the cross features;
   - semantic parse (IR) correct; grounded action (the builder commands) correct; final sandbox state correct;
   - by category, by language, and automatically: lexical unseen, inflection unseen; the compositional holdout,
     verified (a combination absent from TRAIN);
   - pt/en IR equivalence (same page, context and gold);
   - contrast pairs (both right);
   - dialogues, with the gold history and end to end;
   - candidates per sentence (mean, p50, p95, max) and latencies.
6. **Ablations**: without context, without external lexical evidence, without structural features, without
   learning.
"""
from __future__ import annotations

import collections
import copy
import ctypes
import hashlib
import json
import pathlib
import statistics
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from contrastes import PAIRS  # noqa: E402
from dev import DEV  # noqa: E402
from dialogos import DIALOGS  # noqa: E402
from holdout import CRUZADO, HOLDOUT  # noqa: E402
from paginas import PAGES  # noqa: E402
from teste import TEST  # noqa: E402
from treino import TRAIN  # noqa: E402

from nucleo.lang import esquema as E  # noqa: E402
from nucleo.lang import ir  # noqa: E402
from nucleo.lang.acoes_ranker import Ranker  # noqa: E402
from nucleo.lang.mundo import Discourse, Page, Sandbox, applicability, dispatches, same_state  # noqa: E402
from nucleo.lang.values import fold  # noqa: E402

KS = (1, 3, 5, 10)
CRITERION_K = 10
CONTRASTE = [x for pair in PAIRS for x in pair]
EVAL_SETS = {"DEV": DEV, "TEST": TEST, "HOLDOUT": HOLDOUT, "CRUZADO": CRUZADO, "CONTRASTE": CONTRASTE}


# -- freezing ------------------------------------------------------------------------------------------------------
def canon_item(it) -> str:
    lang, page, text, gold, cats, ctx = it
    c = {k: ([a.canonical() for a in v] if k == "last" else v) for k, v in (ctx or {}).items()}
    return json.dumps([lang, page, text, [a.canonical() for a in gold], cats, c], ensure_ascii=False, sort_keys=True)


def digest(items) -> str:
    return hashlib.sha256("\n".join(canon_item(i) for i in items).encode("utf-8")).hexdigest()


def hashes() -> dict:
    dl = json.dumps([[d[0], d[1], [[t, [a.canonical() for a in g]] for t, g in d[2]]] for d in DIALOGS],
                    ensure_ascii=False)
    out = {k: digest(v) for k, v in (("TRAIN", TRAIN), *EVAL_SETS.items())}
    out["DIALOGOS"] = hashlib.sha256(dl.encode("utf-8")).hexdigest()
    return out


def freeze(refreeze: bool) -> dict:
    h = hashes()
    f = HERE / "congelado.json"
    if f.exists() and not refreeze:
        old = json.loads(f.read_text(encoding="utf-8"))
        changed = [k for k in h if old.get(k) != h[k]]
        if changed:
            raise SystemExit(f"datasets changed after freezing: {changed}")
    else:
        f.write_text(json.dumps(h, indent=1), encoding="utf-8")
    return h


# -- leakage -------------------------------------------------------------------------------------------------------
def _norm(s: str) -> str:
    return " ".join("".join(ch if ch.isalnum() or ch.isspace() else " " for ch in s.lower()).split())


def leakage(train, others: dict) -> dict:
    tr = [it[2] for it in train]
    norm = {_norm(s) for s in tr}
    folded = {fold(_norm(s)) for s in tr}
    reorder = {" ".join(sorted(fold(_norm(s)).split())) for s in tr}
    wsets = [set(fold(_norm(s)).split()) for s in tr]
    out = {}
    for name, items in others.items():
        rows, found = collections.Counter(), []
        for it in items:
            s = it[2]
            n = _norm(s)
            kind = None
            if s in tr:
                kind = "exact"
            elif n in norm:
                kind = "normalized"
            elif fold(n) in folded:
                kind = "accents"
            elif " ".join(sorted(fold(n).split())) in reorder:
                kind = "reorder"
            else:
                w = set(fold(n).split())
                if max((len(w & t) / max(1, len(w | t)) for t in wsets), default=0) >= 0.8:
                    kind = "near"
            if kind:
                rows[kind] += 1
                found.append((kind, s))
        out[name] = {"counts": dict(rows), "items": found}
    return out


# -- contexts ------------------------------------------------------------------------------------------------------
_APPL: dict = {}


def page_of(doc: dict, selection: list, sandbox) -> Page:
    pg = Page(doc, list(selection))
    k = hashlib.sha256(json.dumps(doc, sort_keys=True).encode("utf-8")).hexdigest()
    if k not in _APPL:
        applicability(sandbox.b, pg)
        _APPL[k] = (pg.hard_na, pg.soft_na)
    pg.hard_na, pg.soft_na = _APPL[k]
    return pg


def context(it, sandbox) -> tuple[Page, Discourse]:
    lang, page, text, gold, cats, ctx = it
    ctx = ctx or {}
    pg = page_of(PAGES[page], ctx.get("sel", []), sandbox)
    last = ir.Plan(tuple(ctx.get("last", []))) if ctx.get("last") else None
    ref = ctx.get("ref")
    mentioned = [a.target.node for a in (last.steps if last else ()) if a.target is not None and
                 a.target.kind == "node"] + ([ref] if ref else [])
    prop = next((a.arg("property").data for a in (last.steps if last else ()) if a.arg("property") is not None),
                None)
    return pg, Discourse(ref, last, mentioned, prop, pg.parent.get(ref) if ref else None, [])


def history(it, pg) -> list:
    last = (it[5] or {}).get("last") or []
    return (dispatches(ir.Plan(tuple(last)), pg, Discourse()) or []) if last else []


def check_gold(sandbox, items, name) -> list:
    bad = []
    for it in items:
        pg, disc = context(it, sandbox)
        steps = dispatches(ir.Plan(tuple(it[3])), pg, disc)
        if steps is None:
            bad.append((name, it[2], "not grounded"))
            continue
        _, _, ok = sandbox.run(pg.doc, pg.selection, history(it, pg) + steps)
        if not ok:
            bad.append((name, it[2], f"builder refused: {steps}"))
    return bad


# -- training ------------------------------------------------------------------------------------------------------
def train(ranker: Ranker, items, epochs: int, sandbox) -> dict:
    stats = collections.Counter()
    for ep in range(epochs):
        for it in items:
            pg, disc = context(it, sandbox)
            cx = ranker.context(it[2], it[0], pg, disc)
            ranked = ranker.rank(cx, ranker.generate(cx))
            golds = {a.canonical() for a in it[3]} or {"NONE"}
            if ep == epochs - 1:
                stats["gold_generated_last_epoch"] += all(g in {c.canonical() for c in ranked} for g in golds)
            wrong = [c for c in ranked if c.canonical() not in golds]
            for g in (it[3] or [None]):
                gf = ranker.gold(cx, g)
                ranker.learn_pairs(cx, g)
                if wrong and ranker.score(wrong[0].full) >= ranker.score(gf):
                    ranker.update(gf, wrong[0].full)
                    stats["updates"] += 1
    ranker.average()
    stats["train_items"] = len(items)
    return dict(stats)


# -- evaluation ----------------------------------------------------------------------------------------------------
def interpret(ranker: Ranker, text: str, lang: str, pg: Page, disc: Discourse):
    """The pipeline a user's sentence goes through: nothing about the gold is passed."""
    cx = ranker.context(text, lang, pg, disc)
    gen = ranker.generate(cx)
    order_gen = [c.canonical() for c in gen]
    return order_gen, ranker.rank(cx, gen)


def score_item(ranker, it, sandbox, pg=None, disc=None, gold=None) -> dict:
    lang, page, text, g, cats, ctx = it
    gold = gold if gold is not None else g
    if pg is None:
        pg, disc = context(it, sandbox)
    order_gen, ranked = interpret(ranker, text, lang, pg, disc)
    order = [c.canonical() for c in ranked]
    golds = [a.canonical() for a in gold] or ["NONE"]
    res = {"text": text, "lang": lang, "cats": cats.split(), "gold": golds, "n_cands": len(order_gen)}
    for k in KS:
        res[f"cand@{k}"] = all(x in order_gen[:max(k, len(golds))] for x in golds)
        res[f"rank@{k}"] = all(x in order[:max(k, len(golds))] for x in golds)
    res["cand@all"] = all(x in order_gen for x in golds)
    chosen = ranked[:len(golds)]
    res["pred_ir"] = [c.canonical() for c in chosen]
    res["ir"] = sorted(golds) == sorted(res["pred_ir"])
    plan = ir.Plan(tuple(c.action for c in chosen if c.action is not None))
    want = dispatches(ir.Plan(tuple(gold)), pg, disc)
    got = dispatches(plan, pg, disc)
    res["action"] = want is not None and got == want
    state_ok = False
    if want is not None and got is not None:
        pre = history(it, pg)
        d1, _, _ = sandbox.run(pg.doc, pg.selection, pre + want)
        d2, _, _ = sandbox.run(pg.doc, pg.selection, pre + got)
        state_ok = same_state(d1, d2, pg.doc)
    res["state"] = state_ok
    return res


METRICS = [f"cand@{k}" for k in KS] + ["cand@all"] + [f"rank@{k}" for k in KS] + ["ir", "action", "state"]


def table(rows, extra=None) -> dict:
    by = collections.defaultdict(collections.Counter)
    for r in rows:
        for c in r["cats"] + (extra(r) if extra else []) + [f"lang:{r['lang']}", "ALL"]:
            by[c]["n"] += 1
            for k in METRICS:
                by[c][k] += bool(r.get(k))
    return {c: {k: (v if k == "n" else round(100 * v / cnt["n"], 1)) for k, v in cnt.items()}
            for c, cnt in sorted(by.items())}


def train_vocab(ranker: Ranker) -> tuple[set, set]:
    lem, forms = set(), set()
    for it in TRAIN:
        for t in ranker.context(it[2], it[0], Page(PAGES[it[1]], []), Discourse()).toks:
            lem.add(t.keys[0])
            forms.add(fold(t.form.lower()))
    return lem, forms


def unseen(ranker, lem, forms):
    def cats(r):
        out = []
        toks = ranker.context(r["text"], r["lang"], Page(PAGES["L"], []), Discourse()).toks
        cont = [t for t in toks if t.upos in ("NOUN", "VERB", "ADJ", "ADV")]
        if any(t.keys[0] not in lem for t in cont):
            out.append("auto:lexical_unseen")
        if any(fold(t.form.lower()) not in forms and t.keys[0] in lem for t in cont):
            out.append("auto:inflection_unseen")
        return out
    return cats


# -- compositional holdout ------------------------------------------------------------------------------------------
def combos(it, sandbox) -> set:
    pg, disc = context(it, sandbox)
    out = set()
    for a in it[3]:
        node = a.target.node if a.target is not None and a.target.kind == "node" else None
        tt = pg.nodes[node]["type"] if node in pg.nodes else (a.target.type if a.target is not None else None)
        out.add(("op x entity", a.op, tt))
        p, v = a.arg("property"), a.arg("value")
        if p is not None:
            out.add(("property x entity", p.data, tt))
            if isinstance(v, ir.Value):
                out.add(("valueop x property", v.op, p.data))
                if v.op == "SET" and ir.quantity(v.data) is None:
                    out.add(("property x value", p.data, str(v.data)))
                if ir.quantity(v.data) is not None and ir.quantity(v.data)[1]:
                    out.add(("unit x property", ir.quantity(v.data)[1], p.data))
        if a.arg("index") is not None and isinstance(a.arg("parent"), ir.Ref):
            d = a.arg("parent").node
            k, i = len(pg.nodes[d]["children"]), int(a.arg("index").data)
            out.add(("position x destination", "start" if i == 0 else "end" if i == k else "middle",
                     pg.nodes[d]["type"]))
        ref = "ctx" if node and node == disc.referent else "sel" if node in pg.selection else "explicit"
        out.add(("reference x op", ref, a.op))
    for x, y in zip(it[3], it[3][1:]):
        out.add(("op pair", x.op, y.op))
    return out


def holdout_check(sandbox) -> dict:
    seen = set()
    for it in TRAIN:
        seen |= combos(it, sandbox)
    return {it[2]: sorted(c for c in combos(it, sandbox) if c not in seen) for it in HOLDOUT}


# -- dialogues -----------------------------------------------------------------------------------------------------
def run_dialogs(ranker, sandbox, end_to_end: bool) -> dict:
    rows = []
    for lang, page, turns in DIALOGS:
        doc, sel, disc, done = copy.deepcopy(PAGES[page]), [], Discourse(), []
        for text, gold in turns:
            pg = page_of(doc, sel, sandbox)
            g = [ir.Action(a.op, ir.Ref("node", disc.created[-1]) if a.target is not None and a.target.kind == "node"
                           and a.target.node == "$new" and disc.created else a.target, a.args) for a in gold]
            it = (lang, page, text, g, "dialogo", None)
            rows.append(score_item(ranker, it, sandbox, pg, disc, g))
            if end_to_end:
                ranked = interpret(ranker, text, lang, pg, disc)[1]
                plan = ir.Plan(tuple(c.action for c in ranked[:len(g) or 1] if c.action is not None))
            else:
                plan = ir.Plan(tuple(g))
            done += dispatches(plan, pg, disc) or []
            new_doc, new_sel, _ = sandbox.run(PAGES[page], [], done)
            disc = disc.after(plan, pg, Page(new_doc, new_sel))
            doc, sel = new_doc, new_sel
    return {"table": table(rows), "rows": rows}


# -- the run -------------------------------------------------------------------------------------------------------
def evaluate_sets(ranker, sandbox, lem, forms) -> dict:
    cats = unseen(ranker, lem, forms)
    out = {name: {"rows": [score_item(ranker, it, sandbox) for it in items]} for name, items in EVAL_SETS.items()}
    for name in out:
        out[name]["table"] = table(out[name]["rows"], cats)
    rows = out["CONTRASTE"]["rows"]
    out["CONTRASTE"]["pairs_both_right"] = round(
        100 * sum(rows[i]["ir"] and rows[i + 1]["ir"] for i in range(0, len(rows), 2)) / max(1, len(rows) // 2), 1)
    groups = collections.defaultdict(dict)
    for name, items in EVAL_SETS.items():
        for it, r in zip(items, out[name]["rows"]):
            key = (it[1], json.dumps({k: (v if k != "last" else [a.canonical() for a in v])
                                      for k, v in (it[5] or {}).items()}, sort_keys=True),
                   tuple(a.canonical() for a in it[3]))
            groups[key].setdefault(it[0], r)
    eq = [(g["pt"], g["en"]) for g in groups.values() if "pt" in g and "en" in g]
    out["IR_equivalence"] = {
        "pairs": len(eq),
        "same_ir": round(100 * sum(a["pred_ir"] == b["pred_ir"] for a, b in eq) / max(1, len(eq)), 1),
        "same_and_right": round(100 * sum(a["pred_ir"] == b["pred_ir"] and a["ir"] for a, b in eq) /
                                max(1, len(eq)), 1),
        "examples": [(a["text"], b["text"], a["pred_ir"], b["pred_ir"]) for a, b in eq][:60]}
    return out


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else 0


if __name__ == "__main__":
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    epochs = int(args[0]) if args else 6
    t0 = time.time()
    hs = freeze("--recongelar" in sys.argv)
    report: dict = {"hashes": hs, "epochs": epochs, "criterion": f"candidate recall@{CRITERION_K} >= 95% on TEST",
                    "counts": {"TRAIN": len(TRAIN), **{k: len(v) for k, v in EVAL_SETS.items()},
                               "DIALOGOS_turnos": sum(len(d[2]) for d in DIALOGS)}}
    report["leakage"] = leakage(TRAIN, EVAL_SETS)
    print(json.dumps({"hashes": hs, "leakage": {k: v["counts"] for k, v in report["leakage"].items()}}), flush=True)
    sb = Sandbox()
    try:
        report["gold_errors"] = sum((check_gold(sb, items, n) for n, items in (("TRAIN", TRAIN),
                                                                               *EVAL_SETS.items())), [])
        print(json.dumps({"gold_errors": report["gold_errors"]}, ensure_ascii=False), flush=True)
        report["holdout_new_combinations"] = holdout_check(sb)
        r = Ranker()
        report["train"] = train(r, TRAIN, epochs, sb)
        print(json.dumps({"train": report["train"], "secs": round(time.time() - t0)}), flush=True)
        if "--dev" in sys.argv:
            # development: DEV only, with every failure listed (TEST and the other sets are not touched)
            rows = [score_item(r, it, sb) for it in DEV]
            print("DEV", json.dumps(table(rows)["ALL"]), flush=True)
            for x in rows:
                if not x["ir"]:
                    print("  FAIL", x["text"], "| gold", x["gold"], "| got", x["pred_ir"], "| cand@all",
                          x["cand@all"], flush=True)
            raise SystemExit(0)
        lem, forms = train_vocab(r)
        r.stats = {"gen_secs": [], "rank_secs": [], "n": []}
        report["sets"] = evaluate_sets(r, sb, lem, forms)
        n = r.stats["n"]
        report["cost"] = {"operations_in_schema": len(E.schemas()),
                          "candidates_mean": round(statistics.mean(n), 1), "candidates_p50": pct(n, .5),
                          "candidates_p95": pct(n, .95), "candidates_max": max(n),
                          "gen_ms_mean": round(1000 * statistics.mean(r.stats["gen_secs"]), 1),
                          "gen_ms_p95": round(1000 * pct(r.stats["gen_secs"], .95), 1),
                          "rank_ms_mean": round(1000 * statistics.mean(r.stats["rank_secs"]), 1),
                          "rank_ms_p95": round(1000 * pct(r.stats["rank_secs"], .95), 1)}
        report["dialogs_gold_history"] = run_dialogs(r, sb, False)
        report["dialogs_end_to_end"] = run_dialogs(r, sb, True)
        for k in EVAL_SETS:
            print(k, json.dumps(report["sets"][k]["table"].get("ALL")), flush=True)
        print("IR eq", {k: v for k, v in report["sets"]["IR_equivalence"].items() if k != "examples"},
              "contrast pairs", report["sets"]["CONTRASTE"]["pairs_both_right"], flush=True)
        print("dialogs", report["dialogs_gold_history"]["table"]["ALL"], report["dialogs_end_to_end"]["table"]["ALL"],
              flush=True)
        print("cost", report["cost"], flush=True)
        if "--sem-ablacao" not in sys.argv:
            abl = {}
            for name, off, learn in (("sem contexto", {"ctx"}, True), ("sem evidencia externa", {"ev"}, True),
                                     ("sem tracos estruturais", {"struct"}, True), ("sem aprendizado", set(), False)):
                ra = Ranker(frozenset(off))
                if learn:
                    train(ra, TRAIN, epochs, sb)
                abl[name] = table([score_item(ra, it, sb) for it in TEST + HOLDOUT])["ALL"]
                print("ablation", name, abl[name], flush=True)
            report["ablations"] = abl
    finally:
        sb.close()
    report["secs"] = round(time.time() - t0)
    (ROOT / "data" / "cache" / "a1_relatorio.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("secs", report["secs"])
