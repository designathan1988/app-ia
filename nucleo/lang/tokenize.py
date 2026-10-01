"""Tokenization for requests: words, punctuation, protected literals, and contractions split the treebank way.

What is between quotes, a CSS-like value (#ff0000, 56px, 1.5rem, rgb(0 0 0), 50%), and a number are kept whole as
literals, so the parser sees one token and the meaning layer gets the value verbatim. Contractions ("na", "do",
"pelo") are split into the syntactic words the UD treebanks use, from the table learned from them.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache

from .syntax import MODELS

_TOKEN = re.compile(
    r'"[^"]*"|“[^”]*”|\'[^\']*\'|'  # quoted literals
    r"#[0-9a-fA-F]{3,8}\b|"  # hex colours
    r"\b[a-zA-Z][\w-]*\((?:[^()]|\([^()]*\))*\)|"  # CSS functions, one nesting level: blur(4px), calc(1px + var(--x))
    r"-?\d+(?:[.,]\d+)?(?:%|(?:px|rem|em|vh|vw|s|ms|fr|deg)?\b)|"  # numbers and lengths ("%" has no word end)
    r"[\wÀ-ÿ]+(?:['’][\wÀ-ÿ]+)?(?:-[\wÀ-ÿ]+)*|"  # words (hyphenated kept whole: padding-top; "i'd" until split)
    r"[^\s\w]"  # punctuation
)


def contractions() -> dict[str, tuple[str, ...]]:
    from . import langs

    return _contractions(langs.current())


@lru_cache(maxsize=4)
def treebank_contractions(lang: str) -> dict[str, tuple[str, ...]]:
    """The contractions of the language as the UD treebanks write them (multiword tokens), and nothing else."""
    from .syntax import models_dir

    path = models_dir(lang) / "contractions.json"
    table = {k: tuple(v) for k, v in json.loads(path.read_text(encoding="utf-8")).items()} if path.exists() else {}
    if lang == "en":
        table = {k: v for k, v in table.items() if "'" in k or "’" in k}
    return table


def tokenize_data(text: str, lang: str) -> list[str]:
    """``tokenize`` with the treebank's contractions only (no hand-written informal forms): used by A1."""
    out = []
    table = treebank_contractions(lang)
    for m in _TOKEN.finditer(text):
        tok = m.group(0)
        low = tok.lower()
        if lang == "en" and not is_literal(tok) and len(tok) > 2 and low[-2:] in ("'s", "’s") and low not in table:
            out += [tok[:-2], tok[-2:]]
            continue
        if not is_literal(tok) and low in table:
            parts = table[low]
            first = parts[0].capitalize() if tok[:1].isupper() else parts[0]
            out += [first, *parts[1:]]
        else:
            out.append(tok)
    return out


@lru_cache(maxsize=4)
def _contractions(lang: str) -> dict[str, tuple[str, ...]]:
    from .syntax import models_dir

    path = models_dir(lang) / "contractions.json"
    table = {k: tuple(v) for k, v in json.loads(path.read_text(encoding="utf-8")).items()} if path.exists() else {}
    if lang == "en":
        # an English contraction is written with an apostrophe ("don't", "it's"); the treebank's other multiword
        # tokens are typos joined in the source text ("others" = "other s"), not contractions
        table = {k: v for k, v in table.items() if "'" in k or "’" in k}
    from . import langs

    for k, v in langs.profile(lang).get("informal", {}).items():  # spoken contractions the news treebanks lack
        table.setdefault(k, tuple(v))
    return table


def is_literal(tok: str) -> bool:
    return bool(re.fullmatch(r'"[^"]*"|“[^”]*”|\'[^\']*\'|#[0-9a-fA-F]{3,8}|[a-zA-Z][\w-]*\((?:[^()]|\([^()]*\))*\)'
                             r'|-?\d+(?:[.,]\d+)?\w*%?', tok))


def literal_value(tok: str) -> str:
    if tok[:1] in "\"'“" and len(tok) >= 2:
        return tok[1:-1]
    return tok


def tokenize(text: str) -> list[str]:
    from . import langs

    out = []
    lang = langs.current()
    table = contractions()
    for m in _TOKEN.finditer(text):
        tok = m.group(0)
        low = tok.lower()
        if lang == "en" and not is_literal(tok) and len(tok) > 2 and low[-2:] in ("'s", "’s") and low not in table:
            out += [tok[:-2], tok[-2:]]
            continue
        if not is_literal(tok) and low in table:
            parts = table[low]
            # keep the capitalisation of the first letter ("Na" -> "Em a")
            first = parts[0].capitalize() if tok[:1].isupper() else parts[0]
            out += [first, *parts[1:]]
        else:
            out.append(tok)
    return out
