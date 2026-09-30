"""M6: reconstruct deleted function bodies of real Python code from input/output examples.

Tasks: small pure functions of the local standard library and installed packages (``nucleo/synth/tasks.py``); the
oracle is the original function, run on generated inputs. Each task gets 6 training examples; success means the
synthesized expression agrees with the original on 30 held-out inputs it never saw.

Compared: uniform cost (program size) vs. the counted prior (PCFG from the corpus, the task's own file left out).
Usage: python experiments/m6_synthesis.py [time-limit-seconds]
"""
from __future__ import annotations

import builtins
import collections
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from nucleo.synth.enumerate import synthesize  # noqa: E402
from nucleo.synth.prior import CACHE, Prior, count_corpus, load_counts  # noqa: E402
from nucleo.synth.tasks import SAFE_BUILTINS, build_tasks, corpus_files  # noqa: E402

DATA = pathlib.Path(__file__).resolve().parents[1] / "data" / "cache"


def holds(params, source, examples) -> bool:
    env = {k: getattr(builtins, k) for k in SAFE_BUILTINS}
    try:
        fn = eval(f"lambda {', '.join(params)}: ({source})", {"__builtins__": env})  # noqa: S307 - our own output
    except SyntaxError:
        return False
    for args, out in examples:
        try:
            got = fn(*[list(a) if isinstance(a, list) else a for a in args])
        except Exception:  # noqa: BLE001
            return False
        if repr(got) != repr(out):
            return False
    return True


def main(limit_s: float = 5.0):
    counts = load_counts() if CACHE.exists() else count_corpus(corpus_files())
    tasks = build_tasks()
    c = collections.Counter()
    rows = []
    t0 = time.time()
    for t in tasks:
        row = {"nome": t.name, "arquivo": t.source, "tipos": t.kinds, "tamanho": t.size, "original": t.body}
        for mode in ("uniforme", "prior"):
            prior = Prior(counts, exclude=t.source) if mode == "prior" else None
            consts = None
            if prior is not None:
                consts = list(dict.fromkeys(prior.top_constants[:25] + [0, 1, "", " "]))
            r = synthesize(t.params, t.train, prior=prior, constants=consts, time_limit=limit_s)
            ok = r.source is not None and holds(t.params, r.source, t.test)
            c[f"{mode}: resolvidas"] += ok
            c[f"{mode}: acha nos exemplos mas erra no teste"] += r.source is not None and not ok
            row[mode] = {"programa": r.source, "certo": ok, "explorados": r.explored, "segundos": round(r.seconds, 2)}
        c["tarefas"] += 1
        rows.append(row)
    n = c["tarefas"]
    print(f"{n} tarefas em {time.time() - t0:.0f}s (limite {limit_s}s por tarefa e modo)")
    for mode in ("uniforme", "prior"):
        print(f"  {mode:8s}: {c[f'{mode}: resolvidas']}/{n} = {c[f'{mode}: resolvidas'] / n:.1%} "
              f"(generaliza mal: {c[f'{mode}: acha nos exemplos mas erra no teste']})")
    big = [r for r in rows if r["tamanho"] >= 6]
    for mode in ("uniforme", "prior"):
        k = sum(r[mode]["certo"] for r in big)
        print(f"  {mode:8s} só tamanho >= 6: {k}/{len(big)}")
    (DATA / "m6_synthesis.json").write_text(json.dumps(rows, ensure_ascii=False, indent=0, default=str),
                                            encoding="utf-8")


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 5.0)
