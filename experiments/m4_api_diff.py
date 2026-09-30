"""M4 gate (API diffs): rule-deduced API changes between real package versions, judged by the TypeScript compiler.

Pairs: every typed npm package installed in two different versions across the local projects.
For each name of the old version, a probe importing it (in its space) is compiled against the new version; for each
name of the new version, against the old one. Our claims `indisponivel` / `novo` must match exactly.
"""
from __future__ import annotations

import collections
import json
import os
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from nucleo.apis.surface import diff  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bridge" / "code" / "api_surface.mjs"
ENV = {**os.environ, "NUCLEO_TS": "C:/Codex-Shared/deepseek/builder-6"}
PROJECTS = ["C:/Codex-Shared/deepseek/builder-6", "C:/Codex-Shared/Road", "C:/Codex-Shared/zerto-studio"]


def installed(root):
    out = {}
    nm = pathlib.Path(root) / "node_modules"
    for p in list(nm.glob("*")) + list(nm.glob("@*/*")):
        try:
            j = json.loads((p / "package.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        typed = bool(j.get("types") or j.get("typings") or (p / "index.d.ts").exists() or j.get("exports"))
        out[j.get("name")] = (j.get("version"), typed, str(p))
    return out


def node(*args):
    r = subprocess.run(["node", str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8", env=ENV)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-500:])
    return json.loads(r.stdout)


def probe(pkg_dir, names):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(names, f)
    try:
        return node("probe", pkg_dir, f.name)["results"]
    finally:
        os.unlink(f.name)


def pairs():
    inst = [installed(p) for p in PROJECTS]
    seen = {}
    for proj in inst:
        for name, (ver, typed, path) in proj.items():
            if typed:
                seen.setdefault(name, {})[ver] = path
    for name, vers in sorted(seen.items()):
        if len(vers) > 1:
            vs = sorted(vers, key=lambda v: [int(x) if x.isdigit() else x for x in v.replace("-", ".").split(".")])
            yield name, vs[0], vers[vs[0]], vs[-1], vers[vs[-1]]


if __name__ == "__main__":
    c = collections.Counter()
    wrong = []
    for name, v_old, p_old, v_new, p_new in pairs():
        try:
            old, new = node("surface", p_old), node("surface", p_new)
        except RuntimeError as e:
            c["pacote não analisável"] += 1
            print("  pulado", name, str(e)[:120])
            continue
        if not (old["resolved"] and new["resolved"]) or len(old["exports"]) > 1500 or len(new["exports"]) > 1500:
            c["pacote pulado (sem módulo de tipos ou grande demais)"] += 1
            continue
        d = diff(old["exports"], new["exports"])
        testa = lambda e: "valor" if e in ("valor", "ambos") else "tipo"  # noqa: E731
        o_names = [(n, testa(e)) for n, e, _ in old["exports"] if n.isidentifier()]
        n_names = [(n, testa(e)) for n, e, _ in new["exports"] if n.isidentifier()]
        in_new = probe(p_new, o_names) if o_names else {}
        in_old = probe(p_old, n_names) if n_names else {}
        for n, x in o_names:
            claim = (n, x) in d["indisponivel"]
            truth = not in_new[n]
            c["afirmações (removido/mantido)"] += 1
            c["certas"] += claim == truth
            c["removidos reais"] += truth
            if claim != truth:
                wrong.append((name, v_old, v_new, n, x, "removido" if claim else "mantido", "compilador discorda"))
        for n, x in n_names:
            claim = (n, x) in d["novo"]
            truth = not in_old[n]
            c["afirmações (novo/antigo)"] += 1
            c["certas"] += claim == truth
            c["novos reais"] += truth
            if claim != truth:
                wrong.append((name, v_old, v_new, n, x, "novo" if claim else "já existia", "compilador discorda"))
        c["pacotes"] += 1
        c["assinaturas alteradas (afirmadas)"] += len(d["assinatura_mudou"])
        print(f"  {name} {v_old} -> {v_new}: -{len(d['indisponivel'])} +{len(d['novo'])} ~{len(d['assinatura_mudou'])}")
    total = c["afirmações (removido/mantido)"] + c["afirmações (novo/antigo)"]
    print(dict(c))
    print(f"acordo com o compilador: {c['certas']}/{total} = {c['certas'] / max(total, 1):.4%}")
    for w in wrong[:20]:
        print("  ", w)
