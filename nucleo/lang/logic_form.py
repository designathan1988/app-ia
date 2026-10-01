"""Logical form: the meaning structure of a sentence, composed from its Universal Dependencies tree.

The composition is driven by the dependency relations, which are the same in every language (UDepLambda, Reddy
et al. 2017; PredPatt, White et al. 2016), not by a list of constructions:

- a **predicate** (an event, or a state for copular and predicative clauses) with **roles** given by its
  dependents: nsubj -> subject, obj -> object, iobj -> recipient, obl/nmod (by its preposition) -> place, goal,
  source, value, accompaniment; xcomp -> result; advmod -> manner or direction;
- a **mention** for each noun phrase: its head, determiner (definite, indefinite, universal, demonstrative), ordinal,
  modifiers (adjectives, nouns, numbers), names and literals, and the phrases attached to it (possessor, location);
- the **speech act** (request, wish, obligation, question, assertion) and **negation**;
- **coordination** distributes over conjuncts.

What a preposition means is the only language-specific part: it comes from the language profile (``langs``) and
``frames.json`` (places, value markers, the possessive), which are the closed-class grammar of each language.

The logical form says nothing yet about the page or the builder: grounding and interpretation come after
(``interpret``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import langs
from .tokenize import is_literal, literal_value
from .values import fold

# dependency relation (without subtype) -> role, for dependents of a predicate
ROLE = {"nsubj": "subj", "obj": "obj", "iobj": "iobj", "xcomp": "result", "ccomp": "content", "csubj": "subj",
        "advmod": "adv", "obl": "obl", "nmod": "obl", "expl": None, "aux": None, "cop": None, "mark": None,
        "punct": None, "discourse": None, "vocative": None, "dep": "obl", "advcl": "adv", "parataxis": None,
        "compound": "adv", "conj": None, "cc": None, "det": None, "case": None, "fixed": None, "flat": None}


@dataclass
class Mention:
    """A noun phrase: what it says about the thing it refers to."""
    head: object  # Token
    words: list  # tokens of the phrase, in order
    det: str = ""  # definite | indefinite | universal | demonstrative | pronoun | ""
    ordinal: int | None = None
    new: bool = False  # said to be new ("outro", "mais um", "another")
    mods: list = field(default_factory=list)  # modifier tokens (adjectives, nouns, numbers) not part of a name
    names: list = field(default_factory=list)  # proper names and quoted literals
    attached: list = field(default_factory=list)  # [(relation, Mention)]: "do cartão", "in the footer"
    conj: list = field(default_factory=list)  # coordinated mentions ("o título e o botão")

    def text(self) -> str:
        return " ".join(t.form for t in self.words)


@dataclass
class Predicate:
    head: object  # Token (verb; or the adjective/noun of a copular clause)
    lemma: str
    kind: str = "event"  # event | state
    act: str = "request"  # request | wish | obligation | question | assertion
    negated: bool = False
    roles: list = field(default_factory=list)  # [(role, relation_word, Mention | Predicate | str)]
    conj: list = field(default_factory=list)  # coordinated predicates sharing the subject/act

    def role(self, name: str) -> list:
        return [x for r, _, x in self.roles if r == name]


@dataclass
class Sentence:
    tokens: list
    predicates: list  # top-level predicates (coordinated clauses are listed in order)


# -- the tree ----------------------------------------------------------------------------------------------------
def _children(tokens) -> dict:
    out: dict = {}
    for t in tokens:
        out.setdefault(t.head, []).append(t)
    return out


def _base(rel: str) -> str:
    return rel.split(":")[0]


def _subtree(tok, kids) -> list:
    out = [tok]
    for c in kids.get(tok.i, []):
        out += _subtree(c, kids)
    return sorted(out, key=lambda t: t.i)


def _case_of(tok, kids) -> str:
    """The preposition(s) of a phrase ("de", "em o fim de" -> its first word kept whole)."""
    marks = [c for c in kids.get(tok.i, []) if _base(c.deprel) in ("case", "mark") and c.i < tok.i]
    # a multiword preposition is one function word (UD fixed): "para depois de", "em cima de", "on top of"
    marks += [f for c in list(marks) for f in kids.get(c.i, []) if _base(f.deprel) == "fixed"]
    return " ".join(fold(c.form.lower()) for c in sorted(marks, key=lambda t: t.i))


# -- mentions -----------------------------------------------------------------------------------------------------
def mention(tok, kids) -> Mention:
    prof = langs.profile()
    words = _subtree(tok, kids)
    m = Mention(tok, words)
    for c in kids.get(tok.i, []):
        rel = _base(c.deprel)
        low = fold(c.form.lower())
        if rel == "det" or rel == "nummod" and c.i < tok.i:
            if low in prof["universal"]:
                m.det = "universal"
            elif low in prof["new"]:
                m.new = True
            elif low in prof["ordinals"]:
                m.ordinal = prof["ordinals"][low]
            elif low in prof["indefinite"] and not m.det:
                m.det = "indefinite"
            elif low in prof["definite"] and not m.det:
                m.det = "definite"
        elif rel in ("amod", "nummod", "compound", "acl"):
            if low in prof["ordinals"]:
                m.ordinal = prof["ordinals"][low]
            elif low in prof["new"]:
                m.new = True
            elif c.upos == "PROPN" or c.form[:1].isupper() and c.i > 1 or is_literal(c.form):
                m.names.append(literal_value(c.form))
            else:
                m.mods.append(c)
        elif rel == "flat" or rel in ("appos", "nmod") and c.upos == "PROPN" and not _case_of(c, kids) or \
                rel == "appos" and not _case_of(c, kids) and not kids.get(c.i):
            # (an apposition has no preposition: "do parágrafo" labelled appos is a modifier, kept with its phrase)
            m.names.append(literal_value(c.form) if is_literal(c.form) else c.form)
            # (phrases the parser hung on the name belong to the phrase: "o contêiner Actions como 'X'")
            for g in kids.get(c.i, []):
                if _base(g.deprel) in ("nmod", "obl", "acl"):
                    m.attached.append((_case_of(g, kids), mention(g, kids)))
        elif rel in ("nmod", "obl", "acl", "appos"):
            m.attached.append((_case_of(c, kids), mention(c, kids)))
        elif rel == "conj" and c.upos in ("NOUN", "PROPN", "PRON"):
            m.conj.append(mention(c, kids))
    if tok.upos == "PROPN" or is_literal(tok.form) or tok.form[:1].isupper() and tok.i > 1:
        # (a capitalised word inside the sentence is a name, whatever category the tagger gave it)
        m.names.insert(0, literal_value(tok.form) if is_literal(tok.form) else tok.form)
    if tok.upos == "PRON" or fold(tok.form.lower()) in prof["pronouns"]:
        m.det = "pronoun"
    return m


# -- predicates ---------------------------------------------------------------------------------------------------
def _is_copula(t, prof) -> bool:
    from .understand import COPULAS, morph_lemmas

    return t.lemma in COPULAS or any(c in COPULAS for c in morph_lemmas(t.form, "V"))


def predicate(tok, kids, tokens, act: str = "request") -> Predicate:
    prof = langs.profile()
    deps = kids.get(tok.i, [])
    cop = next((c for c in deps if _base(c.deprel) == "cop" or
                _base(c.deprel) == "aux" and _is_copula(c, prof) and tok.upos in ("ADJ", "NOUN", "PROPN", "VERB")),
               None)
    if cop is not None:
        # a copular clause: the state is the head; the copula carries the verb
        p = Predicate(tok, tok.lemma, kind="state", act=act)
        p.roles.append(("attr", "", _value_or_mention(tok, kids)))
    else:
        p = Predicate(tok, tok.lemma, act=act)
    for c in deps:
        rel = _base(c.deprel)
        role = ROLE.get(rel, "obl")
        low = fold(c.form.lower())
        if rel in ("advmod",) and low in ("nao", "not", "never", "nunca", "n't"):
            p.negated = True
            continue
        if rel == "conj" and c.upos in ("VERB", "AUX") or rel == "conj" and _base(c.deprel) == "conj" and \
                any(_base(x.deprel) in ("obj", "cop") for x in kids.get(c.i, [])):
            p.conj.append(predicate(c, kids, tokens, act))
            continue
        if role is None or cop is not None and c is cop:
            continue
        if role == "result" or rel == "xcomp":
            if c.upos in ("VERB", "AUX") and not _participle(c):
                p.roles.append(("content", "", predicate(c, kids, tokens, act)))
            else:
                p.roles.append(("result", _case_of(c, kids), _value_or_mention(c, kids)))
            continue
        if role == "content":
            p.roles.append(("content", "", predicate(c, kids, tokens, act)))
            continue
        if role == "adv":
            p.roles.append(("adv", _case_of(c, kids), _value_or_mention(c, kids)))
            continue
        case = _case_of(c, kids)
        if role in ("obl", "obj") and (c.upos == "ADJ" or c.upos == "VERB" and _participle(c)) and cop is None                 and not case:
            # an adjective is never a nominal argument: depending on a verb, it predicates a state of the object
            # or subject (secondary predication, UD xcomp)
            role = "result"
        elif role == "obj" and case:
            role = "obl"  # an object never has a case marker: a phrase with a preposition is oblique
        elif role == "obl" and not case and c.upos in ("NOUN", "PROPN", "PRON") and not p.role("obj") and                 p.kind == "event":
            # a nominal argument without a preposition is the object (UD obl always has a case marker)
            role = "obj"
        p.roles.append((role, case, _value_or_mention(c, kids)))
    return p


def _participle(t) -> bool:
    if langs.current() == "en":
        return t.form.lower().endswith(("ed", "en")) and t.upos in ("VERB", "ADJ")
    from .morph import analyses

    return any(tags.startswith("V+PTPST") for _, tags in analyses(t.form.lower()))


def _value_or_mention(tok, kids):
    """A dependent as a mention (a noun phrase, an adjective, a literal): kept as a Mention so grounding sees all of
    its words."""
    return mention(tok, kids)


# -- the sentence -------------------------------------------------------------------------------------------------
def build(tokens) -> Sentence:
    """The logical form of an analysed sentence (tokens with heads and relations)."""
    from .understand import MODALS

    kids = _children(tokens)
    by_i = {t.i: t for t in tokens}
    roots = [t for t in tokens if t.head == 0]
    out = []
    for r in roots:
        act = "question" if any(t.form == "?" for t in tokens) else "request"
        top = r
        # a modal or volitive head ("quero", "pode", "tem que", "should", "I'd like"): the speaker wants a state or an
        # act; the predicate is the verbal complement it governs (an infinitive; or a participle with its own copula,
        # "to be centered"), never a noun: "quero o parágrafo sublinhado" is a wish about a state
        while (top.lemma in MODALS or fold(top.form.lower()) in MODALS) and top.upos in ("VERB", "AUX", "ADJ"):
            if act == "request":
                act = "wish"
            nxt = next((c for c in kids.get(top.i, []) if _base(c.deprel) in ("xcomp", "ccomp", "obj", "csubj")
                        and c.upos in ("VERB", "AUX", "ADJ")
                        and (not _participle(c) and c.upos != "ADJ" or any(
                            _base(x.deprel) in ("cop", "aux") for x in kids.get(c.i, [])))), None)
            if nxt is None:
                break
            top = nxt
        p = predicate(top, kids, tokens, act)
        if top is not r and not p.role("subj"):
            # control (UD xcomp): the governed predicate's subject is the governing verb's object when it has one
            # ("I need the paragraph to be centered"), else its subject ("o título tem que ficar azul")
            gov = predicate(by_i[top.head] if top.head in by_i else r, kids, tokens, act)
            ctl = [(rl, w, x) for rl, w, x in gov.roles if rl == "obj"] or                 [(rl, w, x) for rl, w, x in gov.roles if rl == "subj"]
            p.roles += [("subj", w, x) for _, w, x in ctl]
        if any(_base(t.deprel) == "aux" and t.lemma in MODALS for t in kids.get(top.i, [])) and p.act == "request":
            p.act = "wish"  # "o título deve ser azul", "the button should be green"
        # a statement: the subject before the verb (requests have none) and no prospective auxiliary or tense
        if p.act == "request" and _declarative(top, tokens, kids, p):
            p.act = "assertion"
        out.append(p)
        out += p.conj
        # clauses side by side ("me faz um favor, centraliza o parágrafo"; "o título tá pequeno, coloca 36px"): each
        # one is said on its own
        for c in kids.get(r.i, []) + kids.get(top.i, []):
            if _base(c.deprel) == "parataxis" and c.upos in ("VERB", "AUX", "ADJ", "NOUN"):
                q = predicate(c, kids, tokens, "request")
                if q.act == "request" and _declarative(c, tokens, kids, q):
                    q.act = "assertion"
                if all(q.head is not x.head for x in out):
                    out.append(q)
                    out += q.conj
    out.sort(key=lambda q: q.head.i)
    return Sentence(tokens, out)


def _declarative(top, tokens, kids, p) -> bool:
    """A sentence that states something: a subject before its verb (an imperative has no subject), in the present
    or past, with no auxiliary (an auxiliary is prospective or modal: "vai ser", "will be")."""
    from .morph import analyses

    # (a subject has no preposition, UD nsubj: a phrase with one is no subject, "underline the card" is no statement)
    subj = [x for r, w, x in p.roles if r == "subj" and not w and isinstance(x, Mention)]
    if not subj or not any(t.i < top.i for m in subj for t in m.words):
        return False
    if any(fold(m.head.form.lower()) in langs.profile().get("addressee", set()) for m in subj):
        return False  # "você coloca o título...", "you set the title...": said to the listener, a directive
    if any(_base(t.deprel) == "aux" for t in kids.get(top.i, [])):
        return False
    verb = next((t for t in kids.get(top.i, []) if _base(t.deprel) == "cop"), top)
    if langs.current() != "en" and any("+FUT" in tg for _, tg in analyses(verb.form.lower())):
        return False
    return True


def show(s: Sentence) -> str:
    """A readable rendering, for tests and explanations."""
    def m_(m):
        if isinstance(m, Predicate):
            return p_(m)
        bits = [m.head.form]
        if m.det:
            bits.append(m.det)
        if m.ordinal is not None:
            bits.append(f"ord={m.ordinal}")
        if m.new:
            bits.append("novo")
        if m.names:
            bits.append("nome=" + "/".join(m.names))
        if m.mods:
            bits.append("mods=" + ",".join(t.form for t in m.mods))
        for rel, a in m.attached:
            bits.append(f"{rel or '∅'}:{m_(a)}")
        for c in m.conj:
            bits.append(f"&{m_(c)}")
        return "[" + " ".join(bits) + "]"

    def p_(p):
        roles = " ".join(f"{r}{'/' + w if w else ''}={m_(x)}" for r, w, x in p.roles)
        neg = " NÃO" if p.negated else ""
        return f"{p.act}:{p.kind}:{p.lemma}{neg}({roles})"

    return " ; ".join(p_(p) for p in s.predicates)


def signature(p: Predicate) -> str:
    """A compact canonical form of a predicate, for tests: lemma(role[:case]=head, ...) with roles sorted;
    nested predicates in brackets."""
    def arg(x):
        if isinstance(x, Predicate):
            return "[" + signature(x) + "]"
        return fold(x.head.form.lower())

    roles = sorted(f"{r}{':' + w if w and r != 'obj' else ''}={arg(x)}" for r, w, x in p.roles)
    return f"{fold(p.lemma)}({','.join(roles)})"
