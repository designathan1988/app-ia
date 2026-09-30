"""M3: per-file incremental maintenance of the code knowledge, on real code evolution.

Start from builder-5's code base and replace, one file at a time, the files that changed in builder-6 (real edits
made to the project). After the updates, the incrementally maintained model must equal a full rebuild.
Usage: python experiments/m3_incremental.py [n-files]
"""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from m3_resolve import extract  # noqa: E402
from nucleo.code.project import CodeBase  # noqa: E402
from nucleo.logic.engine import evaluate  # noqa: E402
from nucleo.kb.syntax import parse_program  # noqa: E402

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    old = {f["file"]: f for f in extract("C:/Codex-Shared/deepseek/builder-5", "tsconfig.app.json")}
    new = {f["file"]: f for f in extract("C:/Codex-Shared/deepseek/builder-6", "tsconfig.app.json")}
    changed = sorted(k for k in new if k in old and (new[k]["decls"], new[k]["uses"]) != (old[k]["decls"], old[k]["uses"]))
    added = sorted(k for k in new if k not in old)
    print(f"arquivos alterados entre as versões: {len(changed)}; novos: {len(added)}")
    t = time.time()
    cb = CodeBase(list(old.values()))
    _ = cb.model
    print(f"modelo inicial: {time.time() - t:.1f}s")
    steps = (changed[:n] + added[: max(1, n // 4)])
    for name in steps:
        t = time.time()
        cb.update_file(new[name])
        print(f"  atualização incremental de {name}: {time.time() - t:.1f}s "
              f"(componentes reaproveitados {cb.model.reused_components}, mantidos fato a fato "
              f"{cb.model.maintained_components}, de {len(cb.model.analysis.components)})")
    t = time.time()
    full = evaluate(parse_program(cb._text))
    print(f"reconstrução completa: {time.time() - t:.1f}s")
    same = set(full.entries) == set(cb.model.entries) and all(full.entries[a].cost == cb.model.entries[a].cost for a in full.entries)
    print("incremental == recomputação:", same)
    sys.exit(0 if same else 1)
