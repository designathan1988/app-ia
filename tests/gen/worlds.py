"""Random program generator for differential testing.

Rules:

* It produces **programs only**. It never computes an answer; answers come from
  the oracles. A lint test forbids importing ``nucleo.logic`` or
  ``nucleo.check`` here.
* Names (predicates and constants) are invented pseudo-words, new for every
  seed, so nothing in the engine can depend on a particular vocabulary.
* By construction it respects the admission rules:
  - safety;
  - ``not`` only over closed predicates, ``nao_consta`` over any predicate;
  - closed predicates depend only on closed predicates;
  - negation only towards strictly lower levels (stratified).

It also exercises recursion (same-level positive dependencies), strong
negation (facts and rules deriving ``-p``), injected contradictions,
comparisons and 0-ary predicates.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

_ONSETS = ["b", "br", "d", "f", "g", "gl", "j", "k", "l", "m", "n", "p", "pl", "r", "s", "t", "tr", "v", "z", "x"]
_VOWELS = ["a", "e", "i", "o", "u", "ai", "ou", "ei"]


def pseudo_word(rng: random.Random, syllables: int | None = None) -> str:
    n = syllables or rng.randint(2, 3)
    return "".join(rng.choice(_ONSETS) + rng.choice(_VOWELS) for _ in range(n))


@dataclass
class _Pred:
    name: str
    arity: int
    level: int
    closed: bool


def random_program(seed: int, *, n_preds: int | None = None, n_consts: int | None = None,
                   n_rules: int | None = None, n_facts: int | None = None) -> str:
    rng = random.Random(seed)
    used: set[str] = set()

    def fresh() -> str:
        while True:
            w = pseudo_word(rng)
            if w not in used and w not in ("not", "pred", "fechado", "aberto", "nao_consta"):
                used.add(w)
                return w

    n_preds = n_preds or rng.randint(3, 7)
    n_consts = n_consts or rng.randint(2, 4)
    consts: list[str] = [fresh() for _ in range(n_consts)]
    if rng.random() < 0.5:
        consts += [str(rng.randint(0, 9)) for _ in range(rng.randint(1, 2))]
    consts = sorted(set(consts))

    preds: list[_Pred] = []
    for _ in range(n_preds):
        preds.append(_Pred(fresh(), rng.choice([0, 1, 1, 2, 2, 2, 3]), rng.randint(0, 3), rng.random() < 0.45))
    closed = [p for p in preds if p.closed]

    lines: list[str] = []
    for p in preds:
        lines.append(f"pred {p.name}/{p.arity} {'fechado' if p.closed else 'aberto'}.")

    def ground_args(arity: int) -> str:
        return "" if arity == 0 else "(" + ", ".join(rng.choice(consts) for _ in range(arity)) + ")"

    # facts, including some strong-negation facts (possibly contradicting positives)
    n_facts = n_facts or rng.randint(6, 22)
    positive_facts = []
    for _ in range(n_facts):
        p = rng.choice(preds)
        fact = f"{p.name}{ground_args(p.arity)}"
        positive_facts.append(fact)
        lines.append(f"{fact}.")
    for _ in range(rng.randint(0, 3)):
        if positive_facts and rng.random() < 0.4:
            lines.append(f"-{rng.choice(positive_facts)}.")  # injected contradiction
        else:
            p = rng.choice(preds)
            lines.append(f"-{p.name}{ground_args(p.arity)}.")

    var_names = ["X", "Y", "Z", "W", "V"]
    n_rules = n_rules or rng.randint(3, 9)
    for _ in range(n_rules):
        head = rng.choice(preds)
        pool = [q for q in preds if q.level <= head.level]
        if head.closed:
            pool = [q for q in pool if q.closed]
        if not pool:
            continue
        body: list[str] = []
        bound: list[str] = []
        for _ in range(rng.choice([1, 1, 2, 2, 3])):
            q = rng.choice(pool)
            args = []
            for _ in range(q.arity):
                if bound and rng.random() < 0.5:
                    args.append(rng.choice(bound))
                elif rng.random() < 0.8:
                    v = rng.choice(var_names)
                    args.append(v)
                    if v not in bound:
                        bound.append(v)
                else:
                    args.append(rng.choice(consts))
            sign = "-" if rng.random() < 0.12 else ""
            body.append(f"{sign}{q.name}" + (f"({', '.join(args)})" if args else ""))
        # negation towards strictly lower levels
        lower = [q for q in preds if q.level < head.level]
        if lower and rng.random() < 0.5:
            q = rng.choice(lower)
            if head.closed:
                cands = [c for c in lower if c.closed]
                q = rng.choice(cands) if cands else None
            if q is not None:
                args = [rng.choice(bound) if bound and rng.random() < 0.8 else rng.choice(consts)
                        for _ in range(q.arity)]
                atom = q.name + (f"({', '.join(args)})" if args else "")
                if q.closed and (head.closed or rng.random() < 0.6):
                    body.append(f"not {atom}")
                elif not head.closed:
                    body.append(f"nao_consta({atom})")
        if bound and rng.random() < 0.3:
            a = rng.choice(bound)
            b = rng.choice(bound + consts)
            body.append(f"{a} {rng.choice(['=', '!=', '<', '<=', '>', '>='])} {b}")
        head_args = [rng.choice(bound) if bound and rng.random() < 0.85 else rng.choice(consts)
                     for _ in range(head.arity)]
        hsign = "-" if rng.random() < 0.15 else ""
        head_atom = f"{hsign}{head.name}" + (f"({', '.join(head_args)})" if head_args else "")
        lines.append(f"{head_atom} :- {', '.join(body)}.")

    rng.shuffle(lines)
    return "\n".join(lines) + "\n"
