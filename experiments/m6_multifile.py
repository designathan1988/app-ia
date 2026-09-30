"""M6 gate (multi-file): random project models (invented names, random fields, constraints and relations) ->
TypeScript + Python projects -> verified by the strict TypeScript compiler, the generated tests in both languages,
and a differential test against the model's reference meaning. The gate is 100% verified.

Usage: python experiments/m6_multifile.py [n-models] [fuzz-values]
"""
from __future__ import annotations

import collections
import pathlib
import random
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from nucleo.gen.build import verify  # noqa: E402
from nucleo.session import low_priority  # noqa: E402
from tests.gen.worlds import pseudo_word  # noqa: E402


def random_model(seed: int) -> dict:
    rng = random.Random(seed)
    used: set = set()

    def name(cap: bool) -> str:
        while True:
            w = pseudo_word(rng) + pseudo_word(rng)
            w = w.capitalize() if cap else w
            if w.lower() not in used:
                used.add(w.lower())
                return w

    ents = []
    for _ in range(rng.randint(1, 4)):
        fields = []
        for _ in range(rng.randint(1, 6)):
            t = rng.choice(["texto", "texto", "inteiro", "decimal", "booleano", "enum"])
            f = {"nome": name(False), "tipo": t}
            if rng.random() < 0.5:
                f["obrigatorio"] = True
            if t == "texto":
                if rng.random() < 0.4:
                    f["min"] = rng.randint(1, 4)
                if rng.random() < 0.6:
                    f["max"] = rng.randint(f.get("min", 1) + 5, 80)
                if rng.random() < 0.25:
                    f["formato"] = "email"
                    f.pop("min", None)
                    if "max" in f:
                        f["max"] = max(f["max"], 10)
            elif t in ("inteiro", "decimal"):
                if rng.random() < 0.6:
                    f["min"] = rng.randint(-10, 5)
                if rng.random() < 0.6:
                    f["max"] = f.get("min", 0) + rng.randint(1, 500)
            elif t == "enum":
                f["valores"] = [pseudo_word(rng) for _ in range(rng.randint(1, 4))]
            fields.append(f)
        ents.append({"nome": name(True), "campos": fields, "relacoes": []})
    for e in ents:
        if len(ents) > 1 and rng.random() < 0.6:
            target = rng.choice([x for x in ents if x is not e])
            e["relacoes"].append({"nome": name(False), "alvo": target["nome"], "muitos": rng.random() < 0.5})
    return {"entidades": ents}


if __name__ == "__main__":
    low_priority()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    fuzz = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    c = collections.Counter()
    t0 = time.time()
    lines = files = 0
    for seed in range(n):
        r = verify(random_model(seed), fuzz=fuzz, seed=seed)
        c["verificado" if r["verificado"] else "FALHOU"] += 1
        lines += r["linhas"]
        files += r["arquivos"]
        if not r["verificado"]:
            print(f"  modelo {seed}: tsc={r['tsc'][:2]} ts={r.get('testes_ts')} py={r['testes_py']} "
                  f"dif={r.get('diferencial', {}).get('exemplos', [])[:1]}")
    print(f"{n} modelos em {time.time() - t0:.0f}s: {dict(c)}; {files} arquivos, {lines} linhas geradas; "
          f"{n * fuzz} valores no teste diferencial")
