"""Exact Portuguese morphology from MorphoBr (Apache-2.0): every inflected form -> its lemmas and features.

MorphoBr lists ~5 million forms (form, lemma+category+features). They are indexed once into SQLite
(``data/cache/morphobr.sqlite``) and looked up by form. The analyser is exact on what the resource covers, and says
so ("sem análise") on what it does not; it never guesses.
"""

from __future__ import annotations

import pathlib
import sqlite3
from functools import lru_cache

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "morphobr"
DB = ROOT / "data" / "cache" / "morphobr.sqlite"
PARTS = ["nouns", "verbs", "adjectives", "adverbs", "pronouns", "prepositions", "determiners", "conjunctions",
         "numerals", "clitics", "interjections", "contractions"]


def build() -> int:
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE f (form TEXT, lemma TEXT, tags TEXT)")
    n = 0
    for part in PARTS:
        d = SRC / part
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.dict")):
            rows = []
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if "\t" not in line:
                    continue
                form, analysis = line.split("\t", 1)
                lemma, _, tags = analysis.partition("+")
                rows.append((form, lemma, tags))
            con.executemany("INSERT INTO f VALUES (?,?,?)", rows)
            n += len(rows)
    con.execute("CREATE INDEX f_form ON f(form)")
    con.commit()
    con.close()
    return n


@lru_cache(maxsize=1)
def _con():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True, check_same_thread=False)


@lru_cache(maxsize=200_000)
def analyses(form: str) -> tuple[tuple[str, str], ...]:
    """(lemma, tags) for a form, e.g. "insira" -> (("inserir", "V+SBJR+1+SG"), ("inserir", "V+IMP+3+SG"), ...)."""
    rows = _con().execute("SELECT lemma, tags FROM f WHERE form = ?", (form.lower(),)).fetchall()
    return tuple(sorted(set(rows)))


def lemmas(form: str, category: str | None = None) -> list[str]:
    out = []
    for lemma, tags in analyses(form):
        if category is None or tags.split("+")[0] == category:
            if lemma not in out:
                out.append(lemma)
    return out


def gender(noun: str) -> str | None:
    """'M' or 'F' for a noun lemma (or form), None if MorphoBr does not know it or it varies."""
    gs = {t for _, tags in analyses(noun) for t in tags.split("+") if t in ("M", "F") and tags.startswith("N")}
    return gs.pop() if len(gs) == 1 else None


if __name__ == "__main__":
    import time

    t = time.time()
    print(f"{build()} formas indexadas em {time.time() - t:.0f}s")
