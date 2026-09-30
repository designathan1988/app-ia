"""Portuguese names of CSS keyword values, induced from MDN's Portuguese reference pages, not written by hand.

For each property the builder knows, MDN pt-BR lists every keyword value with a description ("right: O conteúdo é
alinhado na borda direita do box"). The words that describe one value of a property and none of its other values
("direita" for right, "esquerda" for left, "negrito" for bold, "centralizados" for center) are that value's
Portuguese names. The induction is statistical over the page, not a list of translations: a word shared by two
values of the same property names neither.

The result (``data/cache/valores_pt.json``) keeps the source URL of every property. A word grounds to one or more
(property, value) pairs; the understanding layer decides which one by abduction (which property applies to the
element, which is essential in the builder's inspector).
"""

from __future__ import annotations

import html
import json
import pathlib
import re
import unicodedata
from functools import lru_cache

CACHE = pathlib.Path(__file__).resolve().parents[2] / "data" / "cache" / "valores_pt.json"
DATA_TYPES = {"length", "percentage", "number", "integer", "string", "url", "uri", "color", "angle", "time",
              "image", "ratio", "flex", "eyword", "ainted", "safe", "unsafe"}
STOP = {"o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas", "que", "e",
        "é", "se", "com", "por", "para", "ao", "à", "igual", "mesmo", "elemento", "valor", "caixa", "box", "conteúdo",
        "conteudos", "conteúdos", "inline", "the", "of", "and", "to", "is", "texto", "linha", "propriedade", "não",
        "como", "mais", "ou", "seu", "sua", "pelo", "pela", "este", "esta", "ele", "ela", "são", "ser", "será", "the"}


def fold(word: str) -> str:
    """Lowercase without accents: "título" and "titulo" are the same word to the matcher."""
    return "".join(c for c in unicodedata.normalize("NFD", word.lower()) if unicodedata.category(c) != "Mn")


def _descriptions(page: str) -> dict[str, str]:
    i = page.find('id="valores"')
    if i < 0:
        return {}
    j = page.find("<dl", i)
    k = page.find("</dl>", j)
    out = {}
    for dt, dd in re.findall(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", page[j:k], re.S):
        text = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", dd))).strip()
        for name in re.findall(r"[a-z][a-z-]*", html.unescape(re.sub(r"<[^>]+>", "", dt))):
            out[name] = text
    return out


def induce(descs: dict[str, str], allowed: set[str]) -> dict[str, list[str]]:
    from .lexicon import lemma_of

    words = {}
    for value, text in descs.items():
        if allowed and value not in allowed:
            continue
        ws = {fold(lemma_of(w)) for w in re.findall(r"[A-Za-zÀ-ÿ]+", text) if fold(w) not in STOP and len(w) > 3}
        words[value] = ws - {fold(value)}
    out = {}
    for value, ws in words.items():
        others = set().union(*(w for v, w in words.items() if v != value)) if len(words) > 1 else set()
        distinct = sorted(ws - others)
        if distinct:
            out[value] = distinct[:4]
    return out


def build(fetcher, root: str | None = None) -> dict:
    from ..builder.knowledge import load_domains

    domains = load_domains(root)
    result: dict = {"_fonte": {}}
    for prop, values in sorted(domains.properties.items()):
        allowed = {str(v) for v in values}  # empty: every keyword the page lists
        url = f"https://developer.mozilla.org/pt-BR/docs/Web/CSS/Reference/Properties/{prop}"
        r = fetcher.get(url)
        if r.status != 200:
            continue
        induced = induce(_descriptions(r.text()), allowed)
        if induced:
            result[prop] = induced
            result["_fonte"][prop] = url
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    index.cache_clear()
    return result


@lru_cache(maxsize=1)
def index() -> dict[str, list[tuple[str, str]]]:
    """folded Portuguese word -> [(property, value)], keeping only specific words: Portuguese (MorphoBr), and rare
    across all value descriptions (a word naming many values of many properties names none of them)."""
    if not CACHE.exists():
        return {}
    data = json.loads(CACHE.read_text(encoding="utf-8"))
    pairs: dict[str, list] = {}
    for prop, vals in data.items():
        if prop.startswith("_"):
            continue
        for value, words in vals.items():
            if len(words) > 3 or value in DATA_TYPES or not re.fullmatch(r"[a-z]+(-[a-z]+)*", value):
                continue  # a data type, not a keyword; or a long description with no specific word
            for w in words:
                pairs.setdefault(w, []).append((prop, value))
    return {w: ps for w, ps in pairs.items() if len({p for p, _ in ps}) <= 3 and len(w) >= 4 and _portuguese_folded(w)}


@lru_cache(maxsize=4096)
def _portuguese_folded(word: str) -> bool:
    from .morph import _con

    rows = _con().execute("SELECT tags FROM f WHERE form = ? LIMIT 20", (word,)).fetchall()
    if not rows:
        # the index is by accented form: try the forms that fold to this word (same length, same first letter)
        cands = _con().execute("SELECT form, tags FROM f WHERE length(form) = ? AND form >= ? AND form < ? LIMIT 4000",
                               (len(word), word[:1], chr(ord(word[:1]) + 1))).fetchall()
        rows = [(t,) for f, t in cands if fold(f) == word]
    tags = {t.split("+")[0] for (t,) in rows}
    # a name of a value is a noun or an adjective, and not also a verb or a function word ("deve", "onde")
    return bool(tags & {"N", "A"}) and not tags & {"PREP", "CONJ", "DET", "PRON"}


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from nucleo.session import low_priority
    from nucleo.web.fetcher import Fetcher

    low_priority()
    res = build(Fetcher(pathlib.Path(__file__).resolve().parents[2] / "data" / "cache" / "web", min_delay=0.5))
    print(len(res) - 1, "propriedades com valores nomeados em português")
