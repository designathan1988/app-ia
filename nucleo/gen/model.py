"""The project model that code generators read: entities, typed fields, constraints and relations.

    {"entidades": [
       {"nome": "Cliente",
        "campos": [{"nome": "email", "tipo": "texto", "obrigatorio": true, "max": 120, "formato": "email"},
                   {"nome": "idade", "tipo": "inteiro", "min": 0, "max": 150},
                   {"nome": "plano", "tipo": "enum", "valores": ["basico", "pro"]},
                   {"nome": "ativo", "tipo": "booleano"}],
        "relacoes": [{"nome": "pedidos", "alvo": "Pedido", "muitos": true}]}]}

Field types: texto, inteiro, decimal, booleano, enum. Constraints: obrigatorio, min/max (value for numbers, length
for text), formato ("email"), valores (enum). A relation stores the id (or ids) of entities of the target type.

``check_model`` rejects a model the generators cannot honour (unknown type, relation to a missing entity, duplicate
names, identifiers that are not valid in both languages), so generation starts only from a sound model.
"""

from __future__ import annotations

import keyword
import re

TYPES = {"texto", "inteiro", "decimal", "booleano", "enum"}
TS_RESERVED = {"break", "case", "catch", "class", "const", "continue", "debugger", "default", "delete", "do", "else",
               "enum", "export", "extends", "false", "finally", "for", "function", "if", "import", "in",
               "instanceof", "new", "null", "return", "super", "switch", "this", "throw", "true", "try", "typeof",
               "var", "void", "while", "with", "let", "static", "yield", "await", "implements", "interface",
               "package", "private", "protected", "public", "id"}


class ModelError(ValueError):
    pass


def _ident(name: str, what: str) -> None:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name) or keyword.iskeyword(name) or name in TS_RESERVED:
        raise ModelError(f"{what} «{name}» não é um identificador válido em TypeScript e Python")


def check_model(model: dict) -> None:
    ents = model.get("entidades") or []
    if not ents:
        raise ModelError("o modelo não tem entidades")
    names = [e["nome"] for e in ents]
    if len(set(names)) != len(names):
        raise ModelError("entidades com o mesmo nome")
    for e in ents:
        _ident(e["nome"], "entidade")
        seen = set()
        for f in e.get("campos", []) + e.get("relacoes", []):
            _ident(f["nome"], f"campo de {e['nome']}")
            if f["nome"] in seen:
                raise ModelError(f"{e['nome']}.{f['nome']} repetido")
            seen.add(f["nome"])
        for f in e.get("campos", []):
            if f["tipo"] not in TYPES:
                raise ModelError(f"{e['nome']}.{f['nome']}: tipo desconhecido {f['tipo']}")
            if f["tipo"] == "enum" and not f.get("valores"):
                raise ModelError(f"{e['nome']}.{f['nome']}: enum sem valores")
            if "min" in f and "max" in f and f["min"] > f["max"]:
                raise ModelError(f"{e['nome']}.{f['nome']}: min > max")
        for r in e.get("relacoes", []):
            if r["alvo"] not in names:
                raise ModelError(f"{e['nome']}.{r['nome']}: relação com entidade inexistente {r['alvo']}")


def reference_errors(entity: dict, obj: dict) -> set[str]:
    """What is wrong with `obj` for `entity`, straight from the model's meaning (the test oracle; independent of the
    generated code). Each error is "<field>:<rule>"."""
    errs = set()
    if not isinstance(obj, dict):
        return {"$:objeto"}
    for f in entity.get("campos", []):
        n, t = f["nome"], f["tipo"]
        if n not in obj or obj[n] is None:
            if f.get("obrigatorio"):
                errs.add(f"{n}:obrigatorio")
            continue
        v = obj[n]
        if t == "texto":
            if not isinstance(v, str):
                errs.add(f"{n}:tipo")
                continue
            if "min" in f and len(v) < f["min"]:
                errs.add(f"{n}:min")
            if "max" in f and len(v) > f["max"]:
                errs.add(f"{n}:max")
            if f.get("formato") == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
                errs.add(f"{n}:formato")
        elif t in ("inteiro", "decimal"):
            if isinstance(v, bool) or not isinstance(v, (int, float)) or (t == "inteiro" and float(v) != int(v)):
                errs.add(f"{n}:tipo")
                continue
            if "min" in f and v < f["min"]:
                errs.add(f"{n}:min")
            if "max" in f and v > f["max"]:
                errs.add(f"{n}:max")
        elif t == "booleano":
            if not isinstance(v, bool):
                errs.add(f"{n}:tipo")
        elif t == "enum":
            if v not in f["valores"]:
                errs.add(f"{n}:valores")
    for r in entity.get("relacoes", []):
        n = r["nome"]
        if n not in obj or obj[n] is None:
            continue
        v = obj[n]
        if r.get("muitos"):
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                errs.add(f"{n}:tipo")
        elif not isinstance(v, str):
            errs.add(f"{n}:tipo")
    return errs
