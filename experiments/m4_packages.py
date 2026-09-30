"""M4 gate (packages): the system never suggests a package that does not exist, and never fetches what robots.txt
forbids.

Names: real packages (taken from local installs, but looked up in the registries, not locally) and invented ones
(pseudo-words, and misspellings of popular packages, the typical hallucination). Each name goes the whole way:
registry lookup -> claim -> fresh retrieval (reproduction) -> verification by rules -> approval (played here by the
experiment, standing in for the user) -> can_suggest. Requests are few and spaced (>= 1 s per host).
"""
from __future__ import annotations

import collections
import pathlib
import random
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from nucleo.store.db import Store  # noqa: E402
from nucleo.web.claims import Claims  # noqa: E402
from nucleo.web.fetcher import Fetcher  # noqa: E402
from nucleo.web.registries import npm, pypi  # noqa: E402
from nucleo.web.robots import Rules  # noqa: E402
from tests.gen.worlds import pseudo_word  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]

REAL = {"npm": ["magic-string", "css-tree", "vitest", "keyv", "nanoid", "postcss"],
        "pypi": ["clingo", "hypothesis", "pluggy", "sortedcontainers"]}
MISSPELLED = {"npm": ["reactt-domm", "lodahs-utilz", "expresss-routr"], "pypi": ["reqeusts-toolz", "numpyy-extrass"]}


def main():
    rng = random.Random(7)
    names = []
    for eco in ("npm", "pypi"):
        names += [(eco, n, "real") for n in REAL[eco]]
        names += [(eco, n, "grafia errada") for n in MISSPELLED[eco]]
        names += [(eco, "".join(pseudo_word(rng) for _ in range(2)) + "zq", "inventado") for _ in range(4)]
    tmp = tempfile.mkdtemp()
    f = Fetcher(pathlib.Path(tmp) / "web", min_delay=1.0)
    claims = Claims(Store(str(pathlib.Path(tmp) / "kb.db")))
    c = collections.Counter()
    exists_by_registry = {}
    for eco, name, kind in names:
        lookup = npm if eco == "npm" else pypi
        info = lookup(f, name)
        exists_by_registry[(eco, name)] = info.exists
        c[f"{kind}: existe={info.exists}"] += 1
        if info.exists:
            fact = f'pacote_existe("{eco}", "{name}").'
            claims.record(fact, info.source, structured=True)
            again = lookup(f, name)  # fresh retrieval (conditional request: 304 counts as reproduction)
            if again.exists:
                claims.record(fact, again.source, structured=True)
    claims.approve(claims.pending(), by="experimento (no lugar do usuário)")
    suggested_missing = [(e, n) for (e, n), ex in exists_by_registry.items() if claims.can_suggest(e, n) and not ex]
    unsuggested_real = [(e, n) for e, n, k in names if k == "real" and not claims.can_suggest(e, n)]
    # every URL actually requested must be allowed by the site's robots.txt (checked again with our RFC 9309 parser)
    robots = {}
    violations = []
    for url, origin, _status in f.log:
        if origin in ("rede", "cache", "bloqueado") and not url.endswith("/robots.txt"):
            host = url.split("/")[2]
            rules = robots.setdefault(host, f._robots[f"https://{host}"][1])
            if not rules.allowed("nucleo/0.1", url):
                violations.append(url)
    print(dict(c))
    print(f"requisições: {len(f.log)}; pacotes inexistentes sugeridos: {len(suggested_missing)}; "
          f"reais não sugeridos: {unsuggested_real}; violações de robots.txt: {len(violations)}")
    return suggested_missing, violations


if __name__ == "__main__":
    missing, violations = main()
    sys.exit(0 if not missing and not violations else 1)
