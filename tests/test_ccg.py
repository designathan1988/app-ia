"""Roteiro CCG: the typed lambda calculus, the combinators and the splitting of meanings (UBL §4)."""
from nucleo.lang.ccg import ccg as C
from nucleo.lang.ccg import logica as L
from nucleo.lang.ccg import ubl

CITY_IN_TEXAS = "(lambda $0:e (and:<t*,t> (city:<c,t> $0) (loc:<lo,<lo,t>> $0 texas:s)))"


def test_parse_type_and_key_roundtrip():
    t = L.parse(CITY_IN_TEXAS)
    assert L.type_str(L.type_of(t)) == "<e,t>"
    assert L.canonical(L.parse(L.canonical(t))) == L.canonical(t)


def test_conjunct_order_does_not_change_the_meaning():
    a = L.parse("(lambda $0:e (and:<t*,t> (city:<c,t> $0) (loc:<lo,<lo,t>> $0 texas:s)))")
    b = L.parse("(lambda $0:e (and:<t*,t> (loc:<lo,<lo,t>> $0 texas:s) (city:<c,t> $0)))")
    assert L.canonical(a) == L.canonical(b)


def test_application_and_composition():
    f = L.parse("(lambda $0:s (lambda $1:e (and:<t*,t> (city:<c,t> $1) (loc:<lo,<lo,t>> $1 $0))))")
    assert L.canonical(L.apply(f, L.Const("texas", "s"))) == L.canonical(L.parse(CITY_IN_TEXAS))
    g = L.parse("(lambda $0:e (city:<c,t> $0))")
    h = L.parse("(lambda $0:<e,t> (lambda $1:e (and:<t*,t> ($0 $1) (loc:<lo,<lo,t>> $1 texas:s))))")
    assert L.canonical(L.apply(h, g)) == L.canonical(L.parse(CITY_IN_TEXAS))


def test_every_split_recombines_to_the_original():
    h = L.parse(CITY_IN_TEXAS)
    splits = ubl.application_splits(h)
    assert splits
    for f, g in splits:
        assert L.canonical(L.apply(f, g)) == L.canonical(h)
    # the constant "texas" can be split off (the lexical item of the word "texas")
    assert any(L.canonical(g) == "texas:s" for _, g in splits)
    for f, g in ubl.composition_splits(h):
        assert L.canonical(L.compose(f, g)) == L.canonical(h)


def test_category_of_type_and_combinators():
    assert C.cat_of_type("t") == "S"
    assert C.cat_str(C.cat_of_type(("e", "t"))) == "(S|NP)"
    f = L.parse("(lambda $0:s (lambda $1:e (loc:<lo,<lo,t>> $1 $0)))")
    a = C.Item((C.FWD, C.cat_of_type(("e", "t")), "NP"), f, 0.0, (0, 1), "lex")
    b = C.Item("NP", L.Const("texas", "s"), 0.0, (1, 2), "lex")
    out = C.combine(a, b)
    assert any(r == ">" and L.canonical(lf) == L.canonical(L.parse(
        "(lambda $0:e (loc:<lo,<lo,t>> $0 texas:s))")) for _, lf, r in out)


def test_factored_lexicon_generalizes_a_lexeme_to_other_templates():
    lex = ubl.Lexicon()
    lex.add_item(("texas",), "NP", L.Const("texas", "s"))
    lex.add_item(("ohio",), "NP", L.Const("ohio", "s"))
    # one template learned with "texas" in another use ...
    lex.add_item(("texas",), (C.BWD, "NP", "NP"), L.parse("(lambda $0:e (loc:<lo,<lo,t>> $0 texas:s))"))
    # ... is available to "ohio" too, through the shared template of its signature
    lid = lex.lexeme_id[(("ohio",), ("ohio:s",))]
    assert len(lex.by_sig[lex.sig(lid)]) >= 1
