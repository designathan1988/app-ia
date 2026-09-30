"""Test generator (not part of the system): Portuguese requests realized from builder-scenario goals.

The realizer varies the surface a request can have:
- the verb among its synonyms, in the imperative ("insira"), the colloquial imperative ("insere"), the infinitive,
  "você pode ...?", "por favor, ..." or "quero que você ..." with the subjunctive;
- word order, with the value first ("coloque 56px na margem superior ...");
- how a node is named: type label plus name ("a seção Hero");
- contractions ("na", "do", "dentro da").

It uses the builder's labels and MorphoBr (gender, verb forms), like any Portuguese writer would, but none of the
understanding code. The expected outcome is never produced here: it is the scenario's own expected document, judged
by the builder's matchDocument.
"""

from __future__ import annotations

import random
import sqlite3
from functools import lru_cache

from nucleo.lang import lexicon
from nucleo.lang.morph import DB, gender

VERBS = {
    "added": ["inserir", "colocar", "adicionar", "incluir", "criar", "pôr"],
    "removed": ["apagar", "remover", "excluir", "tirar", "eliminar"],
    "moved": ["mover", "levar", "passar", "colocar"],
    "style": ["definir", "mudar", "alterar", "deixar", "ajustar", "colocar"],
    "text": ["mudar", "alterar", "trocar", "definir"],
    "name": ["renomear"],
    "attr": ["definir", "mudar", "alterar", "colocar"],
}
CONTRACT = {("de", "o"): "do", ("de", "a"): "da", ("em", "o"): "no", ("em", "a"): "na", ("a", "o"): "ao",
            ("de", "os"): "dos", ("de", "as"): "das", ("em", "os"): "nos", ("em", "as"): "nas"}


@lru_cache(maxsize=None)
def form(lemma: str, tags: str) -> str | None:
    con = sqlite3.connect(DB)
    row = con.execute("SELECT form FROM f WHERE lemma = ? AND tags = ? ORDER BY length(form) LIMIT 1",
                      (lemma, tags)).fetchone()
    return row[0] if row else None


def label(kind: str, id_: str) -> str:
    for e in lexicon.load():
        if e.kind == kind and e.id == id_ and e.label != id_:
            return e.label
    return id_


def article(noun_phrase: str, definite: bool) -> str:
    g = gender(noun_phrase.split()[0].lower()) or "M"
    if definite:
        return "a" if g == "F" else "o"
    return "uma" if g == "F" else "um"


def prep(p: str, det: str) -> str:
    return CONTRACT.get((p, det), f"{p} {det}")


def node_np(node: dict, with_type: bool = True) -> tuple[str, str]:
    """(determiner, rest) for a node: ("a", "seção Hero")."""
    t = label("tipo", node["type"]).lower()
    return article(t, True), (f"{t} {node['name']}" if with_type else node["name"])


def with_prep(p: str, node: dict) -> str:
    det, rest = node_np(node)
    return f"{prep(p, det)} {rest}"


def verb_phrase(lemma: str, rng: random.Random) -> tuple[str, str]:
    """(prefix, verb form) in one of several moods; the suffix "?" is added for the question form."""
    style = rng.choice(["imp", "imp", "imp2", "inf", "pode", "favor", "quero"])
    if style == "imp2":
        return "", form(lemma, "V+IMP+2+SG") or form(lemma, "V+IMP+3+SG")
    if style == "inf":
        return "", lemma
    if style == "pode":
        return "você pode ", lemma
    if style == "quero":
        return "quero que você ", form(lemma, "V+SBJR+3+SG")
    v = form(lemma, "V+IMP+3+SG")
    return ("por favor, " if style == "favor" else ""), v


def quoted(v) -> str:
    s = str(v)
    return f'"{s}"' if (" " in s or "," in s) else s


def describable_insert(item: dict, default: dict | None) -> dict | None:
    """What must be said about a node the goal adds, beyond its type: {} for a plain insertion, {"text": ..,
    "name": ..} for the fields that differ from the builder's default node, None when other fields differ too
    (a tag, styles, attributes: not describable by these requests)."""
    if default is None:
        return None
    node = item.get("node") or {}
    for f in set(node) | set(default):
        if f in ("id", "children", "name", "text"):
            continue
        if node.get(f) != default.get(f):
            return None  # a field these requests cannot say (a tag, styles, custom attributes, ...)
    out = {}
    if item.get("text") is not None and item["text"] != default.get("text"):
        out["text"] = item["text"]
    base = default.get("name") or ""
    name = item.get("name") or ""
    if name and not (name == base or (name.startswith(base + " ") and name[len(base) + 1:].isdigit())):
        out["name"] = name
    return out


def realize(item: dict, nodes: dict, goal_nodes: dict, layer: tuple, rng: random.Random,
            defaults: dict | None = None) -> str | None:
    kind = item["kind"]
    if kind == "field" and item["field"] == "text":
        key = "text"
    elif kind == "field" and item["field"] == "name":
        key = "name"
    elif kind == "field" and item["field"] == "attributes":
        key = "attr"
    elif kind in ("reordered", "moved"):
        key = "moved"
    elif kind in ("style", "added", "removed"):
        key = kind
    else:
        return None
    lemma = rng.choice(VERBS[key])
    pre, v = verb_phrase(lemma, rng)
    if not v:
        return None
    ask = pre.startswith("você pode")
    if key == "style":
        node = nodes.get(item["id"])
        if not node or not isinstance(item["value"], (str, int, float)):
            return None  # a structured value (the shadow editor's list of layers) is not said in a sentence
        plabel = label("propriedade", item["property"]).lower()
        det = article(plabel, True)
        owner = with_prep("de", node)
        extra = ""
        if item["breakpoint"] != layer[0]:
            bl = label("breakpoint", item["breakpoint"]).lower()
            extra += f" {prep('em', article(bl, True))} {bl}"
        if item["state"] != layer[1]:
            sl = label("estado", item["state"]).lower()
            extra += f" {sl}" if sl.startswith("ao ") else f" no estado {sl}"
        val = quoted(item["value"])
        if lemma == "colocar" and rng.random() < 0.5:
            s = f"{pre}{v} {val} {prep('em', det)} {plabel} {owner}{extra}"
        else:
            link = {"definir": "como", "mudar": "para", "alterar": "para", "deixar": "em", "ajustar": "para",
                    "colocar": "como"}[lemma]
            s = f"{pre}{v} {det} {plabel} {owner} {link} {val}{extra}"
    elif key in ("text", "name", "attr"):
        node = nodes.get(item["id"])
        if not node:
            return None
        if key == "name":
            s = f"{pre}{v} {' '.join(node_np(node))} para {quoted(item['value'])}"
        elif key == "text":
            s = f"{pre}{v} o texto {with_prep('de', node)} para \"{item['value']}\""
        else:
            cur = item.get("current") or {}
            changed = [k for k, x in (item["value"] or {}).items() if cur.get(k) != x]
            if len(changed) != 1:
                return None
            k = changed[0]
            al = label("atributo", k).lower()
            s = f"{pre}{v} {article(al, True)} {al} {with_prep('de', node)} como \"{item['value'][k]}\""
    elif key == "removed":
        node = nodes.get(item["id"])
        if not node:
            return None
        s = f"{pre}{v} {' '.join(node_np(node))}"
    elif key == "moved":
        node = nodes.get(item["id"])
        parent = goal_nodes.get(item["parent"]) if item.get("parent") else None
        if not node or not parent:
            return None
        s = f"{pre}{v} {' '.join(node_np(node))} " + place(parent, item["index"], goal_nodes, exclude=item["id"])
    else:  # added
        if not item.get("parent") or item["parent"] not in goal_nodes:
            return None
        extras = describable_insert(item, (defaults or {}).get(item["type"]))
        if extras is None:
            return None
        t = label("tipo", item["type"]).lower()
        said = ""
        if "name" in extras:
            said += f" chamado {quoted(extras['name'])}" if " " not in extras["name"] else f" com o nome \"{extras['name']}\""
        if "text" in extras:
            said += f" com o texto \"{extras['text']}\""
        s = f"{pre}{v} {article(t, False)} {t}{said} " + place(goal_nodes[item["parent"]], item["index"], goal_nodes)
    s = s.strip()
    return s + ("?" if ask else rng.choice(["", ".", ""]))


def place(parent: dict, index: int, goal_nodes: dict, exclude=None) -> str:
    """Where, in words: "no início da seção X", "depois do título Y", "na seção X" (appended last)."""
    kids = [k for k in parent["children"] if k != exclude and k in goal_nodes and goal_nodes[k].get("name")]
    if index == 0:
        det, rest = node_np(parent)
        return f"no início {prep('de', det)} {rest}"
    if index is not None and 0 < index <= len(kids):
        prev = goal_nodes[kids[index - 1]]
        if index == len(kids) and prev.get("name"):
            return f"depois {with_prep('de', prev)}"
        return f"depois {with_prep('de', prev)}"
    det, rest = node_np(parent)
    return f"{prep('em', det)} {rest}"
