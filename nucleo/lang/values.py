"""Portuguese names of CSS keyword values, from independent sources, none written by hand.

A CSS keyword is an English word ("right", "bold", "italic", "red"). Its Portuguese names come from:

1. **Translation.** The Portuguese adjectives and nouns Wiktionary lists as translations of the keyword as an English
   word ("italic" -> "itálico", "red" -> "vermelho"). Only the first verb it gives is used, through its participle
   ("justify" -> "justificar" -> "justificado"): later verbs translate other senses of the English word.
2. **Description.** MDN's pt-BR reference describes every keyword of a property ("right: O conteúdo é alinhado na
   borda direita"). A word that describes one value and none of the property's other values, in a short
   description, names it ("direita", "centralizado").
3. **The builder's catalog.** Its pt-BR labels for values ("value.font-weight.700": "Negrito 700").
4. **The keyword itself** ("flex", "bold"), which users also type.

Which keywords a property takes is read from the W3C definitions (@webref/css), which also list the named colors.
A word that names many keywords names none of them, and a word that heads a property's label names the property;
both are dropped. A color name applies to every
color property, and the understanding layer chooses among them by abduction (which property applies to the element,
which is essential in the builder's inspector). The sources are kept in ``data/cache/``.
"""

from __future__ import annotations

import html
import json
import pathlib
import re
import unicodedata
from functools import lru_cache

ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "cache" / "valores_pt.json"
TRANSLATIONS = ROOT / "data" / "cache" / "traducoes_css.json"
MAX_KEYWORDS = 2  # a word naming more keywords than this ("bloco": block, and resma, quadra...) names none
STOP = {"o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas", "que", "e",
        "é", "se", "com", "por", "para", "ao", "à", "igual", "mesmo", "elemento", "valor", "caixa", "box", "conteúdo",
        "conteudos", "conteúdos", "inline", "the", "of", "and", "to", "is", "texto", "linha", "propriedade", "não",
        "como", "mais", "ou", "seu", "sua", "pelo", "pela", "este", "esta", "ele", "ela", "são", "ser", "será", "the"}
GLOBAL = {"inherit", "initial", "unset", "revert", "revert-layer", "auto", "none", "normal"}


def fold(word: str) -> str:
    """Lowercase without accents: "título" and "titulo" are the same word to the matcher."""
    return "".join(c for c in unicodedata.normalize("NFD", word.lower()) if unicodedata.category(c) != "Mn")


# -- W3C definitions --------------------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _css() -> dict:
    from ..builder.client import DEFAULT_BUILDER

    path = pathlib.Path(DEFAULT_BUILDER) / "node_modules" / "@webref" / "css" / "css.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _syntax_keywords(syntax: str) -> set[str]:
    return set(re.findall(r"(?<![\w-])[a-z]+(?:-[a-z]+)*(?![\w(-])", re.sub(r"<[^>]*>", " ", syntax)))


OPEN = "<ident>"  # marks a grammar that also takes free identifiers (<custom-ident>): any keyword-like word fits


@lru_cache(maxsize=1)
def _all_keywords() -> dict[str, set[str]]:
    """property -> the keywords its value grammar allows, following the named types (<font-weight-absolute> has
    "bold") and the properties (<'mix-blend-mode'>) it refers to."""
    types = {t["name"]: t.get("syntax") or t.get("value") or "" for t in _css().get("types", [])}
    props: dict[str, str] = {}
    for p in _css().get("properties", []):
        props[p["name"]] = (props.get(p["name"], "") + " | " + (p.get("syntax") or p.get("value") or "")).strip(" |")

    def expand(syntax: str, depth: int) -> set[str]:
        words = _syntax_keywords(syntax)
        if "custom-ident" in syntax:
            words.add(OPEN)
        if depth < 4:
            for ref in re.findall(r"<([a-z-]+)(?:\s[^>]*)?>", syntax):
                if ref in types and ref not in ("named-color", "system-color", "color", "color-base"):
                    words |= expand(types[ref], depth + 1)
            for ref in re.findall(r"<'([a-z-]+)'>", syntax):
                words |= expand(props.get(ref, ""), depth + 1)
        return words

    return {name: expand(syntax, 0) for name, syntax in props.items()}


def _keywords(prop: str) -> set[str]:
    return _all_keywords().get(prop, set())


@lru_cache(maxsize=1)
def named_colors() -> set[str]:
    t = next((t for t in _css().get("types", []) if t["name"] == "named-color"), None)
    return _syntax_keywords(t.get("syntax") or t.get("value") or "") if t else set()


@lru_cache(maxsize=1)
def _builder_properties() -> dict[str, dict]:
    from ..builder.client import DEFAULT_BUILDER

    path = pathlib.Path(DEFAULT_BUILDER) / "manifest" / "properties.json"
    return {p["id"]: p for p in json.loads(path.read_text(encoding="utf-8"))["properties"]}


def color_properties() -> list[str]:
    return [pid for pid, p in _builder_properties().items() if p.get("valueType") == "color"]


# -- source 1: translation (Wiktionary) -------------------------------------------------------------------------
def _pt_translations(wikitext: str) -> list[str]:
    english = wikitext.split("==English==", 1)[-1]
    english = re.split(r"\n==[^=]", english)[0]
    return [w.strip() for w in re.findall(r"\{\{tt?\+?\|pt\|([^|}]+)", english)]


def _translate(fetcher, word: str) -> list[str]:
    url = f"https://en.wiktionary.org/w/index.php?title={word}&action=raw"
    r = fetcher.get(url)
    if r.status not in (200, 404):
        r = fetcher.get(url)  # a transient refusal (429, timeout): once more, after the fetcher's delay
    if r.status != 200:
        return []
    text = r.text()
    out = _pt_translations(text)
    if "translation subpage" in text:  # long entries keep their translations on "<word>/translations"
        sub = fetcher.get(f"https://en.wiktionary.org/w/index.php?title={word}/translations&action=raw")
        if sub.status == 200:
            out += _pt_translations(sub.text())
    return [w for w in dict.fromkeys(out) if re.fullmatch(r"[a-zà-ÿ]+", w)]


# -- source 2: description (MDN pt-BR) --------------------------------------------------------------------------
START = ("valores", "values", "sintaxe", "syntax")
END = ("sintaxe_formal", "formal_syntax", "definição_formal", "formal_definition", "exemplos", "examples",
       "especificações", "specifications", "acessibilidade", "accessibility_concerns")


def _descriptions(page: str) -> dict[str, str]:
    """keyword -> its description, from every definition list between the page's syntax (or values) heading and its
    formal syntax (or examples). The pt-BR pages do not all use the same section ids."""
    heads = [(m.start(), m.group(1)) for m in re.finditer(r'<h[23][^>]*\bid="([^"]+)"', page)]
    start = next((i for i, h in heads if h in START), None)
    if start is None:
        return {}
    end = next((i for i, h in heads if i > start and h in END), len(page))
    out = {}
    for dt, dd in re.findall(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", page[start:end], re.S):
        text = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", dd))).strip()
        for name in re.findall(r"[a-z][a-z-]*", html.unescape(re.sub(r"<[^>]+>", "", dt))):
            out[name] = text
    return out


def _words(text: str) -> set[str]:
    from .lexicon import lemma_of

    return {fold(lemma_of(w)) for w in re.findall(r"[A-Za-zÀ-ÿ]+", text) if fold(w) not in STOP and len(w) > 3}


def induce(descs: dict[str, str], allowed: set[str]) -> dict[str, list[str]]:
    """value -> the words of its description that no other value's description of the property has."""
    words = {v: _words(t) - {fold(v)} for v, t in descs.items() if not allowed or v in allowed}
    out = {}
    for value, ws in words.items():
        others = set().union(*(w for v, w in words.items() if v != value)) if len(words) > 1 else set()
        distinct = sorted(ws - others)
        if distinct:
            out[value] = distinct
    return out


# -- building the caches ----------------------------------------------------------------------------------------
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

    keywords = set()
    for prop in _builder_properties():
        keywords |= _keywords(prop)
    keywords = {k for k in keywords - GLOBAL if "-" not in k} | named_colors()
    from .command_verbs import english_verbs

    keywords |= english_verbs(root)  # the verbs of the builder's English command labels ("hide", "duplicate")
    translations = {"_fonte": "https://en.wiktionary.org (traduções para o português)"}
    for k in sorted(keywords):
        found = _translate(fetcher, k)
        if found:
            translations[k] = found
    TRANSLATIONS.write_text(json.dumps(translations, ensure_ascii=False, indent=1), encoding="utf-8")
    for f in (index, color_names):
        f.cache_clear()
    return result


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _pos(word: str) -> set[str]:
    from .morph import analyses

    return {t.split("+")[0] for _, t in analyses(word)} | {"INF" for _, t in analyses(word) if t.startswith("V+INF")}


# -- the lexicon ------------------------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def color_names() -> dict[str, str]:
    """folded Portuguese color word -> named color ("vermelho" -> "red"). A word several colors translate to names
    the one that lists it first ("azul" is blue's first translation, azure's third)."""
    from .lexicon import lemma_of

    best: dict[str, tuple] = {}
    trans = _load(TRANSLATIONS)
    for color in named_colors():
        for rank, w in enumerate(trans.get(color, [])):
            if {"A", "N"} & _pos(w) and "INF" not in _pos(w):
                key = fold(lemma_of(w))
                cand = (rank, len(color), color)
                if key not in best or cand < best[key]:
                    best[key] = cand
    return {w: c[2] for w, c in best.items() if c[0] <= 1}  # a primary translation, not a figurative sense


@lru_cache(maxsize=1)
def index() -> dict[str, list[tuple[str, str]]]:
    """folded Portuguese word -> [(property, value)]."""
    from .lexicon import lemma_of

    props = _builder_properties()
    pairs: dict[str, set] = {}
    # a word that heads a property's label names the property, not a value ("tamanho", "fonte", "cor", "fundo")
    heads = {e.lemmas[0] for e in _lexicon_entries() if e.kind == "propriedade" and e.lemmas}

    def add(word: str, prop: str, value: str, translated: bool = False) -> None:
        # a translated word that heads a property's label names that property; a word MDN uses to describe the
        # value ("direita" for text-align: right, though "Direita" also labels the property right) is kept
        if prop in props and value in _keywords(prop) and not (translated and word in heads):
            pairs.setdefault(word, set()).add((prop, value))

    trans = _load(TRANSLATIONS)
    for prop in props:
        for value in _keywords(prop) - GLOBAL:
            add(fold(value), prop, value)  # the keyword as users type it
            first_verb = True
            for w in trans.get(value, []):
                if {"A", "N"} & _pos(w) and "INF" not in _pos(w):
                    add(fold(lemma_of(w)), prop, value, translated=True)
                elif first_verb and "INF" in _pos(w):
                    # the first verb the dictionary gives ("justify" -> "justificar", "underline" -> "sublinhar"):
                    # its participle names the value ("justificado", "sublinhado"); later verbs translate other
                    # senses of the English word
                    first_verb = False
                    part = _participle(w)
                    if part:
                        add(fold(part), prop, value, translated=True)
    for prop, vals in _load(CACHE).items():
        if prop.startswith("_"):
            continue
        for value, words in vals.items():
            if len(words) <= 3:  # a short description: its distinctive words name the value
                for w in words:
                    if _portuguese_folded(w):
                        add(w, prop, value)
    out = {w: sorted(ps) for w, ps in pairs.items() if len({v for _, v in ps}) <= MAX_KEYWORDS and len(w) >= 4}
    for (prop, value), words in _catalog_values().items():
        for w in words:
            if not any(p == prop for p, _ in out.get(w, [])):
                out.setdefault(w, []).append((prop, value))
    for w, color in color_names().items():  # a color names a value of every color property
        if w not in heads:
            out[w] = [(p, color) for p in color_properties()]
    return out


def _participle(verb: str) -> str | None:
    """The masculine singular participle of a verb, checked in MorphoBr ("justificar" -> "justificado")."""
    from .morph import analyses

    stem, ending = verb[:-2], verb[-2:]
    for form in ({"ar": [stem + "ado"], "er": [stem + "ido"], "ir": [stem + "ido"]}.get(ending, [])):
        if any(lem == verb and tags.startswith("V+PTPST+M+SG") for lem, tags in analyses(form)):
            return form
    return None


def _lexicon_entries():
    from .lexicon import load

    return load()


def translate(word: str, prop: str) -> str | None:
    """The CSS keyword a Portuguese word names for this property ("azul" for background-color -> "blue")."""
    from .lexicon import lemma_of

    w = fold(lemma_of(word))
    for p, value in index().get(w, []):
        if p == prop:
            return value
    return None


def _catalog_values() -> dict[tuple[str, str], list[str]]:
    """(property, value) -> the word of its one-word label in the builder's pt-BR catalog ("value.font-weight.700")."""
    from ..builder.client import DEFAULT_BUILDER
    from .lexicon import lemma_of

    path = pathlib.Path(DEFAULT_BUILDER) / "src" / "i18n" / "locales" / "pt-BR.json"
    if not path.exists():
        return {}
    out = {}
    for key, label in json.loads(path.read_text(encoding="utf-8")).items():
        parts = key.split(".")
        if len(parts) != 3 or parts[0] != "value":
            continue
        words = [fold(lemma_of(w)) for w in re.findall(r"[A-Za-zÀ-ÿ]+", label) if len(w) >= 4]
        if len(words) == 1:  # "Extra leve", "Altura da tela" name nothing with one word
            out[(parts[1], parts[2])] = words
    return out


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
    # a value names a quality: its name is an adjective or a noun, and not also a function word ("onde")
    return bool(tags & {"N", "A"}) and not tags & {"PREP", "CONJ", "DET", "PRON"}


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(ROOT))
    from nucleo.session import low_priority
    from nucleo.web.fetcher import Fetcher

    low_priority()
    res = build(Fetcher(ROOT / "data" / "cache" / "web", min_delay=0.5))
    print(len(res) - 1, "propriedades com valores descritos em português;",
          len(_load(TRANSLATIONS)) - 1, "palavras-chave com tradução")
