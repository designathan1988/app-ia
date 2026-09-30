"""Generate a project from a model in TypeScript and Python, and verify it without taking anyone's word for it.

Verification, in order:
1. the TypeScript compiler, strict, finds no problem;
2. the generated TypeScript tests pass (node) and the generated Python tests pass (pytest);
3. **differential test**: many random values (valid and broken on purpose, with unicode, floats, booleans, nulls,
   wrong types) are judged by the TypeScript validator, the Python validator and the model's reference meaning
   (``model.reference_errors``); all three must give the same error codes for every value.
"""

from __future__ import annotations

import json
import os
import pathlib
import random
import subprocess
import sys
import tempfile

from ..builder.client import DEFAULT_BUILDER
from . import python as pygen
from . import typescript as tsgen
from .model import check_model, reference_errors

ROOT = pathlib.Path(__file__).resolve().parents[2]
TS_PROJECT = ROOT / "bridge" / "code" / "ts_project.mjs"
ENV = {**os.environ, "NUCLEO_TS": os.environ.get("NUCLEO_TS", DEFAULT_BUILDER)}


def _valid_value(f: dict):
    t = f["tipo"]
    if t == "texto":
        if f.get("formato") == "email":
            base = "a@b.co"
            n = max(f.get("min", 0), len(base))
            return ("x" * (n - len(base))) + base if n <= f.get("max", 10**9) else None
        n = max(f.get("min", 0), 1)
        return "t" * n if n <= f.get("max", 10**9) else None
    if t in ("inteiro", "decimal"):
        lo, hi = f.get("min", 0), f.get("max", 10**6)
        v = lo if lo <= hi else None
        return (float(v) + 0.5 if t == "decimal" and v is not None and v + 0.5 <= hi else v)
    if t == "booleano":
        return True
    return f["valores"][0]


def examples(model: dict) -> dict:
    """A valid object per entity and one object per constraint broken on purpose; expected codes by the reference."""
    out = {}
    for e in model["entidades"]:
        valid = {}
        for f in e.get("campos", []):
            valid[f["nome"]] = _valid_value(f)
        violations = []
        for f in e.get("campos", []):
            n, t = f["nome"], f["tipo"]
            breaks = []
            if f.get("obrigatorio"):
                breaks.append(None)
            breaks.append(123 if t in ("texto", "enum") else "texto")
            if t == "texto" and "max" in f:
                breaks.append("m" * (f["max"] + 1))
            if t == "texto" and f.get("min", 0) > 1:
                breaks.append("m" * (f["min"] - 1))
            if t in ("inteiro", "decimal") and "min" in f:
                breaks.append(f["min"] - 1)
            if t in ("inteiro", "decimal") and "max" in f:
                breaks.append(f["max"] + 1)
            if t == "inteiro":
                breaks.append(1.5)
            if t == "texto" and f.get("formato") == "email":
                breaks.append("sem-arroba")
            if t == "enum":
                breaks.append("zzz-nao-existe")
            for b in breaks:
                obj = dict(valid)
                if b is None:
                    obj.pop(n)
                else:
                    obj[n] = b
                codes = sorted(reference_errors(e, obj))
                if codes:
                    violations.append([obj, codes])
        assert not reference_errors(e, valid), (e["nome"], reference_errors(e, valid))
        out[e["nome"]] = {"valido": valid, "violacoes": violations}
    return out


def fuzz_values(model: dict, n: int, rng: random.Random) -> list[dict]:
    pool = [None, "", "a", "ação", "😀" * 3, "x" * 40, "e@x.io", "a b@c.d", "@x.y", 0, -1, 7, 2.5, 1e9, True, False,
            [], ["a"], {"k": 1}, "basico", "pro"]
    out = []
    for _ in range(n):
        e = rng.choice(model["entidades"])
        obj = {}
        for f in e.get("campos", []) + e.get("relacoes", []):
            r = rng.random()
            if r < 0.15:
                continue
            if r < 0.3 and f.get("tipo") == "texto" and ("min" in f or "max" in f):
                # right at the length limits, in characters that JavaScript counts as two units each
                k = rng.choice([x for x in (f.get("min"), f.get("max")) if x is not None])
                obj[f["nome"]] = "😀" * (k + rng.choice([-1, 0, 1]))
                continue
            if r < 0.55 and "tipo" in f:
                v = _valid_value(f)
                if f["tipo"] == "enum":
                    v = rng.choice(f["valores"])
                elif f["tipo"] in ("inteiro", "decimal") and v is not None:
                    v = v + rng.choice([0, 1, -1, 2, 100])
                obj[f["nome"]] = v
            else:
                obj[f["nome"]] = rng.choice(pool)
        if rng.random() < 0.03:
            obj = rng.choice([[], "x", 3])
        out.append({"entity": e["nome"], "value": obj})
    return out


def verify(model: dict, workdir: str | None = None, fuzz: int = 300, seed: int = 0) -> dict:
    check_model(model)
    ex = examples(model)
    base = pathlib.Path(workdir or tempfile.mkdtemp(prefix="nucleo-gen-"))
    ts_dir, py_dir = base / "ts", base / "py"
    files = {**{f"ts/{k}": v for k, v in tsgen.project(model, ex).items()},
             **{f"py/{k}": v for k, v in pygen.project(model, ex).items()}}
    for rel, text in files.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    report = {"arquivos": len(files), "linhas": sum(t.count("\n") for t in files.values()), "dir": str(base)}
    r = subprocess.run(["node", str(TS_PROJECT), "check", str(ts_dir)], capture_output=True, text=True,
                       encoding="utf-8", env=ENV)
    diags = json.loads(r.stdout)["diagnostics"] if r.returncode == 0 and r.stdout else [r.stderr[-500:]]
    report["tsc"] = diags
    if not diags:
        t = subprocess.run(["node", str(ts_dir / "out" / "test" / "run.js")], capture_output=True, text=True,
                           encoding="utf-8")
        report["testes_ts"] = t.stdout.strip().splitlines()[-1] if t.stdout.strip() else t.stderr[-300:]
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(py_dir / "gerado")],
                       capture_output=True, text=True, encoding="utf-8", cwd=str(py_dir))
    report["testes_py"] = (p.stdout.strip().splitlines() or ["?"])[-1]
    report["py_ok"] = p.returncode == 0
    if not diags:
        values = fuzz_values(model, fuzz, random.Random(seed))
        vf = base / "valores.jsonl"
        vf.write_text("\n".join(json.dumps(v, ensure_ascii=False) for v in values), encoding="utf-8")
        tsr = subprocess.run(["node", str(TS_PROJECT), "validate", str(ts_dir), str(vf)], capture_output=True,
                             text=True, encoding="utf-8", env=ENV)
        ts_out = [json.loads(line) for line in tsr.stdout.splitlines() if line.strip()]
        sys.path.insert(0, str(py_dir))
        try:
            import importlib

            for m in [m for m in list(sys.modules) if m == "gerado" or m.startswith("gerado.")]:
                del sys.modules[m]
            validators = importlib.import_module("gerado.validate").VALIDATORS
        finally:
            sys.path.remove(str(py_dir))
        ents = {e["nome"]: e for e in model["entidades"]}
        disagreements = []
        for v, t in zip(values, ts_out):
            val = json.loads(json.dumps(v["value"]))  # what both sides saw: the JSON value
            ref = sorted(reference_errors(ents[v["entity"]], val))
            py = sorted(validators[v["entity"]](val))
            if not (ref == py == t["errors"]):
                disagreements.append({"valor": v, "referencia": ref, "python": py, "typescript": t["errors"]})
        report["diferencial"] = {"valores": len(values), "divergencias": len(disagreements),
                                 "exemplos": disagreements[:3]}
    report["verificado"] = (not diags and report.get("testes_ts") == "OK" and report["py_ok"]
                            and report["diferencial"]["divergencias"] == 0)
    return report
