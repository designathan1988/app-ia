"""M3 gate (Python): rule-based name resolution against CPython's own symbol tables.

Corpus: this repository's code, plus the standard library's top-level modules (never used to write the rules).
Usage: python experiments/m3_python.py [--stdlib-limit=N]
"""
from __future__ import annotations

import collections
import pathlib
import sys
import sysconfig
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from nucleo.code.python_facts import facts_of  # noqa: E402
from nucleo.code.resolve import resolve_file  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def corpus(stdlib_limit: int | None, extra: str | None = None):
    if extra:
        return [("extra", p) for p in sorted(pathlib.Path(extra).rglob("*.py"))]
    own = sorted(p for p in ROOT.rglob("*.py") if "data" not in p.parts)
    lib = sorted(pathlib.Path(sysconfig.get_paths()["stdlib"]).glob("*.py"))[:stdlib_limit]
    return [("nucleo", p) for p in own] + [("stdlib", p) for p in lib]


def run(stdlib_limit=None, show=15, extra=None):
    c = collections.Counter()
    wrong = []
    for group, path in corpus(stdlib_limit, extra):
        src = path.read_text(encoding="utf-8", errors="replace")
        if len(src) > 400_000:
            c["arquivo grande pulado"] += 1
            continue
        try:
            f = facts_of(src, str(path))
        except SyntaxError:
            c["não analisável"] += 1
            continue
        ours, _ = resolve_file(f)
        c[f"arquivos {group}"] += 1
        for pos, name, _s, _sp, *_ in f["uses"]:
            truth = f["oracle"].get(str(pos))
            if truth is None:
                c["sem oráculo"] += 1
                continue
            mine = ours.get(pos)
            if mine == "externo":
                c["nosso externo"] += 1
                c["externo certo" if truth == "externo" else "externo errado"] += 1
                if truth != "externo":
                    wrong.append((group, path.name, pos, name, mine, truth))
            else:
                c["nosso resolvido"] += 1
                ok = isinstance(truth, list) and mine in truth
                c["resolvido certo" if ok else "resolvido ERRADO"] += 1
                if not ok:
                    wrong.append((group, path.name, pos, name, mine, truth))
            if isinstance(truth, list):
                c["oráculo local"] += 1
    p = c["resolvido certo"] / max(c["nosso resolvido"], 1)
    r = c["resolvido certo"] / max(c["oráculo local"], 1)
    print(dict(c))
    print(f"precisão {p:.4%}  cobertura {r:.4%}  VERDADEIRO errado {c['resolvido ERRADO'] / max(c['nosso resolvido'], 1):.4%}")
    for w in wrong[:show]:
        print("  ", w)
    return c, wrong


if __name__ == "__main__":
    lim = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--stdlib-limit=")), None)
    t = time.time()
    run(lim, extra=next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--dir=")), None))
    print(f"{time.time() - t:.0f}s")
