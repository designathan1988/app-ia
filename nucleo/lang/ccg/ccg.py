"""CCG categories, the universal combinators, and a CKY parser over a factored lexicon (Steedman 2000; Kwiatkowski
et al. 2010, 2011).

- A category is ``"S"``, ``"NP"`` or ``(slash, result, argument)`` with slash ``/`` (argument to the right), ``\\``
  (to the left) or ``|`` (either side: the vertical slash of UBL).
- ``cat_of_type`` is UBL's C(T): e-like types -> NP, t -> S, <T1,T2> -> C(T2)|C(T1).
- Combinators: forward/backward application and forward/backward composition. Nothing in this file depends on a
  language or a domain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from . import logica as L

FWD, BWD, ANY = "/", "\\", "|"


def cat_of_type(ty):
    if ty == L.T:
        return "S"
    if L.is_fn(ty):
        if ty[0] == "*":
            return (ANY, cat_of_type(ty[2]), cat_of_type(ty[1]))
        return (ANY, cat_of_type(ty[1]), cat_of_type(ty[0]))
    return "NP"


@lru_cache(maxsize=None)
def cat_str(c) -> str:
    if isinstance(c, str):
        return c
    s, r, a = c
    return f"({cat_str(r)}{s}{cat_str(a)})"


def slashes(c) -> int:
    return 0 if isinstance(c, str) else 1 + slashes(c[1]) + slashes(c[2])


def match(a, b) -> bool:
    """Category equality where the vertical slash matches any direction."""
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    if a[0] != b[0] and ANY not in (a[0], b[0]):
        return False
    return match(a[1], b[1]) and match(a[2], b[2])


def takes_right(c) -> bool:
    return not isinstance(c, str) and c[0] in (FWD, ANY)


def takes_left(c) -> bool:
    return not isinstance(c, str) and c[0] in (BWD, ANY)


@dataclass
class Item:
    cat: object
    lf: object
    score: float
    span: tuple  # (i, j)
    rule: str  # "lex" | ">" | "<" | ">B" | "<B" | "skip"
    kids: tuple = ()
    lexeme: object = None  # for lexical items: (lexeme id, template id)
    lkey: str = ""
    consts: tuple = ()  # constants of the logical form (for constrained parsing)

    def ident(self) -> tuple:
        return (cat_str(self.cat), self.lkey)


_MEMO: dict = {}


def combine_memo(a: Item, b: Item) -> list:
    """``combine`` remembered by the two items' categories and meanings: the same pairs recur across sentences
    and epochs. Returns (category, logical form, rule, key, constants)."""
    k = (cat_str(a.cat), a.lkey, cat_str(b.cat), b.lkey)
    got = _MEMO.get(k)
    if got is None:
        got = [(cat, lf, rule, L.key(lf), tuple(L.const_str(c) for c in L.constants(lf)))
               for cat, lf, rule in combine(a, b)]
        if len(_MEMO) > 3_000_000:
            _MEMO.clear()
        _MEMO[k] = got
    return got


def combine(a: Item, b: Item):
    """All items made by the combinators from a (left) and b (right)."""
    out = []
    if takes_right(a.cat) and match(a.cat[2], b.cat):
        lf = L.apply(a.lf, b.lf)
        if lf is not None and L.type_of(lf) is not None:
            out.append((a.cat[1], lf, ">"))
    if takes_left(b.cat) and match(b.cat[2], a.cat):
        lf = L.apply(b.lf, a.lf)
        if lf is not None and L.type_of(lf) is not None:
            out.append((b.cat[1], lf, "<"))
    if takes_right(a.cat) and takes_right(b.cat) and match(a.cat[2], b.cat[1]) and b.cat[0] != BWD:
        lf = L.compose(a.lf, b.lf)
        if lf is not None and L.type_of(lf) is not None:
            out.append(((b.cat[0], a.cat[1], b.cat[2]), lf, ">B"))
    if takes_left(a.cat) and takes_left(b.cat) and match(b.cat[2], a.cat[1]) and a.cat[0] != FWD:
        lf = L.compose(b.lf, a.lf)
        if lf is not None and L.type_of(lf) is not None:
            out.append(((a.cat[0], b.cat[1], a.cat[2]), lf, "<B"))
    return out


def multiset_le(small: tuple, big: dict) -> bool:
    need: dict = {}
    for c in small:
        need[c] = need.get(c, 0) + 1
        if need[c] > big.get(c, 0):
            return False
    return True


@dataclass
class Chart:
    n: int
    cells: dict = field(default_factory=dict)  # (i, j) -> {ident: Item}

    def add(self, it: Item) -> None:
        cell = self.cells.setdefault(it.span, {})
        k = it.ident()
        old = cell.get(k)
        if old is None or it.score > old.score:
            cell[k] = it

    def items(self, i, j) -> list:
        return list(self.cells.get((i, j), {}).values())

    def prune(self, i, j, beam: int) -> None:
        cell = self.cells.get((i, j))
        if cell and len(cell) > beam:
            keep = sorted(cell.values(), key=lambda x: -x.score)[:beam]
            self.cells[(i, j)] = {x.ident(): x for x in keep}


def parse(n: int, lexical, beam: int = 50, allowed: dict | None = None, rule_score=None) -> Chart:
    """CKY: ``lexical(i, j)`` gives the lexical items of words[i:j]; spans are filled bottom-up; each cell keeps its
    ``beam`` best items. With ``allowed`` (a multiset of constants), items whose constants exceed it are dropped:
    the constrained parse used to find the best correct derivation during learning."""
    ch = Chart(n)
    for length in range(1, n + 1):
        for i in range(0, n - length + 1):
            j = i + length
            for it in lexical(i, j):
                if allowed is None or multiset_le(it.consts, allowed):
                    ch.add(it)
            for k in range(i + 1, j):
                left, right = ch.items(i, k), ch.items(k, j)
                if not left or not right:
                    continue
                for a in left:
                    for b in right:
                        for cat, lf, rule, lk, consts in combine_memo(a, b):
                            if allowed is not None and not multiset_le(consts, allowed):
                                continue
                            sc = a.score + b.score + (rule_score(rule) if rule_score else 0.0)
                            ch.add(Item(cat, lf, sc, (i, j), rule, (a, b), None, lk, consts))
            ch.prune(i, j, beam)
    return ch


def leaves(it: Item) -> list:
    if not it.kids:
        return [it]
    return [x for k in it.kids for x in leaves(k)]


def nodes(it: Item) -> list:
    return [it] + [x for k in it.kids for x in nodes(k)]
