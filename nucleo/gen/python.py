"""Model -> a Python package: dataclasses, validators, an in-memory store with referential integrity, and tests.

Same error codes as the TypeScript project and as the model's reference meaning, so the three can be compared.
"""

from __future__ import annotations

import json

PY_TYPE = {"texto": "str", "inteiro": "int", "decimal": "float", "booleano": "bool"}


def models_py(model: dict) -> str:
    out = ['"""Generated from the project model. Do not edit: change the model and generate again."""', "",
           "from __future__ import annotations", "", "from dataclasses import dataclass, field", "from typing import Literal, Optional", ""]
    for e in model["entidades"]:
        out.append("")
        out.append("@dataclass")
        out.append(f"class {e['nome']}:")
        req = [f for f in e.get("campos", []) if f.get("obrigatorio")]
        opt = [f for f in e.get("campos", []) if not f.get("obrigatorio")]
        for f in req + opt:
            t = f"Literal[{', '.join(json.dumps(v) for v in f['valores'])}]" if f["tipo"] == "enum" else PY_TYPE[f["tipo"]]
            out.append(f"    {f['nome']}: {t}" if f.get("obrigatorio") else f"    {f['nome']}: Optional[{t}] = None")
        for r in e.get("relacoes", []):
            out.append(f"    {r['nome']}: Optional[list[str]] = None  # ids of {r['alvo']}" if r.get("muitos")
                       else f"    {r['nome']}: Optional[str] = None  # id of {r['alvo']}")
        out.append("    id: Optional[str] = field(default=None)")
    return "\n".join(out) + "\n"


def _check(f: dict) -> list[str]:
    n, t = f["nome"], f["tipo"]
    q = json.dumps(n)
    lines = [f"    v = o.get({q})", "    if v is None:"]
    lines.append(f"        {'errors.append(' + json.dumps(n + ':obrigatorio') + ')' if f.get('obrigatorio') else 'pass'}")
    if t == "texto":
        lines.append("    elif not isinstance(v, str):")
        lines.append(f"        errors.append({json.dumps(n + ':tipo')})")
        lines.append("    else:")
        body = []
        if "min" in f:
            body.append(f"        if len(v) < {f['min']}:\n            errors.append({json.dumps(n + ':min')})")
        if "max" in f:
            body.append(f"        if len(v) > {f['max']}:\n            errors.append({json.dumps(n + ':max')})")
        if f.get("formato") == "email":
            body.append(f"        if not _EMAIL.fullmatch(v):\n            errors.append({json.dumps(n + ':formato')})")
        lines.append("\n".join(body) if body else "        pass")
    elif t in ("inteiro", "decimal"):
        cond = "isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v in (float('inf'), float('-inf'))"
        if t == "inteiro":
            cond += " or float(v) != int(v)"
        lines.append(f"    elif {cond}:")
        lines.append(f"        errors.append({json.dumps(n + ':tipo')})")
        lines.append("    else:")
        body = []
        if "min" in f:
            body.append(f"        if v < {f['min']}:\n            errors.append({json.dumps(n + ':min')})")
        if "max" in f:
            body.append(f"        if v > {f['max']}:\n            errors.append({json.dumps(n + ':max')})")
        lines.append("\n".join(body) if body else "        pass")
    elif t == "booleano":
        lines.append("    elif not isinstance(v, bool):")
        lines.append(f"        errors.append({json.dumps(n + ':tipo')})")
    else:
        lines.append(f"    elif v not in {json.dumps(f['valores'])}:")
        lines.append(f"        errors.append({json.dumps(n + ':valores')})")
    return lines


def validate_py(model: dict) -> str:
    out = ['"""Generated from the project model. Do not edit: change the model and generate again."""', "",
           "from __future__ import annotations", "", "import re", "",
           r'_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")', ""]
    for e in model["entidades"]:
        out.append("")
        out.append(f"def validate_{e['nome']}(o: object) -> list[str]:")
        out.append(f'    """What is wrong with a candidate {e["nome"]}: codes "<field>:<rule>"; empty when valid."""')
        out.append("    if not isinstance(o, dict):")
        out.append("        return ['$:objeto']")
        out.append("    errors: list[str] = []")
        for f in e.get("campos", []):
            out += _check(f)
        for r in e.get("relacoes", []):
            q = json.dumps(r["nome"])
            if r.get("muitos"):
                cond = "not isinstance(v, list) or not all(isinstance(x, str) for x in v)"
            else:
                cond = "not isinstance(v, str)"
            out.append(f"    v = o.get({q})")
            out.append(f"    if v is not None and ({cond}):")
            out.append(f"        errors.append({json.dumps(r['nome'] + ':tipo')})")
        out.append("    return errors")
    out.append("")
    out.append("")
    out.append("VALIDATORS = {" + ", ".join(f"{json.dumps(e['nome'])}: validate_{e['nome']}" for e in model["entidades"]) + "}")
    return "\n".join(out) + "\n"


def store_py(model: dict) -> str:
    rels = {e["nome"]: [(r["nome"], r["alvo"], bool(r.get("muitos"))) for r in e.get("relacoes", [])]
            for e in model["entidades"]}
    return '\n'.join([
        '"""Generated from the project model. In-memory store: every write is validated, and relations must point',
        'to existing records."""', "",
        "from __future__ import annotations", "",
        "from .validate import VALIDATORS", "",
        f"RELATIONS = {rels!r}", "", "",
        "class Store:",
        "    def __init__(self) -> None:",
        "        self._tables: dict[str, dict[str, dict]] = {}",
        "        self._next = 1", "",
        "    def _table(self, kind: str) -> dict[str, dict]:",
        "        return self._tables.setdefault(kind, {})", "",
        "    def _check(self, kind: str, value: dict) -> list[str]:",
        "        errors = VALIDATORS[kind](value)",
        "        for fieldname, target, many in RELATIONS[kind]:",
        "            v = value.get(fieldname)",
        "            if v is None:",
        "                continue",
        "            ids = (v if isinstance(v, list) else []) if many else [v]",
        "            if any(not isinstance(i, str) or i not in self._table(target) for i in ids):",
        "                errors.append(f'{fieldname}:referencia')",
        "        return errors", "",
        "    def create(self, kind: str, value: dict) -> dict:",
        "        errors = self._check(kind, value)",
        "        if errors:",
        "            return {'ok': False, 'errors': errors}",
        "        rid = f'{kind}-{self._next}'",
        "        self._next += 1",
        "        self._table(kind)[rid] = {**value, 'id': rid}",
        "        return {'ok': True, 'id': rid}", "",
        "    def get(self, kind: str, rid: str) -> dict | None:",
        "        v = self._table(kind).get(rid)",
        "        return dict(v) if v else None", "",
        "    def list(self, kind: str) -> list[dict]:",
        "        return [dict(v) for v in self._table(kind).values()]", "",
        "    def update(self, kind: str, rid: str, changes: dict) -> dict:",
        "        current = self._table(kind).get(rid)",
        "        if current is None:",
        "            return {'ok': False, 'errors': ['$:inexistente']}",
        "        nxt = {**current, **changes, 'id': rid}",
        "        errors = self._check(kind, nxt)",
        "        if errors:",
        "            return {'ok': False, 'errors': errors}",
        "        self._table(kind)[rid] = nxt",
        "        return {'ok': True, 'id': rid}", "",
        "    def remove(self, kind: str, rid: str) -> dict:",
        '        """Refused while another record still points to this one."""',
        "        if rid not in self._table(kind):",
        "            return {'ok': False, 'errors': ['$:inexistente']}",
        "        for other, rels in RELATIONS.items():",
        "            for fieldname, target, _many in rels:",
        "                if target != kind:",
        "                    continue",
        "                for rec in self._table(other).values():",
        "                    v = rec.get(fieldname)",
        "                    if v == rid or (isinstance(v, list) and rid in v):",
        "                        return {'ok': False, 'errors': ['$:referenciado']}",
        "        del self._table(kind)[rid]",
        "        return {'ok': True, 'id': rid}", ""])


def tests_py(model: dict, examples: dict) -> str:
    out = ['"""Generated from the project model."""', "", "from .store import Store", "from .validate import VALIDATORS", ""]
    for e in model["entidades"]:
        ex = examples[e["nome"]]
        out.append("")
        out.append(f"def test_{e['nome']}_valid_and_violations():")
        out.append(f"    assert VALIDATORS[{json.dumps(e['nome'])}]({json.dumps(ex['valido'])!r}) == []".replace("!r", ""))
        out[-1] = f"    assert VALIDATORS[{json.dumps(e['nome'])}]({_py(ex['valido'])}) == []"
        for obj, codes in ex["violacoes"]:
            out.append(f"    assert sorted(VALIDATORS[{json.dumps(e['nome'])}]({_py(obj)})) == {sorted(codes)!r}")
    out.append("")
    out.append("")
    out.append("def test_store_integrity():")
    out.append("    s = Store()")
    for e in model["entidades"]:
        obj = dict(examples[e["nome"]]["valido"])
        for r in e.get("relacoes", []):
            obj.pop(r["nome"], None)
        out.append(f"    r = s.create({json.dumps(e['nome'])}, {_py(obj)})")
        out.append("    assert r['ok'] and s.get(" + json.dumps(e["nome"]) + ", r['id'])['id'] == r['id']")
    for e in model["entidades"]:
        for r in e.get("relacoes", []):
            obj = dict(examples[e["nome"]]["valido"])
            obj[r["nome"]] = ["nao-existe"] if r.get("muitos") else "nao-existe"
            out.append(f"    assert s.create({json.dumps(e['nome'])}, {_py(obj)}) == "
                       f"{{'ok': False, 'errors': [{json.dumps(r['nome'] + ':referencia')}]}}")
    return "\n".join(out) + "\n"


def _py(obj) -> str:
    return repr(obj)


def project(model: dict, examples: dict, package: str = "gerado") -> dict[str, str]:
    return {
        f"{package}/__init__.py": '"""Generated from the project model."""\n',
        f"{package}/models.py": models_py(model),
        f"{package}/validate.py": validate_py(model),
        f"{package}/store.py": store_py(model),
        f"{package}/test_gerado.py": tests_py(model, examples),
    }
