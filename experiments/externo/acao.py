"""Plano D, action layer: edit requests other people wrote, judged by the commands they were labelled with.

DocEdit-PDF (Mathur et al., AAAI 2023; Adobe Research DocEdit Dataset License 1.0, noncommercial): ~14K edit
requests over PDF pages, written by people, each labelled ``action_para ACTION component_para COMPONENT
intial_state ... final_state ...``. The states are free text, so only the action and the component are judged.

The documents are images, which the engine does not see, so the page is one ordinary document with the components
DocEdit names (header, headings, paragraphs, a list, an image with caption, a table, a footer with the page
number). Requests that name text this page does not have must be asked, not guessed.

**Adapter** (fixed once, at the level of the DSL's vocabulary, never per sentence) — which changes of state of the
builder count as each DocEdit action:
- ADD    -> an element added
- DELETE -> an element removed, or a value taken away (style back to its default: "remove the highlight")
- MOVE   -> an element moved, or a position/alignment style (DocEdit labels "moved the title to the center" MOVE)
- MODIFY -> a style or a command on an element
- REPLACE-> a text or field changed, or a style value changed
- COPY   -> a duplicate command
- SPLIT, MERGE -> nothing the builder does: any executed change is wrong
Outcome per request: **certo** (executed, and every change is of a kind its action allows), **ERRADO** (executed,
some change is not), **perguntou** (did not execute). Also reported: **leitura** — whether the engine's best
reading, executed or not, is of the right kind (what it understood, apart from whether it dared to act).

Splits: ``train.csv`` is for learning (D3); ``val.csv`` is divided by document (hash of the image name) into
``dev`` (work) and ``teste`` (gates only). DocEdit's own test has no labels.

Usage: python experiments/externo/acao.py [dev|teste] [limit] [-v]
"""
from __future__ import annotations

import collections
import csv
import ctypes
import hashlib
import json
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data" / "externo" / "docedit" / "DocEdit-PDF-trainval"
COMMAND = re.compile(r"action_para\s+(\S+)\s+component_para\s+(.*?)\s+intial_state", re.S)
POSITION = {"text-align", "justify-content", "justify-self", "align-self", "align-items", "float", "position",
            "top", "left", "right", "bottom", "margin", "margin-left", "margin-right", "margin-top", "margin-bottom",
            "order", "vertical-align", "inset"}

NODES = {
    "pg": ("Page", "page", None, ["hd", "mn", "ft"], None),
    "hd": ("Header", "header", "pg", ["hdt"], None),
    "hdt": ("Header text", "paragraph", "hd", [], "Quarterly Report"),
    "mn": ("Main", "main", "pg", ["h1", "p1", "h2", "p2", "ls", "fg", "tb", "p3"], None),
    "h1": ("Heading", "heading", "mn", [], "Introduction"),
    "p1": ("Paragraph", "paragraph", "mn", [], "This report summarizes the results of the quarter."),
    "h2": ("Heading 2", "heading", "mn", [], "Summary"),
    "p2": ("Paragraph 2", "paragraph", "mn", [], "Revenue grew in every region."),
    "ls": ("List", "list", "mn", ["li1", "li2", "li3"], None),
    "li1": ("List item", "listItem", "ls", [], "First point"),
    "li2": ("List item 2", "listItem", "ls", [], "Second point"),
    "li3": ("List item 3", "listItem", "ls", [], "Third point"),
    "fg": ("Figure", "figure", "mn", ["im", "fc"], None),
    "im": ("Image", "image", "fg", [], None),
    "fc": ("Caption", "figureCaption", "fg", [], "Figure 1. Results"),
    "tb": ("Table", "table", "mn", ["tr1", "tr2"], None),
    "tr1": ("Table row", "tableRow", "tb", ["c11", "c12"], None),
    "c11": ("Cell", "cell", "tr1", [], "Region"),
    "c12": ("Cell 2", "cell", "tr1", [], "Total"),
    "tr2": ("Table row 2", "tableRow", "tb", ["c21", "c22"], None),
    "c21": ("Cell 3", "cell", "tr2", [], "North"),
    "c22": ("Cell 4", "cell", "tr2", [], "120"),
    "p3": ("Paragraph 3", "paragraph", "mn", [], "Conclusions follow."),
    "ft": ("Footer", "footer", "pg", ["pn"], None),
    "pn": ("Page number", "paragraph", "ft", [], "1"),
}


def world():
    from nucleo.lang.base import World

    def node(nid):
        name, typ, _, kids, text = NODES[nid]
        n = {"id": nid, "type": typ, "name": name, "children": [node(k) for k in kids]}
        if text is not None:
            n["text"] = text
        return n

    return World.from_document({"pages": [{"tree": node("pg")}]}, [])


def _split_of(image: str) -> str:
    return "dev" if int(hashlib.sha256(image.encode("utf-8")).hexdigest(), 16) % 2 == 0 else "teste"


def requests(split: str) -> list[dict]:
    name = "train.csv" if split == "treino" else "val.csv"
    rows = list(csv.DictReader((DATA / name).open(encoding="utf-8")))
    out = []
    for r in rows:
        m = COMMAND.match(r["command"].strip())
        if not m:
            continue
        if split in ("dev", "teste") and _split_of(r["image"]) != split:
            continue
        out.append({"id": r["id"], "text": " ".join(r["user_request"].split()), "action": m.group(1).upper(),
                    "component": m.group(2).strip().upper()})
    return out


def kind_of(c: dict) -> str:
    """The DocEdit action a change of the builder's state is an instance of (several when ambiguous)."""
    k = c.get("kind", "")
    if k == "added":
        return "ADD"
    if k == "removed":
        return "DELETE"
    if k == "moved":
        return "MOVE"
    if k == "style":
        prop = c.get("property", "")
        if prop in POSITION:
            return "MOVE"
        return "MODIFY|REPLACE|DELETE"  # (a style set to its default takes a value away)
    if k == "command":
        return "COPY|MODIFY" if "duplicate" in str(c.get("command", "")).lower() else "MODIFY|DELETE"
    if k.startswith("field"):
        return "REPLACE|MODIFY"
    return "?"


def fits(constraints: list, action: str) -> bool:
    return bool(constraints) and all(action in kind_of(c).split("|") for c in constraints)


def run(split: str, limit: int | None, verbose: bool) -> dict:
    from nucleo.lang.interpret import understand_request

    w = world()
    rows = requests(split)[:limit]
    out = collections.Counter()
    by_action = collections.defaultdict(collections.Counter)
    decisions = collections.Counter()
    read_ok = 0
    examples = []
    crashes = []
    t = time.time()
    for r in rows:
        try:
            u = understand_request(r["text"], w, lang="en")
            d = u.decision
            best = u.best.constraints if u.best else []
        except Exception as e:  # noqa: BLE001 — counted, never hidden
            d, best = f"exceção {type(e).__name__}", []
            crashes.append((r["text"], repr(e)[:200]))
        decisions[d] += 1
        read_ok += fits(best, r["action"])
        if d == "executar" and best:
            o = "certo" if fits(best, r["action"]) else "ERRADO"
        else:
            o = "perguntou"
        out[o] += 1
        by_action[r["action"]][o] += 1
        if o == "ERRADO":
            examples.append({"pedido": r["text"], "rotulo": r["action"], "componente": r["component"],
                             "restricoes": best})
            if verbose:
                print(f"[ERRADO] ({r['action']}/{r['component']}) {r['text']}\n    -> {best}")
    n = max(1, len(rows))
    return {"split": split, "n": len(rows), **dict(out), "taxa_certo": round(out["certo"] / n, 4),
            "taxa_errado": round(out["ERRADO"] / n, 4), "leitura_certa": round(read_ok / n, 4),
            "por_acao": {a: dict(c) for a, c in sorted(by_action.items())}, "decisoes": dict(decisions),
            "segundos": round(time.time() - t, 1), "exemplos_errados": examples[:80],
            "excecoes_frases": crashes[:30]}


if __name__ == "__main__":
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    split = args[0] if args else "dev"
    assert split in ("dev", "teste"), "treino is for learning, not for measuring"
    limit = int(args[1]) if len(args) > 1 else None
    res = run(split, limit, "-v" in sys.argv)
    print(json.dumps({k: v for k, v in res.items() if k != "exemplos_errados"}, ensure_ascii=False))
    if limit is None:
        dest = ROOT / "data" / "cache" / f"externo_acao_{split}.json"
        dest.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print("gravado em", dest)
