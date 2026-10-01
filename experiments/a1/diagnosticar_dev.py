"""Inspect saved DEV candidates and learned contributions, never held-out sets.

Run avaliar.py --dev first, then diagnosticar_dev.py [zero-based DEV indices].
The saved model is a trusted local artifact written by the evaluator.
"""

from runtime import lower_priority

lower_priority()

import json
import pickle
import sys

from avaliar import DEV, ROOT, Sandbox, context


def contributions(ranker, features):
    return sorted([(round(ranker.w.get(k, 0) * v, 3), str(k), v)
                   for k, v in features.items() if ranker.w.get(k, 0) * v], reverse=True)


if __name__ == "__main__":
    cache = ROOT / "data" / "cache"
    ranker = pickle.loads((cache / "a1_dev_model.pkl").read_bytes())
    saved = json.loads((cache / "a1_dev_rows.json").read_text(encoding="utf-8"))
    indices = [int(x) for x in sys.argv[1:]] or [i for i, row in enumerate(saved["rows"]) if not row["ir"]]
    sandbox = Sandbox()
    try:
        for i in indices:
            item = DEV[i]
            page, discourse = context(item, sandbox)
            cx = ranker.context(item[2], item[0], page, discourse)
            generated = ranker.generate(cx)
            ranked = ranker.rank(cx, generated)
            gold = {a.canonical() for a in item[3]}
            inspected = ranked[:3] + [c for c in ranked[3:] if c.canonical() in gold]
            print(json.dumps({"index": i, "text": item[2], "tokens": [vars(t) for t in cx.toks],
                              "targets": [(n, round(ranker.score(f), 3)) for n, f in ranker._targets(cx)],
                              "ops": [(n, round(ranker.score(f), 3)) for n, f in ranker._ops(cx)],
                              "candidates": [{"ir": c.ir(), "kind": c.kind,
                                              "score": round(ranker.score(c.full), 3),
                                              "contributions": contributions(ranker, c.full)} for c in inspected]},
                             ensure_ascii=False), flush=True)
    finally:
        sandbox.close()
