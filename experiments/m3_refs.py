"""M3: "find all references" by rules, against TypeScript's language service (findReferences).

Compared on the positions both sides can name (identifier uses); the oracle's references that are not uses in our
facts (import specifiers, which are declarations for us) are counted separately.
Usage: python experiments/m3_refs.py --project=... --tsconfig=... [--every=20]
"""
from __future__ import annotations

import collections
import json
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from m3_resolve import extract  # noqa: E402
from nucleo.builder.client import DEFAULT_BUILDER  # noqa: E402
from nucleo.code.project import CodeBase  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def arg(name, default):
    return next((a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{name}=")), default)


if __name__ == "__main__":
    project, tsconfig, every = arg("project", DEFAULT_BUILDER), arg("tsconfig", "tsconfig.app.json"), arg("every", "20")
    t = time.time()
    files = extract(project, tsconfig)
    cb = CodeBase(files)
    _ = cb.model
    t1 = time.time()
    out = subprocess.run(["node", str(ROOT / "bridge" / "code" / "ts_refs.mjs"), project, tsconfig, every],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    samples = [json.loads(l) for l in out.splitlines() if l.strip()]
    uses = {(f["file"], u[0]) for f in files for u in f["uses"]}
    c = collections.Counter()
    bad = []
    for s in samples:
        truth = {(f, p) for f, p, d in s["refs"] if not d}
        comparable = {r for r in truth if r in uses}
        c["fora do conjunto de usos"] += len(truth - comparable)
        mine = cb.references(s["file"], s["pos"])
        c["referências (oráculo)"] += len(comparable)
        c["referências (nossas)"] += len(mine)
        c["certas"] += len(mine & comparable)
        if mine != comparable:
            c["declarações com diferença"] += 1
            bad.append((s["file"], s["name"], sorted(mine - comparable)[:3], sorted(comparable - mine)[:3]))
    c["declarações"] = len(samples)
    print(f"base de código: {time.time() - t:.1f}s (raciocínio {t1 - t:.1f}s)")
    print(dict(c))
    print(f"precisão {c['certas'] / max(c['referências (nossas)'], 1):.4%}  "
          f"cobertura {c['certas'] / max(c['referências (oráculo)'], 1):.4%}")
    for b in bad[:10]:
        print("  ", b)
    unused = cb.unused_exports()
    print(f"exportações sem uso fora de si mesmas: {len(unused)}")
