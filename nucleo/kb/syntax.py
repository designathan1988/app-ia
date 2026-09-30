"""The knowledge language: terms, atoms, literals, rules, programs, and its parser.

This is a *formal* language (like Prolog/Datalog), not natural language. Parsing
it with a hand-written tokenizer is ordinary compiler work.

Surface syntax::

    % comment until end of line
    pred pai/2 fechado.            % predicate declaration: closed world
    pred mora/2 aberto.            % open world (the default)
    pai(ana, bia).                 % fact
    -mora(ana, rio).               % strong negation: "it is known that NOT mora(ana, rio)"
    avo(X, Z) :- pai(X, Y), pai(Y, Z).
    orfao(X) :- pessoa(X), not tem_pai(X).        % negation as failure: only over CLOSED predicates
    talvez(X) :- pessoa(X), nao_consta(mora(X, rio)).  % absence over OPEN predicates -> PRESUMIDO
    maior(X, Y) :- idade(X, A), idade(Y, B), A > B.

Terms: variables start with an uppercase letter or ``_``; symbols start with a
lowercase letter; integers; double-quoted strings.

This module is part of the checker's trusted base, so it deliberately contains no
evaluation logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Union

# ---------------------------------------------------------------------------
# Terms
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Var:
    name: str

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class Sym:
    """A symbolic constant (lowercase identifier)."""

    name: str

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class Text:
    """A quoted string constant."""

    value: str

    def __str__(self) -> str:
        escaped = self.value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'


Const = Union[int, Sym, Text]
Term = Union[Var, int, Sym, Text]


def is_var(term: Term) -> bool:
    return isinstance(term, Var)


def term_str(term: Term) -> str:
    return str(term)


# ---------------------------------------------------------------------------
# Predicates, atoms, literals
# ---------------------------------------------------------------------------


@dataclass(frozen=True, order=True)
class PredKey:
    """A predicate identity. ``neg`` marks the strong-negation relation ``-name``."""

    name: str
    arity: int
    neg: bool = False

    @property
    def base(self) -> tuple[str, int]:
        return (self.name, self.arity)

    def negated(self) -> "PredKey":
        return PredKey(self.name, self.arity, not self.neg)

    def __str__(self) -> str:
        return f"{'-' if self.neg else ''}{self.name}/{self.arity}"


@dataclass(frozen=True)
class Atom:
    pred: PredKey
    args: tuple

    def is_ground(self) -> bool:
        return not any(isinstance(a, Var) for a in self.args)

    def vars(self) -> set[Var]:
        return {a for a in self.args if isinstance(a, Var)}

    def __str__(self) -> str:
        sign = "-" if self.pred.neg else ""
        if not self.args:
            return f"{sign}{self.pred.name}"
        return f"{sign}{self.pred.name}({', '.join(term_str(a) for a in self.args)})"


@dataclass(frozen=True)
class Pos:
    """A positive body literal (the atom may be a strong-negation atom)."""

    atom: Atom

    def __str__(self) -> str:
        return str(self.atom)


@dataclass(frozen=True)
class Naf:
    """Negation as failure: ``not q(...)``. Only allowed over closed-world predicates."""

    atom: Atom

    def __str__(self) -> str:
        return f"not {self.atom}"


@dataclass(frozen=True)
class NaoConsta:
    """Explicit absence over any predicate: ``nao_consta(q(...))``. Conclusions become PRESUMIDO."""

    atom: Atom

    def __str__(self) -> str:
        return f"nao_consta({self.atom})"


CMP_OPS = ("=", "!=", "<", "<=", ">", ">=")


@dataclass(frozen=True)
class Cmp:
    op: str
    left: Term
    right: Term

    def vars(self) -> set[Var]:
        return {t for t in (self.left, self.right) if isinstance(t, Var)}

    def __str__(self) -> str:
        return f"{term_str(self.left)} {self.op} {term_str(self.right)}"


Literal = Union[Pos, Naf, NaoConsta, Cmp]


def literal_vars(lit: Literal) -> set[Var]:
    if isinstance(lit, Cmp):
        return lit.vars()
    return lit.atom.vars()


@dataclass(frozen=True)
class Rule:
    id: int
    head: Atom
    body: tuple

    def __str__(self) -> str:
        return f"{self.head} :- {', '.join(str(b) for b in self.body)}."


@dataclass
class Program:
    facts: list[Atom] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    # world per base predicate (name, arity): "fechado" | "aberto"
    worlds: dict[tuple[str, int], str] = field(default_factory=dict)
    default_world: str = "aberto"

    def world(self, pred: PredKey) -> str:
        return self.worlds.get(pred.base, self.default_world)

    def is_closed(self, pred: PredKey) -> bool:
        return self.world(pred) == "fechado"

    def predicates(self) -> set[PredKey]:
        preds: set[PredKey] = {f.pred for f in self.facts}
        for r in self.rules:
            preds.add(r.head.pred)
            for lit in r.body:
                if not isinstance(lit, Cmp):
                    preds.add(lit.atom.pred)
        for name, arity in self.worlds:
            preds.add(PredKey(name, arity))
        return preds

    def constants(self) -> set:
        consts: set = set()

        def add(terms: Iterable[Term]) -> None:
            for t in terms:
                if not isinstance(t, Var):
                    consts.add(t)

        for f in self.facts:
            add(f.args)
        for r in self.rules:
            add(r.head.args)
            for lit in r.body:
                if isinstance(lit, Cmp):
                    add((lit.left, lit.right))
                else:
                    add(lit.atom.args)
        return consts

    def __str__(self) -> str:
        lines = [f"pred {n}/{a} {w}." for (n, a), w in sorted(self.worlds.items())]
        lines += [f"{f}." for f in self.facts]
        lines += [str(r) for r in self.rules]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Total order on constants (same convention as clingo: integers < symbols < strings)
# ---------------------------------------------------------------------------


def const_key(c: Const) -> tuple:
    if isinstance(c, bool):  # guard: bool is an int subclass
        raise TypeError("booleans are not terms")
    if isinstance(c, int):
        return (0, c, "")
    if isinstance(c, Sym):
        return (1, 0, c.name)
    if isinstance(c, Text):
        return (2, 0, c.value)
    raise TypeError(f"not a constant: {c!r}")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class ParseError(ValueError):
    pass


_PUNCT2 = (":-", "!=", "<=", ">=")
_PUNCT1 = "(),.-=<>/"
_KEYWORDS = {"pred", "not", "nao_consta", "fechado", "aberto"}


@dataclass(frozen=True)
class _Tok:
    kind: str  # NAME VAR INT STR P EOF
    text: str
    pos: int


def _tokenize(src: str) -> list[_Tok]:
    toks: list[_Tok] = []
    i, n = 0, len(src)
    while i < n:
        ch = src[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "%":
            while i < n and src[i] != "\n":
                i += 1
            continue
        if src.startswith(_PUNCT2, i):
            toks.append(_Tok("P", src[i : i + 2], i))
            i += 2
            continue
        if ch == "-" and i + 1 < n and src[i + 1].isdigit():
            j = i + 1
            while j < n and src[j].isdigit():
                j += 1
            toks.append(_Tok("INT", src[i:j], i))
            i = j
            continue
        if ch in _PUNCT1:
            toks.append(_Tok("P", ch, i))
            i += 1
            continue
        if ch.isdigit():
            j = i
            while j < n and src[j].isdigit():
                j += 1
            toks.append(_Tok("INT", src[i:j], i))
            i = j
            continue
        if ch == '"':
            j, buf = i + 1, []
            while j < n and src[j] != '"':
                if src[j] == "\\" and j + 1 < n:
                    buf.append(src[j + 1])
                    j += 2
                else:
                    buf.append(src[j])
                    j += 1
            if j >= n:
                raise ParseError(f"unterminated string at {i}")
            toks.append(_Tok("STR", "".join(buf), i))
            i = j + 1
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            word = src[i:j]
            kind = "VAR" if (word[0].isupper() or word[0] == "_") else "NAME"
            toks.append(_Tok(kind, word, i))
            i = j
            continue
        raise ParseError(f"unexpected character {ch!r} at {i}")
    toks.append(_Tok("EOF", "", n))
    return toks


class _Parser:
    def __init__(self, src: str) -> None:
        self.toks = _tokenize(src)
        self.i = 0
        self.program = Program()
        self._anon = 0

    # -- helpers -----------------------------------------------------------
    def peek(self, k: int = 0) -> _Tok:
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def take(self) -> _Tok:
        tok = self.toks[self.i]
        self.i += 1
        return tok

    def expect(self, kind: str, text: str | None = None) -> _Tok:
        tok = self.take()
        if tok.kind != kind or (text is not None and tok.text != text):
            want = text or kind
            raise ParseError(f"expected {want!r} at {tok.pos}, got {tok.text!r}")
        return tok

    def at(self, kind: str, text: str | None = None) -> bool:
        tok = self.peek()
        return tok.kind == kind and (text is None or tok.text == text)

    # -- grammar -----------------------------------------------------------
    def parse(self) -> Program:
        while not self.at("EOF"):
            self.statement()
        return self.program

    def statement(self) -> None:
        if self.at("NAME", "pred") and self.peek(1).kind == "NAME" and self.peek(2).text == "/":
            self.declaration()
            return
        head = self.atom()
        if self.at("P", ":-"):
            self.take()
            body = [self.literal()]
            while self.at("P", ","):
                self.take()
                body.append(self.literal())
            self.expect("P", ".")
            rule = Rule(len(self.program.rules), head, tuple(body))
            self.program.rules.append(rule)
            return
        self.expect("P", ".")
        if not head.is_ground():
            raise ParseError(f"fact {head} is not ground")
        self.program.facts.append(head)

    def declaration(self) -> None:
        self.expect("NAME", "pred")
        name = self.expect("NAME").text
        self.expect("P", "/")
        arity = int(self.expect("INT").text)
        world = "aberto"
        if self.at("NAME") and self.peek().text in ("fechado", "aberto"):
            world = self.take().text
        self.expect("P", ".")
        key = (name, arity)
        if key in self.program.worlds and self.program.worlds[key] != world:
            raise ParseError(f"conflicting world declarations for {name}/{arity}")
        self.program.worlds[key] = world

    def atom(self) -> Atom:
        neg = False
        if self.at("P", "-"):
            self.take()
            neg = True
        tok = self.expect("NAME")
        if tok.text in _KEYWORDS:
            raise ParseError(f"reserved word {tok.text!r} used as predicate at {tok.pos}")
        args: list[Term] = []
        if self.at("P", "("):
            self.take()
            args.append(self.term())
            while self.at("P", ","):
                self.take()
                args.append(self.term())
            self.expect("P", ")")
        return Atom(PredKey(tok.text, len(args), neg), tuple(args))

    def term(self) -> Term:
        tok = self.take()
        if tok.kind == "VAR":
            if tok.text == "_":
                self._anon += 1
                return Var(f"_Anon{self._anon}")
            return Var(tok.text)
        if tok.kind == "INT":
            return int(tok.text)
        if tok.kind == "STR":
            return Text(tok.text)
        if tok.kind == "NAME":
            return Sym(tok.text)
        raise ParseError(f"expected a term at {tok.pos}, got {tok.text!r}")

    def literal(self) -> Literal:
        if self.at("NAME", "not") and self.peek(1).kind in ("NAME", "P"):
            self.take()
            return Naf(self.atom())
        if self.at("NAME", "nao_consta") and self.peek(1).text == "(":
            self.take()
            self.expect("P", "(")
            atom = self.atom()
            self.expect("P", ")")
            return NaoConsta(atom)
        # comparison: term OP term (a term that is not followed by '(' when it is a NAME)
        tok = self.peek()
        nxt = self.peek(1)
        is_term_start = tok.kind in ("VAR", "INT", "STR") or (
            tok.kind == "NAME" and nxt.kind == "P" and nxt.text in CMP_OPS
        )
        if is_term_start:
            left = self.term()
            op = self.take()
            if op.kind != "P" or op.text not in CMP_OPS:
                raise ParseError(f"expected a comparison operator at {op.pos}")
            right = self.term()
            return Cmp(op.text, left, right)
        return Pos(self.atom())


def parse_program(src: str) -> Program:
    return _Parser(src).parse()


def parse_atom(src: str) -> Atom:
    p = _Parser(src)
    atom = p.atom()
    if not p.at("EOF"):
        raise ParseError(f"trailing input after atom: {p.peek().text!r}")
    return atom
