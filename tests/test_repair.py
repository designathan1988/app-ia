"""M7: fix templates repair a faulty expression, and a repair is judged on inputs it never saw."""

from __future__ import annotations

from nucleo.repair.templates import passes, repair

TRAIN = [((3, 4), 7), ((10, 1), 11), ((0, 0), 0), ((-2, 5), 3), ((7, 7), 14), ((1, 9), 10)]
HELD = [((a, b), a + b) for a in range(-5, 6) for b in range(-5, 6)]


def test_operator_bug_is_repaired_and_generalises():
    r = repair(["a", "b"], "a - b", TRAIN)
    assert r.source == "a + b" and passes(["a", "b"], r.source, HELD)


def test_off_by_one_constant():
    train = [((s,), s[: 3]) for s in ["abcdef", "xy", "hello", "", "1234"]]
    r = repair(["s"], "s[:2]", train)
    assert r.source == "s[:3]"


def test_nothing_is_proposed_when_no_small_edit_explains_the_tests():
    train = [((s,), s[::-1].upper()) for s in ["abc", "Hello", "xy"]]
    assert repair(["s"], "s.lower()", train, max_edits=1).source is None
