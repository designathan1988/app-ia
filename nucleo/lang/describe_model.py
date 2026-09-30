"""A project model from a Portuguese description.

    crie um projeto com a entidade Cliente com email (e-mail, obrigatório, até 120), nome (texto obrigatório de 2 a
    60), idade (inteiro de 0 a 150), plano (opções basico, pro) e ativo (sim ou não); e a entidade Pedido com total
    (decimal, obrigatório, no mínimo 0), itens (inteiro de 1 a 99) e cliente (Cliente)

Grammar:
- "entidade <Nome>" opens an entity;
- then a list of fields, separated by commas or "e" outside parentheses;
- each field is "<nome> (<especificação>)" or "<nome>: <especificação>".

The specification words come from ``SPEC`` below (data): types, "obrigatório", bounds ("de A a B", "entre A e B",
"até N", "no máximo N", "no mínimo N"), "opções a, b". A word that names another entity makes a relation; "lista de
<Entidade>" makes a many-relation. Every word of a specification must be explained: an unknown one is reported and
nothing is generated from a guess.
"""

from __future__ import annotations

import re
import unicodedata

SPEC = {
    "tipos": {"texto": "texto", "string": "texto", "palavra": "texto", "nome": "texto", "frase": "texto",
              "inteiro": "inteiro", "decimal": "decimal", "número": "decimal", "numero": "decimal", "valor": "decimal",
              "preço": "decimal", "preco": "decimal", "booleano": "booleano", "lógico": "booleano"},
    "email": {"e-mail", "email"},
    "obrigatorio": {"obrigatório", "obrigatorio", "requerido", "necessário", "necessario"},
    "opcional": {"opcional"},
    "booleano_frases": ["sim ou não", "sim ou nao", "verdadeiro ou falso"],
    "vazias": {"do", "tipo", "um", "uma", "de", "com", "e", "a", "o", "caracteres", "letras"},
}


class DescriptionError(ValueError):
    pass


def _norm(s: str) -> str:
    return unicodedata.normalize("NFC", s.strip())


def _split_top(text: str, seps: str = ",") -> list[str]:
    """Split at commas (and at " e ") outside parentheses."""
    parts, depth, cur, i = [], 0, "", 0
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth == 0 and (ch in seps or text[i:i + 3] == " e " and i > 0):
            if cur.strip():
                parts.append(cur.strip())
            cur = ""
            i += 3 if text[i:i + 3] == " e " else 1
            continue
        cur += ch
        i += 1
    if cur.strip():
        parts.append(cur.strip())
    return parts


def _spec(field: str, spec: str, entities: set[str], problems: list[str]) -> dict:
    s = spec.strip()
    low = s.lower()
    f: dict = {"nome": field}
    rel = re.fullmatch(r"(?:uma\s+)?lista\s+de\s+(\w+)|v[áa]rios\s+(\w+)", s, flags=re.I)
    if rel:
        target = rel.group(1) or rel.group(2)
        if target in entities:
            return {"nome": field, "relacao": True, "alvo": target, "muitos": True}
    if s in entities:
        return {"nome": field, "relacao": True, "alvo": s, "muitos": False}
    m = re.search(r"op[çc][õo]es\s*:?\s*(.+)$", s, flags=re.I)
    if m:
        f["tipo"] = "enum"
        f["valores"] = [v.strip() for v in re.split(r",|\s+ou\s+|\s+e\s+", m.group(1)) if v.strip()]
        low = low[: m.start()]
    for phrase in SPEC["booleano_frases"]:
        if phrase in low:
            f["tipo"] = "booleano"
            low = low.replace(phrase, " ")
    for pat, keys in ((r"(?:de|entre)\s+(-?\d+(?:[.,]\d+)?)\s+(?:a|e|até)\s+(-?\d+(?:[.,]\d+)?)", ("min", "max")),
                      (r"(?:até|no máximo|máximo|max)\s+(-?\d+(?:[.,]\d+)?)", ("max",)),
                      (r"(?:no mínimo|mínimo|min|a partir de)\s+(-?\d+(?:[.,]\d+)?)", ("min",))):
        for mm in list(re.finditer(pat, low)):
            for k, g in zip(keys, mm.groups()):
                v = float(g.replace(",", "."))
                f[k] = int(v) if v.is_integer() else v
            low = low.replace(mm.group(0), " ")
    for word in re.findall(r"[\wÀ-ÿ-]+", low):
        if word in SPEC["tipos"] and "tipo" not in f:
            f["tipo"] = SPEC["tipos"][word]
        elif word in SPEC["email"]:
            f["tipo"] = "texto"
            f["formato"] = "email"
        elif word in SPEC["obrigatorio"]:
            f["obrigatorio"] = True
        elif word in SPEC["opcional"] or word in SPEC["vazias"] or word in SPEC["tipos"]:
            continue
        else:
            problems.append(f"«{word}» em {field}")
    f.setdefault("tipo", "texto")
    return f


def model_from_text(text: str) -> dict:
    """The model a description asks for; DescriptionError listing every word that was not understood."""
    text = _norm(text)
    chunks = re.split(r"\bentidade\s+", text, flags=re.I)[1:]
    if not chunks:
        raise DescriptionError("não achei nenhuma entidade (escreva «entidade <Nome> com <campos>»)")
    names = [re.match(r"(\w+)", c).group(1) for c in chunks]
    entities = set(names)
    problems: list[str] = []
    model = {"entidades": []}
    for name, chunk in zip(names, chunks):
        body = chunk[len(name):].strip()
        body = re.sub(r"^(com\s+(os\s+)?(campos\s*)?|que\s+tem\s+|tem\s+|:)", "", body, flags=re.I).strip()
        body = re.sub(r"[;.]\s*(e\b\s*)?(a\b\s*)?$", "", body).strip().rstrip(";.").strip()
        body = re.sub(r"\s+e\s+a\s*$|\s+e\s*$", "", body)
        ent = {"nome": name, "campos": [], "relacoes": []}
        for part in _split_top(body):
            m = re.fullmatch(r"(\w+)\s*\((.*)\)\s*", part) or re.fullmatch(r"(\w+)\s*:\s*(.+)", part) or \
                re.fullmatch(r"(\w+)\s+(.+)", part) or re.fullmatch(r"(\w+)", part)
            if not m:
                problems.append(f"campo «{part}»")
                continue
            fname = m.group(1)
            spec = m.group(2) if m.lastindex and m.lastindex >= 2 else "texto"
            f = _spec(fname, spec, entities, problems)
            if f.pop("relacao", False):
                ent["relacoes"].append(f)
            else:
                ent["campos"].append(f)
        model["entidades"].append(ent)
    if problems:
        raise DescriptionError("não entendi: " + "; ".join(problems))
    return model
