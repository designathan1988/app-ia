"""M3 gate (TypeScript): our rule-based name resolution against the TypeScript checker, on builder-6's sources.

Usage: python experiments/m3_resolve.py [limit-files]
"""
from __future__ import annotations

import collections
import json
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from nucleo.builder.client import DEFAULT_BUILDER  # noqa: E402
from nucleo.code.resolve import resolve_file  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def extract(project=DEFAULT_BUILDER, tsconfig="tsconfig.app.json", filt=""):
    out = subprocess.run(["node", str(ROOT / "bridge" / "code" / "ts_facts.mjs"), project, tsconfig, filt],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def compare(files):
    c = collections.Counter()
    wrong = []
    for f in files:
        ours, _ = resolve_file(f)
        for pos, name, _s, space, *_ in f["uses"]:
            truth = f["oracle"][str(pos)]
            mine = ours.get(pos)
            if isinstance(truth, str) and truth != "externo":
                truth = ["outro-arquivo"]
            if mine == "externo":
                c["nosso externo"] += 1
                if truth == "externo":
                    c["externo certo"] += 1
                else:
                    c["externo errado"] += 1
            else:
                c["nosso resolvido"] += 1
                if isinstance(truth, list) and mine in truth:
                    c["resolvido certo"] += 1
                else:
                    c["resolvido ERRADO"] += 1
                    wrong.append((f["file"], pos, name, space, mine, truth))
            if isinstance(truth, list) and truth != ["outro-arquivo"]:
                c["oráculo local"] += 1
    return c, wrong


if __name__ == "__main__":
    t = time.time()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    project = next((a[10:] for a in sys.argv if a.startswith("--project=")), DEFAULT_BUILDER)
    tsconfig = next((a[11:] for a in sys.argv if a.startswith("--tsconfig=")), "tsconfig.app.json")
    files = extract(project, tsconfig)
    files = files[: int(args[0])] if args else files
    t1 = time.time()
    c, wrong = compare(files)
    print(f"{len(files)} arquivos; extração {t1 - t:.1f}s; raciocínio {time.time() - t1:.1f}s")
    print(dict(c))
    p = c["resolvido certo"] / max(c["nosso resolvido"], 1)
    r = c["resolvido certo"] / max(c["oráculo local"], 1)
    print(f"precisão {p:.4%}  cobertura {r:.4%}  VERDADEIRO errado {c['resolvido ERRADO'] / max(c['nosso resolvido'], 1):.4%}")
    for w in wrong[:25]:
        print("  ", w)
    (ROOT / "data" / "cache" / "m3_wrong.json").write_text(json.dumps(wrong), encoding="utf-8")


def compare_imports(files):
    from nucleo.code.modules import resolve_imports

    ours, _ = resolve_imports(files)
    c = collections.Counter()
    wrong = []
    for f in files:
        for pos, local, spec, imported in f["imports"]:
            truth = f["aliasOracle"][str(pos)]
            mine = ours.get((f["file"], pos), set())
            if truth == "externo":
                c["oráculo externo"] += 1
                c["externo certo" if not mine else "resolvido ERRADO"] += 1
                if mine:
                    wrong.append((f["file"], local, spec, sorted(mine), truth))
                continue
            c["oráculo interno"] += 1
            if not mine:
                c["não resolvido"] += 1
                wrong.append((f["file"], local, spec, [], truth))
            elif mine <= set(truth):
                c["resolvido certo"] += 1
            else:
                c["resolvido ERRADO"] += 1
                wrong.append((f["file"], local, spec, sorted(mine), truth))
    return c, wrong


if __name__ == "__main__" and "--imports" in sys.argv:
    c, wrong = compare_imports(files)
    print("importações:", dict(c))
    for w in wrong[:15]:
        print("  ", w)
