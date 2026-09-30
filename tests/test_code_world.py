"""M3: code knowledge by rules, judged by the compilers themselves (TypeScript checker and language service,
CPython's symbol tables). The tricky scoping cases are written here as small programs; the answers come from the
compilers, not from this file."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sysconfig

import pytest

from nucleo.builder.client import DEFAULT_BUILDER
from nucleo.code.project import CodeBase
from nucleo.code.python_facts import facts_of
from nucleo.code.resolve import resolve_file

ROOT = pathlib.Path(__file__).resolve().parents[1]
TS_FACTS = ROOT / "bridge" / "code" / "ts_facts.mjs"
ENV = {**os.environ, "NUCLEO_TS": DEFAULT_BUILDER}


def _ts_extract(project: str, tsconfig: str) -> list[dict]:
    out = subprocess.run(["node", str(TS_FACTS), project, tsconfig], capture_output=True, text=True,
                         encoding="utf-8", check=True, env=ENV).stdout
    return [json.loads(l) for l in out.splitlines() if l.strip()]


def _agree(f: dict) -> tuple[int, list]:
    ours, _ = resolve_file(f)
    n, bad = 0, []
    for use in f["uses"]:
        pos, name = use[0], use[1]
        truth = f["oracle"].get(str(pos))
        if truth is None:
            continue
        mine = ours.get(pos)
        ok = (truth == "externo" and mine == "externo") or (isinstance(truth, list) and mine in truth) or (
            isinstance(truth, str) and truth != "externo" and mine not in (None, "externo"))
        n += 1
        if not ok:
            bad.append((f["file"], name, pos, mine, truth))
    return n, bad


TS_TRICKY = {
    "src/a.ts": """
export const shared = 1;
export function hoisted() { return later; }
var later = 2;
export type Pair = [number, number];
export interface Box { v: Pair }
export class Thing { m(x: Box): Box { const Pair = 3; return { v: [Pair, x.v[0]] }; } }
function outer() { let v = 1; { let v = 2; return v; } }
for (let i = 0; i < 3; i++) { const j = i; }
try { outer(); } catch (e) { console.log(e); }
const brand: unique symbol = Symbol();
export type Id = number & { readonly [brand]: true };
export { hoisted as renamed };
export default Thing;
""",
    "src/b.ts": """
import Thing, { shared as s, renamed, type Pair } from './a';
import * as all from './a';
export * from './a';
function Pair2(p: Pair) { return p; }
const t = new Thing();
export const total = s + renamed() + all.shared + t.m({ v: Pair2([1, 2]) }).v[0];
""",
    "src/c.ts": """
import { total, hoisted } from './b';
export const again = total + hoisted();
""",
}


@pytest.fixture(scope="module")
def tricky_ts(tmp_path_factory):
    d = tmp_path_factory.mktemp("tsproj")
    (d / "tsconfig.json").write_text(json.dumps({"compilerOptions": {"strict": True, "target": "ES2022",
                                                  "module": "ESNext", "moduleResolution": "bundler",
                                                  "noEmit": True, "lib": ["ES2022", "DOM"]},
                                                  "include": ["src"]}), encoding="utf-8")
    (d / "package.json").write_text("{}", encoding="utf-8")
    for name, src in TS_TRICKY.items():
        (d / name).parent.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(src, encoding="utf-8")
    return str(d), _ts_extract(str(d), "tsconfig.json")


def test_ts_tricky_scoping_agrees_with_the_checker(tricky_ts):
    _, files = tricky_ts
    total, bad = 0, []
    for f in files:
        n, b = _agree(f)
        total += n
        bad += b
    assert total > 25 and not bad, bad


def test_ts_cross_file_chains_agree_with_the_checker(tricky_ts):
    from nucleo.code.modules import resolve_imports

    _, files = tricky_ts
    ours, _ = resolve_imports(files)
    checked = 0
    for f in files:
        for pos, local, _spec, _imp in f["imports"]:
            truth = f["aliasOracle"][str(pos)]
            mine = ours.get((f["file"], pos), set())
            assert mine and mine <= set(truth), (f["file"], local, mine, truth)
            checked += 1
    assert checked >= 6


def test_ts_whole_builder_agrees_with_the_checker():
    files = _ts_extract(DEFAULT_BUILDER, "tsconfig.app.json")
    total, bad = 0, []
    for f in files:
        n, b = _agree(f)
        total += n
        bad += b
    assert total > 60000 and not bad, bad[:5]


PY_TRICKY = '''
import os.path as osp
from typing import TypeVar
T = TypeVar("T")
x = 1
class C[T]:
    x = 2
    __hidden = 3
    def m(self, d=__hidden) -> T:
        return x
    ys = [x for _ in range(2)]
    def n(self):
        global x
        x = 4
        return self.__hidden
def outer(a):
    b = [i * a for i in range(3)]
    g = (j for j in b)
    def inner():
        nonlocal a
        a += 1
        return a
    if (w := len(b)) > 1:
        return w, g, inner, lambda q: q + b[0]
type Alias[V] = list[V]
def uses():
    return osp.join(str(T), str(C), str(Alias))
'''


def test_python_tricky_scoping_agrees_with_symtable():
    n, bad = _agree(facts_of(PY_TRICKY, "tricky.py"))
    assert n > 25 and not bad, bad


def test_python_stdlib_sample_agrees_with_symtable():
    lib = sorted(pathlib.Path(sysconfig.get_paths()["stdlib"]).glob("*.py"))[::6]
    total = 0
    for path in lib:
        src = path.read_text(encoding="utf-8", errors="replace")
        n, bad = _agree(facts_of(src, path.name))
        total += n
        assert not bad, bad[:3]
    assert total > 10000


def test_references_and_unused_by_rules(tricky_ts):
    _, files = tricky_ts
    cb = CodeBase(files)
    decl = next(d for d in next(f for f in files if f["file"] == "src/a.ts")["decls"] if d[1] == "shared")
    refs = cb.references("src/a.ts", decl[2])
    assert {f for f, _ in refs} == {"src/b.ts"}  # via `shared as s` and via `all.shared`? only the named import
    unused = cb.unused_exports()
    names = {n for f in files for d in f["decls"] for n in [d[1]] if (f["file"], d[2]) in unused}
    assert "again" in names and "shared" not in names
    impact = cb.impact("src/a.ts", decl[2])
    assert ("src/b.ts",) and any(f == "src/c.ts" for f, _ in impact)  # a -> b.total -> c.again
