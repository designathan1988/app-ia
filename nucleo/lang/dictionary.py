"""A Portuguese dictionary, local: definitions, synonyms and translations of every word (no word lists by hand).

Sources (downloaded once, with the user's permission, into ``data/dicionario/``):
- the Portuguese Wiktionary as extracted by kaikki.org (``pt-extract.jsonl.gz``, CC BY-SA): 600k entries with their
  definitions (glosses), synonyms and English translations;
- OpenWordNet-PT (``own-pt-lmf.xml``, CC BY 4.0): synsets, i.e. words that share a sense.

Why: a word means something to the system only when it reaches what the system can do (an element type, a property,
a value, a command). The few hundred words the builder's own catalog names are reached directly; every other word is
reached **through the dictionary**, the way a person learns a word from its definition (symbol grounding through a
dictionary, Harnad 1990): a synonym that is grounded, an English translation that is a CSS keyword or a command's
English label, or a word of its definition that is grounded ("colorir: dar cor a" -> "cor"). The path is kept, so
the understanding layer can say why it read a word as it did, and each step has a cost (abduction prefers short
paths).

The index is built once into ``data/cache/dicionario.sqlite`` (``python -m nucleo.lang.dictionary``).
"""

from __future__ import annotations

import gzip
import json
import pathlib
import re
import sqlite3
import xml.etree.ElementTree as ET
from functools import lru_cache

from .values import fold

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "dicionario"
DB = ROOT / "data" / "cache" / "dicionario.sqlite"
POS = {"verb": "V", "noun": "N", "adj": "A", "adv": "ADV", "phrase": "LOC", "name": "PROPN"}


def build() -> dict:
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.executescript("""
        CREATE TABLE gloss (word TEXT, pos TEXT, sense INTEGER, text TEXT);
        CREATE TABLE syn (word TEXT, other TEXT, source TEXT);
        CREATE TABLE tr (word TEXT, en TEXT);
    """)
    n = {"verbetes": 0, "definicoes": 0, "sinonimos": 0, "traducoes": 0}
    with gzip.open(SRC / "pt-extract.jsonl.gz", "rt", encoding="utf-8") as f:
        rows_g, rows_s, rows_t = [], [], []
        for line in f:
            d = json.loads(line)
            if d.get("lang_code") != "pt" or not d.get("word"):
                continue
            w = fold(d["word"])
            pos = POS.get(d.get("pos"), d.get("pos"))
            n["verbetes"] += 1
            for i, s in enumerate(d.get("senses") or []):
                if "Gíria" in (s.get("raw_tags") or []):
                    continue
                for g in s.get("glosses") or []:
                    rows_g.append((w, pos, i, g))
                for x in s.get("synonyms") or []:
                    if x.get("word"):
                        rows_s.append((w, fold(x["word"]), "wiktionary"))
                for t in s.get("translations") or []:
                    if t.get("lang_code") == "en" and t.get("word"):
                        rows_t.append((w, t["word"].lower()))
            for x in d.get("synonyms") or []:
                if x.get("word"):
                    rows_s.append((w, fold(x["word"]), "wiktionary"))
            for t in d.get("translations") or []:
                if t.get("lang_code") == "en" and t.get("word"):
                    rows_t.append((w, t["word"].lower()))
        con.executemany("INSERT INTO gloss VALUES (?,?,?,?)", rows_g)
        con.executemany("INSERT INTO syn VALUES (?,?,?)", rows_s)
        con.executemany("INSERT INTO tr VALUES (?,?)", rows_t)
        n["definicoes"], n["traducoes"] = len(rows_g), len(rows_t)
        n["sinonimos"] = len(rows_s)
    # OpenWordNet-PT: words of a synset are synonyms of each other in that sense
    xml = SRC / "own-pt" / "own-pt-lmf.xml"
    if xml.exists():
        members: dict[str, list[str]] = {}
        for _, el in ET.iterparse(xml, events=("end",)):
            if el.tag == "LexicalEntry":
                lemma = el.find("Lemma")
                word = fold(lemma.get("writtenForm")) if lemma is not None else None
                for sense in el.findall("Sense"):
                    if word:
                        members.setdefault(sense.get("synset"), []).append(word)
                el.clear()
        rows = [(a, b, "wordnet") for ws in members.values() if len(ws) <= 12 for a in ws for b in ws if a != b]
        con.executemany("INSERT INTO syn VALUES (?,?,?)", rows)
        n["sinonimos"] += len(rows)
    con.executescript("""
        CREATE INDEX gloss_w ON gloss(word);
        CREATE INDEX syn_w ON syn(word);
        CREATE INDEX tr_w ON tr(word);
        CREATE INDEX tr_en ON tr(en);
    """)
    con.commit()
    con.close()
    return n


@lru_cache(maxsize=1)
def _con():
    if not DB.exists():
        return None
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True, check_same_thread=False)


@lru_cache(maxsize=50_000)
def glosses(word: str, pos: str | None = None) -> tuple[str, ...]:
    """The definitions of a word, in the dictionary's order (the first sense first)."""
    con = _con()
    if con is None:
        return ()
    q = "SELECT text FROM gloss WHERE word = ?" + (" AND pos = ?" if pos else "") + " ORDER BY sense"
    return tuple(r[0] for r in con.execute(q, (fold(word),) + ((pos,) if pos else ())))


@lru_cache(maxsize=50_000)
def synonyms(word: str) -> tuple[str, ...]:
    con = _con()
    if con is None:
        return ()
    rows = con.execute("SELECT DISTINCT other FROM syn WHERE word = ?", (fold(word),)).fetchall()
    return tuple(r[0] for r in rows)


@lru_cache(maxsize=50_000)
def translations(word: str) -> tuple[str, ...]:
    con = _con()
    if con is None:
        return ()
    return tuple(r[0] for r in con.execute("SELECT DISTINCT en FROM tr WHERE word = ?", (fold(word),)))


@lru_cache(maxsize=50_000)
def portuguese_for(en: str) -> tuple[str, ...]:
    """Portuguese words whose translation is this English word ("hide" -> esconder, ocultar)."""
    con = _con()
    if con is None:
        return ()
    return tuple(r[0] for r in con.execute("SELECT DISTINCT word FROM tr WHERE en = ?", (en.lower(),)))


def gloss_words(word: str, pos: str | None = None, senses: int = 2) -> list[str]:
    """The content words of the first definitions of a word, in order."""
    out = []
    for g in glosses(word, pos)[:senses]:
        out += [w for w in re.findall(r"[a-zà-ÿ]+", g.lower()) if len(w) > 2]
    return out


if __name__ == "__main__":
    import sys
    import time

    sys.path.insert(0, str(ROOT))
    from nucleo.session import low_priority

    low_priority()
    t = time.time()
    print(build(), f"{time.time() - t:.0f}s")
