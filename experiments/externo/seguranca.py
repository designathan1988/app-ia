"""Plano D, safety layer: sentences other people wrote, none of them about the page, must never change it.

MASSIVE 1.1 (FitzGerald et al. 2022, Amazon): virtual-assistant utterances written and localized by people, parallel
in pt-PT and en-US (alarms, music, lights, weather, calendar, ...). None refers to a web page, so the mechanical
oracle is: **any change the engine executes is an error**. Asking, refusing or answering as talk is right.

The page is a fixed ordinary page (headings, paragraphs, buttons, an image, sections, a footer), so that lexical
coincidences ("turn the lights blue", "remove the alarm", "make it louder") have something to ground on.

Splits: ``dev`` while working, ``test`` only at the gates (docs/plano_aprendizado.md, §3).

Usage: python experiments/externo/seguranca.py [dev|test] [pt|en|both] [limit] [-v]
"""
from __future__ import annotations

import collections
import ctypes
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data" / "externo" / "massive" / "1.1" / "data"
LOCALES = {"pt": "pt-PT", "en": "en-US"}

NODES = {
    "pg": ("Página", "page", None, ["s1", "s2", "ft"], None),
    "s1": ("Seção", "section", "pg", ["h", "p", "b", "i"], None),
    "h": ("Título", "heading", "s1", [], "Bem-vindo"),
    "p": ("Parágrafo", "paragraph", "s1", [], "Um texto de apresentação"),
    "b": ("Botão", "button", "s1", [], "Saiba mais"),
    "i": ("Imagem", "image", "s1", [], None),
    "s2": ("Seção 2", "section", "pg", ["h2", "p2", "b2"], None),
    "h2": ("Título 2", "heading", "s2", [], "Serviços"),
    "p2": ("Parágrafo 2", "paragraph", "s2", [], "O que fazemos"),
    "b2": ("Botão 2", "button", "s2", [], "Contato"),
    "ft": ("Rodapé", "footer", "pg", ["p3"], None),
    "p3": ("Parágrafo 3", "paragraph", "ft", [], "Todos os direitos reservados"),
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


def utterances(split: str, lang: str) -> list[dict]:
    path = DATA / f"{LOCALES[lang]}.jsonl"
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [r for r in rows if r["partition"] == split]


def run(split: str, lang: str, limit: int | None, verbose: bool) -> dict:
    from nucleo.lang.interpret import understand_request

    w = world()
    rows = utterances(split, lang)[:limit]
    decisions = collections.Counter()
    wrong_by_intent = collections.Counter()
    wrong = []
    crashes = []
    t = time.time()
    for r in rows:
        try:
            u = understand_request(r["utt"], w, lang=lang)
            d = u.decision
            acted = d == "executar" and bool(u.best and u.best.constraints)
        except Exception as e:  # a crash is recorded, never hidden
            d, acted = f"exceção {type(e).__name__}", False
            crashes.append((r["utt"], repr(e)[:200]))
        decisions[d] += 1
        if acted:
            wrong_by_intent[r["intent"]] += 1
            wrong.append((r["intent"], r["utt"], u.best.constraints))
            if verbose:
                print(f"[ERRADO] ({r['intent']}) {r['utt']}\n    -> {u.best.constraints}")
    secs = time.time() - t
    return {"lang": lang, "split": split, "n": len(rows), "errados": len(wrong),
            "taxa_errados": round(len(wrong) / max(1, len(rows)), 4), "decisoes": dict(decisions),
            "errados_por_intencao": dict(wrong_by_intent.most_common()), "segundos": round(secs, 1),
            "exemplos": [{"intencao": i, "frase": s, "restricoes": c} for i, s, c in wrong[:60]],
            "excecoes_frases": crashes[:30]}


if __name__ == "__main__":
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    split = args[0] if args else "dev"
    langs_ = ["pt", "en"] if len(args) < 2 or args[1] == "both" else [args[1]]
    limit = int(args[2]) if len(args) > 2 else None
    out = {}
    for lang in langs_:
        res = run(split, lang, limit, "-v" in sys.argv)
        out[lang] = res
        print(json.dumps({k: v for k, v in res.items() if k != "exemplos"}, ensure_ascii=False))
    dest = ROOT / "data" / "cache" / f"externo_seguranca_{split}.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("gravado em", dest)
