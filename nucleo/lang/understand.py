"""Understanding a Portuguese request: the least-cost explanation of the sentence against the current document.

Pipeline:

1. Tokenize (literals protected, contractions split). Tag and parse with the linear models trained on the UD
   treebanks.
2. The predicate is the root verb. A modal or volitive verb ("pode", "quero") gives way to the verb it governs.
   The verb's lemma comes from MorphoBr (exact) or the treebank lemmatizer.
3. The arguments are the verb's dependents. Inside each argument, the grounded lexicon (``lexicon.py``) names
   entities by their longest label, and the rest splits at prepositions into references and places. A
   prepositional phrase the parser attached to the wrong word is therefore still available as an argument.
4. **Abduction** (Hobbs 1993). Every frame of the verb (``frames.json``) is tried against the document. Each
   assumption has a cost, and the reading with the least total cost is the interpretation. Costs come from:
   - a verb outside the frame;
   - an ambiguous or unresolved referent;
   - a missing value;
   - each word left unexplained.
5. **Decision.**
   - "executar": one cheap reading, or several readings that ask for the same thing.
   - "perguntar": two cheap readings that ask for different things. The question shows both paraphrases.
   - "nao_entendi": no reading is cheap enough. The answer lists what was not understood.

The result is a list of constraints (the planner's goal vocabulary) plus a Portuguese paraphrase of them. The
command is chosen by the planner, not here.
"""

from __future__ import annotations

import json
import re
import pathlib
from types import SimpleNamespace
from dataclasses import dataclass, field
from functools import lru_cache

from . import command_verbs, langs, learned, lexicon
from . import values as values_mod
from .values import fold
from .values import index as value_index
from .morph import lemmas as _pt_lemmas


def morph_lemmas(form: str, category: str | None = None) -> list[str]:
    """Lemmas of a form: MorphoBr for Portuguese; the English treebank's lemmas (and the wordnet) for English."""
    if langs.current() == "en":
        return [langs.english_lemma(form, "VERB" if category == "V" else None)]
    return _pt_lemmas(form, category)
from .syntax import load_models
from .tokenize import is_literal, literal_value, tokenize

class _Frames(dict):
    """frames.json, whose function-word parts (places, value markers, field names) come from the current language's
    profile when it has them (``langs``)."""

    def __getitem__(self, key):
        prof = langs.profile()
        if langs.current() != "pt" and key in ("locais", "valor_casos", "campos") and key in prof:
            return prof[key]
        return dict.__getitem__(self, key)


class _LangSet:
    """A closed class of words (modals, articles, pronouns...) of the current language."""

    def __init__(self, key: str) -> None:
        self.key = key

    def _set(self) -> set:
        return langs.profile()[self.key]

    def __contains__(self, x) -> bool:
        return x in self._set()

    def __iter__(self):
        return iter(self._set())

    def __or__(self, other):
        return set(self._set()) | set(other)


FRAMES = _Frames(json.loads((pathlib.Path(__file__).with_name("frames.json")).read_text(encoding="utf-8")))
MODALS = _LangSet("modals")
# verbs that link a subject to a state ("o título tem que ficar vermelho"): the request is that state
COPULAS = _LangSet("copulas")
PRONOUNS = _LangSet("pronouns")
COST = {"verbo_fora_do_quadro": 4.0, "construcao": 1.5, "referente_ambiguo": 2.5, "referente_por_tipo": 0.5,
        "referente_pela_selecao": 0.3, "referente_nao_resolvido": 5.0, "valor_ausente": 5.0,
        "palavra_sem_explicacao": 1.0, "tipo_diferente_do_nome": 2.0, "local_ausente": 0.5,
        "artigo_como_preposicao": 0.5, "objeto_com_preposicao": 1.0, "definido_para_novo": 1.0,
        "indefinido_para_existente": 2.0, "definido_com_referente": 3.0,
        "tipo_de_valor_incompativel": 3.0, "propriedade_pelo_valor": 1.0, "significado_inferido": 1.0, "significado_pelo_dicionario": 0.5, "valor_primeiro": 0.3, "palavra_com_significado_ignorada": 4.5}
LIMIT = 4.0


@dataclass
class Token:
    i: int
    form: str
    lemma: str
    upos: str
    head: int
    deprel: str
    alts: tuple = ()  # other lemmas the form can have (homographs: "some" = somar / sumir)
    particle: bool = False  # part of a multiword verb ("jogar fora"): not an argument


@dataclass
class Reading:
    frame: str
    constraints: list
    cost: float
    assumptions: list = field(default_factory=list)
    paraphrase: str = ""
    ambiguous: list = field(default_factory=list)  # candidate nodes when a referent was not unique
    unknown_verb: bool = False
    verb: str = ""
    uncertain: bool = False  # its meaning came through the dictionary by an indirect path: confirm before acting


@dataclass
class Understanding:
    text: str
    tokens: list
    readings: list
    decision: str
    message: str = ""
    lang: str = "pt"

    @property
    def best(self) -> Reading | None:
        return self.readings[0] if self.readings else None


def _models():
    return _models_for(langs.current())


@lru_cache(maxsize=4)
def _models_for(lang: str):
    return load_models(lang)


def analyse(text: str) -> list[Token]:
    tagger, parser, lem, _ = _models()
    words = tokenize(text)
    tags = tagger.tag([("VALOR" if is_literal(w) else w) for w in words])
    arcs = parser.parse([("VALOR" if is_literal(w) else w) for w in words], tags)
    out = []
    for i, (w, t, (h, lab)) in enumerate(zip(words, tags, arcs), 1):
        if is_literal(w):
            lemma = w
        elif t in ("VERB", "AUX"):
            cands = morph_lemmas(w, "V")
            known = [c for c in cands if _known_verb(c) or c in MODALS]
            lemma = (known or cands or [lem.lemma(w, t)])[0]
        else:
            lemma = lem.lemma(w, t)
        alts = tuple(c for c in (morph_lemmas(w, "V") if t in ("VERB", "AUX") else []) if c != lemma)
        out.append(Token(i, w, lemma, t, h, lab, alts))
    return out


# -- argument structure ---------------------------------------------------------------------------------------
def _subtree(tokens: list[Token], root: int) -> list[Token]:
    keep = {root}
    changed = True
    while changed:
        changed = False
        for t in tokens:
            if t.head in keep and t.i not in keep:
                keep.add(t.i)
                changed = True
    return [t for t in tokens if t.i in keep]


def _in_frame(lemma: str, frame: dict | None = None) -> bool:
    """Whether a verb belongs to a frame's class (or to any): listed in frames.json, or induced from use."""
    induced = learned.classes().get(lemma)
    lang = langs.current()
    if frame is not None:
        return lemma in langs.frame_verbs(frame["id"], lang) or induced == frame["id"]
    return induced is not None or any(lemma in langs.frame_verbs(f["id"], lang) for f in FRAMES["quadros"])


def _known_verb(lemma: str) -> bool:
    """A verb with a meaning: in a frame, taught by the user, the label of a builder command, or naming a value."""
    return _in_frame(lemma) or lemma in learned.verbs() or \
        lemma in command_verbs.table() or bool(_verb_value_pairs(lemma))


def _frame_verb(form: str) -> str | None:
    """The lemma of a known verb this form can be, per MorphoBr, whatever tag the tagger gave it ("ajuste": a noun
    to the tagger, but also the subjunctive of "ajustar")."""
    for lemma in morph_lemmas(form, "V"):
        if _known_verb(lemma):
            return lemma
    return None


@lru_cache(maxsize=1)
def _participle_pairs() -> dict:
    """verb -> [(property, value)] named by its participle ("centralizado" names text-align: center, so
    "centralizar" means to give that value)."""
    from .morph import analyses

    out: dict = {}
    PARTICIPLE_WORD.clear()
    for word, pairs in value_index().items():
        for lemma, tags in analyses(word):
            if tags.startswith("V+PTPST"):
                out.setdefault(lemma, [])
                out[lemma] += [pr for pr in pairs if pr not in out[lemma]]
                for pr in pairs:
                    PARTICIPLE_WORD[(lemma,) + pr] = word
    return out


PARTICIPLE_WORD: dict = {}  # (verb, property, value) -> the participle that names the value


def _verb_value_pairs(lemma: str) -> list:
    return list(_participle_pairs().get(lemma, []))


def _predicative(tokens: list[Token], t: Token) -> bool:
    """A participle right after a noun describes it ("o título sublinhado"): it is a state, not the request's verb."""
    from .morph import analyses

    k = tokens.index(t)
    return k > 0 and tokens[k - 1].upos in ("NOUN", "PROPN") and         any(tags.startswith("V+PTPST") for _, tags in analyses(t.form.lower()))


def _predicate(tokens: list[Token]) -> Token | None:
    """The request's verb. The parser proposes (the root, or what a modal root governs); the lexicon reranks when
    the proposal is not a frame verb but another word can be one."""
    roots = [t for t in tokens if t.head == 0]
    # a copular clause ("the title should be bold", "o título está vermelho"): UD makes the predicate adjective the
    # root and hangs the copula on it; the request is the state, and the copula is its verb
    for r in roots:
        cop = next((t for t in tokens if t.head == r.i and t.deprel == "cop"), None)
        if cop is not None and r.upos in ("ADJ", "NOUN", "PROPN"):
            cop.lemma = next((c for c in COPULAS if c in morph_lemmas(cop.form, "V")), cop.lemma)
            return cop
    pred = next((t for t in roots if t.upos in ("VERB", "AUX") and t.lemma not in MODALS
                 and not _politeness(tokens, tokens.index(t)) and not _predicative(tokens, t)), None)
    if pred is None and roots:
        pred = roots[0]
        for _ in range(3):
            deps = [t for t in tokens if t.head == pred.i and t.upos == "VERB"]
            if pred.lemma in MODALS or pred.upos not in ("VERB", "AUX"):
                if deps:
                    pred = deps[0]
                    continue
            break
    if pred is not None and pred.upos in ("VERB", "AUX") and pred.lemma not in MODALS and \
            _in_frame(pred.lemma):
        return pred
    for k, t in enumerate(tokens):  # lexical reranking: the first word that can be a frame verb
        if _politeness(tokens, k) or _predicative(tokens, t):
            continue
        if fold(t.form.lower()) in _case_words() or t.form.lower() in lexicon.stop():
            continue  # a preposition or article is never the request's verb ("to" read as a verb by the tagger)
        lemma = _frame_verb(t.form)
        if lemma and t.lemma not in MODALS:
            t.lemma, t.upos = lemma, "VERB"
            return t
    modal = next((t for t in roots if t.lemma in MODALS), None)
    if modal is not None and not any(t.upos == "VERB" and t is not modal and not _predicative(tokens, t)
                                     for t in tokens):
        return modal  # "quero o título sublinhado": no other verb than a predicative participle
    if pred is None or pred.upos not in ("VERB", "AUX") or pred.lemma in MODALS:
        verbs = [t for t in tokens if t.upos == "VERB" and t.lemma not in MODALS]
        pred = verbs[0] if verbs else pred
    # a request opens with its verb: when the first word is a verb the wordnet knows (in any of its regular
    # forms: "delete" -> "deletar"), it is the predicate, even if the tagger read it otherwise
    first = next((k for k in range(len(tokens)) if not _politeness(tokens, k) and tokens[k].upos != "PUNCT"), None)
    if first is not None and (pred is None or pred.upos not in ("VERB", "AUX") or pred.i != tokens[first].i):
        verb = _graph_verb(tokens[first].form)
        if verb and (pred is None or pred.upos not in ("VERB", "AUX")):
            tokens[first].lemma, tokens[first].upos = verb, "VERB"
            return tokens[first]
    return pred


def _meaning_cost(lemma: str) -> float:
    """The cost of the cheapest action meaning a verb has for the machine (9 when it has none)."""
    from . import grounding

    costs = [m.cost for m in grounding.meanings(lemma, "V") if m.kind in ("comando", "acao", "verbo")]
    return min(costs, default=9.0)


def _multiword_verb(tokens: list[Token], pred: Token) -> None:
    """A verb and the particle after it that the wordnet lexicalizes together ("jogar fora", "pôr para fora"):
    the pair is the verb, and the particle is no argument."""
    from . import concepts

    k = next((i for i, t in enumerate(tokens) if t.i == pred.i), None)
    if k is None:
        return
    for n in (2, 1):  # "get rid of", "jogar fora"
        tail = tokens[k + 1:k + 1 + n]
        if len(tail) != n or tail[0].upos not in ("ADV", "ADP", "PART", "ADJ", "NOUN"):
            continue
        phrase = " ".join([pred.lemma] + [t.form.lower() for t in tail])
        if concepts.concepts_of(phrase, langs.current(), "v"):
            pred.lemma = phrase
            for t in tail:
                t.particle = True
            return


def _graph_verb(form: str) -> str | None:
    from . import concepts

    for inf in morph_lemmas(form, "V") + _regular_infinitives(form):
        if concepts.concepts_of(inf, langs.current(), "v"):
            return inf
    return None


def _politeness(tokens: list[Token], k: int) -> bool:
    """ "por favor" is a fixed politeness formula: its "por" is not the verb "pôr"."""
    return tokens[k].form.lower() == "por" and k + 1 < len(tokens) and tokens[k + 1].form.lower() == "favor"


ARTICLE_FORMS = _LangSet("article_forms")
DEFINITE = _LangSet("definite")
INDEFINITE = _LangSet("indefinite")


@dataclass
class Piece:
    case: tuple  # lemmas of the preposition(s) that introduce it, () for a bare phrase
    words: list  # tokens (content)
    det: str | None = None  # the determiner that opened it, if any

    @property
    def lemmas(self) -> tuple:
        # the same lemmatization as the lexicon's labels, whatever tag the word got ("prevista": a participle to the
        # tagger, an adjective in the label "Mudança prevista")
        # articles are not content, whatever tag the tagger gave them ("o" tagged as a pronoun)
        return tuple(lexicon.lemma_of(t.form) for t in self.words
                     if not is_literal(t.form) and t.form.lower() not in lexicon.stop())


def _pieces(tokens: list[Token], pred: Token) -> list[Piece]:
    """The words after (and around) the predicate, cut at prepositions into pieces, in surface order.
    Determiners and punctuation are dropped; modal/politeness words that belong to no argument are ignored."""
    used = {pred.i}
    for t in tokens:
        # a subject is dropped only when it is a pronoun ("você"): a phrase the parser mislabels as subject would
        # otherwise vanish with its whole subtree
        if t.head == pred.i and (t.deprel in ("aux", "punct", "discourse", "vocative", "mark", "cop")
                                 or t.deprel == "nsubj" and t.upos == "PRON" and t.i < pred.i
                                 or t.lemma in MODALS or t.lemma in ("por", "favor") and t.deprel in ("advmod", "obl")):
            for s in _subtree(tokens, t.i):
                used.add(s.i)
    # heads of the sentence above the predicate (a modal root) are not arguments either
    for t in tokens:
        # (a pronoun after the verb of a request is its object, "deixe ele vermelho"; before it, the subject)
        if t.i != pred.i and (t.lemma in MODALS or t.upos == "PRON" and t.deprel == "nsubj" and t.i < pred.i):
            used.add(t.i)
    pieces: list[Piece] = []
    # a modifier of the verb said before it ("right align the title", "left-align"): an argument of its own
    # (a request has no subject: a value word the parser took for one, "center align", is such a modifier too)
    mods = [t for t in tokens if t.i < pred.i and t.head == pred.i and t.i not in used and
            t.upos in ("ADJ", "ADV", "NOUN") and
            (t.deprel in ("advmod", "amod", "compound", "obl", "xcomp", "nmod") or
             t.deprel == "nsubj" and fold(t.form.lower()) in value_index())]
    if mods:
        pieces.append(Piece((), mods))
        used |= {t.i for t in mods}
    current = Piece((), [])
    for k, t in enumerate(tokens):
        nxt = tokens[k + 1] if k + 1 < len(tokens) else None
        if t.i not in used and fold(t.lemma) in _locution_heads() and nxt is not None and nxt.upos == "ADP":
            # a locative head right before a preposition opens a new place phrase ("... depois do título")
            if current.words:
                pieces.append(current)
                current = Piece((fold(t.lemma),), [])
            else:
                current = Piece(current.case + (fold(t.lemma),), [])
            continue
        if t.i == pred.i:
            # before the verb: a fronted place ("na seção Hero, coloque ...") is an argument; loose words
            # ("quero que você ...", "por favor, ...") are not
            if current.words and current.case:
                pieces.append(current)
            current = Piece((), [])
            continue
        if t.upos == "DET" and t.i not in used and not current.words:
            # "todos os títulos": the quantifier is kept, the article after it adds nothing
            if not (current.det and fold(current.det) in langs.profile()["universal"]):
                current.det = t.form.lower()
            continue
        if t.i in used or t.upos in ("PUNCT", "DET") or t.lemma in ("favor",) or t.particle:
            continue
        if t.upos == "ADP" or t.upos in ("SCONJ", "PART") and fold(t.form.lower()) in _case_words():
            # "para" before a word the tagger read as a verb ("para Comprar") still marks the value phrase
            if current.words and all(fold(w.lemma) in _locution_heads() for w in current.words):
                # "depois de", "para o início de": head + preposition form one complex preposition
                current = Piece(current.case + tuple(fold(w.lemma) for w in current.words) + (fold(t.lemma),), [])
            elif current.words:
                pieces.append(current)
                current = Piece((fold(t.lemma),), [])
            else:
                current = Piece(current.case + (fold(t.lemma),), [])
            continue
        current.words.append(t)
    if current.words or current.case:
        pieces.append(current)
    return pieces


# -- grounding ------------------------------------------------------------------------------------------------
@dataclass
class World:
    nodes: dict  # id -> {"name", "type", "parent", "index", "children"}
    selection: list
    layer: tuple = ("desktop", "base")

    @classmethod
    def from_document(cls, doc: dict, selection: list, layer=("desktop", "base")) -> "World":
        nodes = {}

        def walk(n, parent, index):
            nodes[n["id"]] = {"name": n.get("name"), "type": n.get("type"), "parent": parent, "index": index,
                              "children": [c["id"] for c in n.get("children", [])],
                              "flags": {k: v for k, v in n.items() if isinstance(v, bool)},
                              "styles": n.get("styles") or {}}
            for i, c in enumerate(n.get("children", [])):
                walk(c, n["id"], i)

        for p in doc.get("pages", []):
            walk(p["tree"], None, 0)
        return cls(nodes, list(selection), tuple(layer))


def _names_in(piece: Piece, world: World) -> list[str]:
    """Node ids whose name the piece mentions (a proper name, an unknown capitalised word, or a quoted literal)."""
    out = []
    texts = [literal_value(t.form) for t in piece.words]
    for nid, n in world.nodes.items():
        name = (n["name"] or "").lower()
        if name and any(x.lower() == name for x in texts):
            out.append(nid)
    return out


def _reference(piece: Piece, world: World, skip: int = 0) -> tuple[list[str], float, list[str], int]:
    """Candidate nodes a piece refers to, with the cost of the assumption, notes, and how many lemmas it explained."""
    seq = piece.lemmas[skip:]
    names = _names_in(piece, world)
    if not names:
        # a proper name (or quoted name) that names no node: the referent does not exist, whatever its type says
        known = {(n["name"] or "").lower() for n in world.nodes.values()}
        for t in piece.words[skip:] if skip < len(piece.words) else []:
            if is_literal(t.form) and t.form[:1] not in "\"'“":
                continue  # an unquoted CSS value ("#ff0000", "24px") is a value, never the name of an element
            if (t.upos == "PROPN" or t.form[:1].isupper() or t.form[:1] in "\"'“") and                     literal_value(t.form).lower() not in known and not lexicon.match((lexicon.lemma_of(t.form),), KINDS):
                return [], COST["referente_nao_resolvido"], [langs.msg("no_such_element", name=literal_value(t.form))], 1
    type_hits = lexicon.match(seq, {"tipo"})
    if not type_hits:
        # the type may come after a name ("the Hero section", "the Intro paragraph")
        for i in range(1, len(seq)):
            type_hits = lexicon.match(seq, {"tipo"}, i)
            if type_hits:
                break
    typ = type_hits[0][0].id if type_hits else None
    type_cost = 0.0
    if typ is None and seq and skip < len(piece.words):
        # a word the catalog does not use for a type ("title" for Heading, "foto" for Image): its meaning in the
        # concept graph
        from . import grounding

        types = [m for m in grounding.meanings(piece.words[skip].form, "N") if m.kind == "tipo" and m.cost <= 1.5]
        # a definite phrase presupposes its referent: among the types the word can mean ("title": header or
        # heading), the one the page has
        present = {v["type"] for v in world.nodes.values()}
        hit = next((m for m in types if m.target in present), types[0] if types else None)
        if hit is not None:
            typ, type_cost = hit.target, hit.cost
            type_hits = [(SimpleNamespace(id=hit.target, lemmas=(seq[0],)), 1)]
    # a node named like its type ("Parágrafo") is named by the very word that gave the type: counted once
    # (the default name is the type's own label in the catalog: "Parágrafo"; a name like "Title" for a heading is a
    # real name, even if it is also a word for the type)
    type_label = lexicon.lemma_seq(_label("tipo", typ)) if typ else ()
    named_by_type = bool(names and type_hits) and all(
        lexicon.lemma_of(world.nodes[n]["name"] or "") in type_label for n in names)
    # words explained: those of the type label and those of the name, each word counted once ("the title Title":
    # two words; "make the title red" with a heading called "Title": one word, "title", is both)
    content = [t for t in piece.words[skip:] if not is_literal(t.form) and t.form.lower() not in lexicon.stop()]
    name_words = {i for i, t in enumerate(content) for n in names
                  if literal_value(t.form).lower() == (world.nodes[n]["name"] or "").lower()}
    type_words = set()
    if type_hits:
        start = next((i for i in range(len(seq)) if lexicon.match(seq, {"tipo"}, i)), 0) if typ else 0
        type_words = set(range(start, start + type_hits[0][1]))
    used_words = name_words | type_words
    explained = (max(used_words) + 1) if used_words else 0
    if named_by_type and len([n for n, v in world.nodes.items() if v["type"] == typ]) > 1:
        names = []  # "o título" with two titles: the default name "Título" does not single one out
    if names:
        cands = [n for n in names if typ is None or world.nodes[n]["type"] == typ]
        if cands:
            return cands, 0.0, [], explained
        return names, COST["tipo_diferente_do_nome"], ["o tipo dito não é o do nome"], explained
    if seq[:1] and seq[0] in PRONOUNS or (not seq and not piece.words):
        if world.selection:
            return list(world.selection), COST["referente_pela_selecao"], ["o que está selecionado"], 1
    if typ:
        of_type = [n for n, v in world.nodes.items() if v["type"] == typ]
        # an ordinal picks one by document order ("o último parágrafo", "the first heading")
        ordinals = langs.profile()["ordinals"]
        said = [ordinals[fold(t.form.lower())] for t in piece.words if fold(t.form.lower()) in ordinals]
        if said and of_type:
            k = said[0]
            if -len(of_type) <= k < len(of_type):
                return [of_type[k]], COST["referente_por_tipo"], [], explained + 1
        if len(of_type) == 1:
            return of_type, COST["referente_por_tipo"] + type_cost, [], explained
        universal = langs.profile()["universal"]
        if len(of_type) > 1 and (any(fold(t.form.lower()) in universal for t in piece.words) or
                                 piece.det and fold(piece.det) in universal):
            return of_type, COST["referente_por_tipo"], [], explained  # "todos os títulos": all of them, asked for
        sel = [n for n in of_type if n in world.selection]
        if len(sel) == 1:
            return sel, COST["referente_por_tipo"], ["o selecionado entre vários"], explained
        if of_type:
            return of_type, COST["referente_ambiguo"], [f"{len(of_type)} candidatos"], explained
    if seq[:1] and seq[0] in {fold(w) for w in FRAMES["campos"] if FRAMES["campos"][w] == "text"}:
        # "o texto" with no owner said: the element that has text, if one stands out (the only one, or the
        # selected one among them)
        _, contents = _property_facts()
        texts = [n for n, v in world.nodes.items() if contents.get(v["type"]) == "text"]
        sel = [n for n in texts if n in world.selection]
        if len(texts) == 1 or len(sel) == 1:
            return (texts if len(texts) == 1 else sel), COST["referente_por_tipo"], ["o elemento de texto"], 1
        if texts:
            return texts, COST["referente_ambiguo"], [f"{len(texts)} elementos de texto"], 1
    return [], COST["referente_nao_resolvido"], ["referente não encontrado"], explained


LITERAL_COST = 2.0


def _literal_cost(pieces: list[Piece], v, prop: str | None = None) -> float:
    """Taking unquoted words that mean something known as a literal value costs (the meaning is likelier), unless
    that meaning is a value of the very property being set ("center" for text-align, "azul" for a color)."""
    if v is None or not isinstance(v[0], str):
        return 0.0
    if prop and (v[0].lower() in values_mod._keywords(prop) or values_mod.translate(v[0], prop)):
        return 0.0
    words = pieces[v[1]].words
    if any(is_literal(t.form) for t in words):
        return 0.0  # quoted or CSS-like: a literal by its form
    lem = pieces[v[1]].lemmas
    meaningful = any(x in value_index() for x in _common_lemmas(pieces[v[1]])) or bool(
        lexicon.match(lem, {"tipo", "propriedade", "atributo", "estado", "breakpoint"}))
    return LITERAL_COST if meaningful else 0.0


def _value_kind(value) -> str:
    v = str(value).strip().lower()
    if v.startswith("#") or re.match(r"(rgb|rgba|hsl|hsla|oklch|lab|lch|color)\(", v) or v in values_mod.named_colors():
        return "color"
    if re.fullmatch(r"-?\d*\.?\d+(px|rem|em|%|vh|vw|vmin|vmax|pt|ch|ex|cm|mm|in|fr|svh|dvh)", v):
        return "length"
    if re.fullmatch(r"-?\d*\.?\d+", v):
        return "number"
    if re.fullmatch(r"[a-z]+(-[a-z]+)*", v):
        return "keyword"
    return "other"


ACCEPTS = {"color": {"color"}, "length": {"length", "number"}, "length-percentage": {"length", "number"},
           "number": {"number"}, "integer": {"number"}, "time": {"length", "number"}, "angle": {"number"},
           "font-family-list": {"keyword", "other"}}  # manifest valueType -> kinds of literal it takes


def _value_fits(prop: str, value) -> bool:
    """Whether a value is of the kind the property takes (manifest valueType; keywords from the W3C grammar). A
    Portuguese value name the property has ("azul" for a color) fits too."""
    ptype = values_mod._builder_properties().get(prop, {}).get("valueType")
    if ptype is None or values_mod.translate(str(value), prop):
        return True
    kind = _value_kind(value)
    if kind == "other":
        return True  # a phrase or a function: the builder judges it when the plan runs
    accepts = ACCEPTS.get(ptype)
    if kind == "keyword":
        allowed = values_mod._keywords(prop)
        return not allowed or value in allowed or values_mod.OPEN in allowed or ptype in ("string", "font-family-list")
    return accepts is None or kind in accepts


def _property_for_value(entity, value):
    """Another property whose label contains the one said ("tamanho da fonte" contains "fonte") and whose declared
    type takes this kind of value (a free-text property does not count); None when there is none or more than one."""
    said = entity.lemmas
    fits = []
    for e in lexicon.load():
        if e.kind != "propriedade" or e.id == entity.id or len(e.lemmas) <= len(said):
            continue
        if any(e.lemmas[i:i + len(said)] == said for i in range(len(e.lemmas) - len(said) + 1)) and \
                _value_kind(value) in ACCEPTS.get(values_mod._builder_properties().get(e.id, {}).get("valueType"), ()):
            if e.id not in [f.id for f in fits]:
                fits.append(e)
    return fits[0] if len(fits) == 1 else None


def _as_keyword(value, prop: str):
    """A Portuguese value name as the CSS keyword it names for the property ("azul" -> "blue"); other values as
    said."""
    if isinstance(value, str) and not is_literal(value):
        k = values_mod.translate(value, prop)
        if k:
            return k
    return value


def _value(pieces: list[Piece], used: set, prop: str | None = None, bare_ok: bool = False,
           cases=None) -> tuple[object, int] | None:
    """A literal value (quoted, CSS-like, number), or a bare word the property declares among its values. With
    `bare_ok` (the property came in a phrase with "em": "coloque relative na posição ..."), the free bare phrase is
    the value as said."""
    for k, p in enumerate(pieces):
        if k in used:
            continue
        for t in p.words:
            if is_literal(t.form):
                return literal_value(t.form), k
    if prop:
        from ..builder.knowledge import load_domains

        allowed = {str(v).lower() for v in load_domains().properties.get(prop, [])}
        for k, p in enumerate(pieces):
            if k in used:
                continue
            for t in p.words:
                if t.form.lower() in allowed:
                    return t.form.lower(), k
    if bare_ok:
        for k, p in enumerate(pieces):
            if k not in used and not p.case and p.words and not lexicon.match(
                    p.lemmas, {"tipo", "propriedade", "atributo", "estado", "breakpoint"}):
                return " ".join(t.form for t in p.words), k
    for k, p in enumerate(pieces):
        if k in used or not p.case or p.case[-1] not in (cases or FRAMES["valor_casos"]) or not p.words:
            continue
        # the words of a "para/como/em ..." phrase that grounds to nothing: the value as said (a CSS keyword, a
        # name). If it is not valid, the builder refuses it when the plan runs: never a silent change.
        # Words that also mean something known (a type, a property, a named CSS value such as "negrito") can
        # still be a literal (a new name "Topo"), but reading them literally costs: when another reading uses their
        # meaning, that reading wins (see LITERAL_COST at the callers).
        phrase = " ".join(t.form for t in p.words)
        if prop is not None and (phrase.lower() in values_mod._keywords(prop) or values_mod.translate(phrase, prop)):
            return phrase, k  # a keyword of the property ("clip"), even if it also names something else
        if prop is not None and lexicon.match(p.lemmas, {"tipo", "propriedade", "atributo", "estado", "breakpoint"}):
            continue
        return phrase, k
    if prop:
        from ..builder.knowledge import load_domains

        allowed = {str(v).lower() for v in load_domains().properties.get(prop, [])}
        for k, p in enumerate(pieces):
            if k in used:
                continue
            for t in p.words:
                if t.form.lower() in allowed:
                    return t.form.lower(), k
    return None


def _OF() -> tuple:  # noqa: N802
    """The language's possessive preposition ("de"; "of"): "a cor do texto", "the color of the text"."""
    return (langs.profile().get("of", "de"),)


def _case_words() -> set:
    """The language's value and place markers ("para", "como"; "to", "as", "in"): a word the tagger read otherwise
    ("to" as an infinitive particle, "para" before a verb) still opens an argument."""
    out = {fold(w) for w in FRAMES["valor_casos"]}
    for phrases in FRAMES["locais"].values():
        out |= {fold(ph.split()[0]) for ph in phrases}
    return out


def _locution_heads() -> set:
    return _locution_heads_for(langs.current())


@lru_cache(maxsize=4)
def _locution_heads_for(lang: str) -> set:
    """The non-preposition words of the place phrases in frames.json ("depois", "início", "dentro", ...)."""
    preps = {"em", "de", "para", "a", "o", "in", "of", "to", "at", "the", "a"}
    return {w for phrases in FRAMES["locais"].values() for ph in phrases for w in lexicon.lemma_seq(ph)
            if w not in preps}


def _locais() -> dict:
    out = {}
    for kind, phrases in FRAMES["locais"].items():
        for ph in phrases:
            out[lexicon.lemma_seq(ph)] = kind
    return out


def _place(case: tuple, piece: Piece) -> tuple[str | None, int]:
    """Which kind of place a piece names ("dentro", "depois", ...) from its case and leading nouns."""
    locais = _locais()
    seq = case + piece.lemmas
    best = (None, 0)
    for phrase, kind in locais.items():
        n = len(phrase)
        if seq[:n] == phrase and n > best[1]:
            best = (kind, n)
    consumed_in_words = max(0, best[1] - len(case))
    return best[0], consumed_in_words


def _layer(pieces: list[Piece], used: set, world: World) -> tuple[str, str, dict, dict]:
    """The breakpoint and style state a style is for: labels found anywhere in the pieces ("no tablet", "no estado
    foco", "ao passar o mouse", or left at the end of the value phrase). Returns the pieces it takes, with how many
    of their lemmas the label explains (up to its end: words after it, "... no estado ativo e também o fundo", are
    still to be explained), and, for pieces already in use, how many extra lemmas the layer explained."""
    bp, st = world.layer
    more: dict[int, int] = {}
    extra: dict[int, int] = {}
    for k, p in enumerate(pieces):
        seq = p.case + p.lemmas if k not in used else p.lemmas
        for start in range(len(seq)):
            hits = lexicon.match(seq, {"breakpoint", "estado"}, start)
            if not hits:
                continue
            e, n = hits[0]
            if e.kind == "breakpoint":
                bp = e.id
            else:
                st = e.id
            if k in used:
                extra[k] = extra.get(k, 0) + n + (1 if start > 0 and seq[start - 1] == "estado" else 0)
            else:
                more[k] = max(0, start + n - len(p.case))
            break
    return bp, st, more, extra


def _readings(tokens: list[Token], world: World) -> list[Reading]:
    pred = _predicate(tokens)
    if pred is None:
        return []
    k = tokens.index(pred)
    if k + 1 < len(tokens) and fold(pred.form.lower()) in value_index():
        nxt = tokens[k + 1]
        lemma = (morph_lemmas(nxt.form, "V") or [nxt.form.lower()])[0]
        if any(_in_frame(lemma, f) for f in FRAMES["quadros"] if f.get("valor_rotulado")):
            # "left align the button": the tagger read "left" as a verb; a value word before a verb of setting a
            # value is the compound's modifier, and the next word is the verb
            pred.upos, pred.deprel, pred.head = "ADJ", "advmod", nxt.i
            nxt.upos, nxt.lemma, nxt.head, nxt.deprel = "VERB", lemma, 0, "root"
            for t in tokens:
                if t.head == pred.i and t is not nxt:
                    t.head = nxt.i
            pred = nxt
    _multiword_verb(tokens, pred)
    out = _readings_for(tokens, pred, world)
    # a homograph ("some": somar / sumir) is read with each of its lemmas: the reading that explains the sentence
    # best decides which verb it was
    original = pred.lemma
    for alt in pred.alts:
        if " " in original:
            break
        pred.lemma = alt
        out += _readings_for(tokens, pred, world)
    pred.lemma = original
    out.sort(key=lambda r: (r.cost, r.frame))
    return out


def _readings_for(tokens: list[Token], pred: Token, world: World) -> list[Reading]:
    pieces = _pieces(tokens, pred)
    if pred.lemma in COPULAS or pred.lemma in MODALS:
        # "o título tem que ficar vermelho", "quero o título sublinhado": the request is a state of an element;
        # the subject before the verb is the element
        before = [t for t in tokens if t.i < pred.i and t.upos not in ("PUNCT", "DET", "ADP", "AUX", "VERB")
                  and t.lemma not in MODALS and t.upos != "PRON"]
        subject = [Piece((), before)] if before else []
        value_frame = next(f for f in FRAMES["quadros"] if f.get("valor_rotulado"))
        rs = _value_readings(value_frame, subject + pieces, world)
        for r in rs:
            r.verb = pred.lemma
        return rs + _light_verb_readings(pred, pieces, world)
    out: list[Reading] = []
    frames = [f for f in FRAMES["quadros"] if _in_frame(pred.lemma, f)]
    base_cost = 0.0
    if not frames:
        frames = FRAMES["quadros"]
        base_cost = COST["verbo_fora_do_quadro"]
    from . import preferences

    extra = _command_readings(pred.lemma, pieces, world, in_frame=not base_cost)
    if base_cost:
        extra += _verb_value_readings(pred.lemma, pieces, world)
        extra += _dictionary_readings(pred.lemma, pieces, world)
    for r in extra:
        r.verb = pred.lemma
        out.append(r)
    for r in _comparative_readings(tokens, pred, pieces, world):
        r.verb = pred.lemma
        out.append(r)
    if any(f["id"] == "remover" for f in frames):
        for r in _value_removal_readings(pieces, world):
            r.verb = pred.lemma
            out.append(r)
    if any(f["id"] == "estilo" for f in frames):
        for r in _family_readings(pieces, world):
            r.verb = pred.lemma
            r.cost += base_cost
            r.unknown_verb = bool(base_cost)
            if base_cost:
                r.assumptions.insert(0, f"o verbo '{pred.lemma}' não está no quadro 'estilo'")
            out.append(r)
    for f in frames:
        for r in _frame_readings(f, pieces, world):
            r.verb = pred.lemma
            r.cost += base_cost + preferences.penalty(pred.lemma, f["id"])  # readings the user keeps undoing
            if base_cost:
                r.unknown_verb = True
                r.assumptions.insert(0, f"o verbo '{pred.lemma}' não está no quadro '{f['id']}'")
            out.append(r)
    # constructions carry meaning of their own, whatever the verb (Goldberg 1995): verb + object + destination
    # is caused motion ("joga o botão pro começo da seção"); verb + new element + place is putting it there
    # ("joga um botão no fim"). For verbs whose own frames are not these; they compete with the other readings.
    for f in FRAMES["quadros"]:
        if f["id"] not in ("mover", "existir") or f in frames and not base_cost:
            continue
        for r in _frame_readings(f, pieces, world):
            placed = any(c.get("parent") for c in r.constraints)
            if not placed or (f["id"] == "existir" and any(c.get("parent") is None for c in r.constraints)):
                continue
            if f["id"] == "existir" and "artigo definido para algo novo" in r.assumptions:
                continue  # putting something new needs it said as new ("um botão", "another button")
            r.verb = pred.lemma
            r.cost += COST["construcao"]
            r.assumptions.insert(0, f"construção: verbo + objeto + lugar ({f['id']})")
            out.append(r)
    if not out or min(r.cost for r in out) > LIMIT or all(r.unknown_verb for r in out):
        out += _light_verb_readings(pred, pieces, world)
        if not base_cost:
            # a known verb whose frames do not fit the sentence ("joga o botão pro começo": jogar is listed for
            # styles): its other meanings, through the concept graph
            for r in _dictionary_readings(pred.lemma, pieces, world):
                r.verb = pred.lemma
                out.append(r)
    out.sort(key=lambda r: (r.cost, r.frame))
    return out


def _light_verb_readings(pred: Token, pieces: list[Piece], world: World) -> list[Reading]:
    """ "faz uma cópia do botão": a verb that adds little ("fazer", "dar") and a noun that names the action
    ("cópia" -> copiar -> duplicar): the noun's action applied to the element after "de"."""
    from . import grounding

    out = []
    for k, p in enumerate(pieces):
        if p.case or not p.words:
            continue
        noun = p.words[0].form
        if _span_match(pieces, k, {"tipo", "propriedade"}) is not None:
            continue  # the noun begins the label of a type or property ("bloco de link"): it is not the action
        actions = [m for m in grounding.meanings(noun, "N") if m.kind in ("comando", "acao")]
        if not actions:
            # the noun's own verb (derivation in the dictionary: "cópia" <- "copiar")
            from . import dictionary

            for g in dictionary.gloss_words(noun, "N")[:6]:
                if morph_lemmas(g, "V"):
                    actions += [m for m in grounding.meanings(morph_lemmas(g, "V")[0], "V")
                                if m.kind in ("comando", "acao")]
        if not actions:
            continue
        rest = pieces[:k] + [Piece((), q.words, q.det) if q.case[:1] == _OF() and i == k + 1 else q
                             for i, q in enumerate(pieces) if i > k]
        for r in _dictionary_readings(noun, rest, world, actions):
            r.verb = pred.lemma
            r.cost += 0.5
            r.assumptions.insert(0, f"«{pred.lemma} {noun}» = a ação de «{noun}»")
            out.append(r)
    return out


KINDS = {"tipo", "propriedade", "atributo", "estado", "breakpoint"}


COMPARATIVE_STEP = 1.25  # "maior" / "bigger" without a number: one step of the usual type scale (major third)


def _comparative_readings(tokens: list[Token], pred: Token, pieces: list[Piece], world: World) -> list[Reading]:
    """ "deixe a fonte do título maior", "make the title bigger", "aumente a margem da seção": a change of amount
    without a number. The new value is computed from the element's current value (one step up or down); when the
    document does not say what it is, there is nothing to compute from, and the reading asks for the number."""
    prof = langs.profile()
    words = {fold(t.form.lower()) for t in tokens} | {fold(pred.lemma)}
    more, less = bool(words & prof["more"]), bool(words & prof["less"])
    if more == less or any(is_literal(t.form) for t in tokens):
        return []
    factor = COMPARATIVE_STEP if more else 1 / COMPARATIVE_STEP
    out = []
    for k, p in enumerate(pieces):
        span = _span_match(pieces, k, {"propriedade"}) if p.lemmas else None
        candidates = []
        if span is not None:
            candidates = [span[0].id]
            explained_k = span[1]
            numeric = ("length", "length-percentage", "number", "integer")
            types = values_mod._builder_properties()
            if types.get(span[0].id, {}).get("valueType") not in numeric:
                # "a fonte maior": an amount of that family ("tamanho da fonte"), not the typeface
                said = span[0].lemmas
                alt = [e.id for e in lexicon.load() if e.kind == "propriedade" and e.id != span[0].id and
                       any(e.lemmas[i:i + len(said)] == said for i in range(len(e.lemmas))) and
                       types.get(e.id, {}).get("valueType") in numeric]
                candidates = alt[:1] or candidates
        for j, q in enumerate(pieces):
            if j == k and span is None:
                ref, c, notes, ex = _reference(q, world)
            elif j != k and (q.case[:1] == _OF() or span is None):
                ref, c, notes, ex = _reference(q, world)
            else:
                continue
            if len(ref) != 1:
                continue
            node = ref[0]
            props = candidates or (["font-size"] if _property_facts()[1].get(world.nodes[node]["type"]) == "text"
                                   else ["width"])
            prop = props[0]
            current = ((world.nodes[node].get("styles") or {}).get(world.layer[0]) or {}).get(world.layer[1], {}).get(prop)
            m = re.fullmatch(r"(-?\d+(?:\.\d+)?)(px|rem|em|%)", str(current or ""))
            used = {j} | ({k} if span is not None else set())
            explained = {j: ex, **({k: explained_k} if span is not None else {})}
            cost = c + _unexplained(pieces, used, explained) - sum(
                1.0 for q2 in pieces for t in q2.words if fold(t.form.lower()) in prof["more"] | prof["less"])
            if m is None:
                r = Reading("estilo", [], max(cost, 0.0), [f"{_label('propriedade', prop)}: sem valor atual"], "")
                r.ask_value = (node, prop)
                out.append(r)
                continue
            n, unit = float(m.group(1)), m.group(2)
            new = round(n * factor, 2 if unit in ("rem", "em") else 0)
            value = f"{int(new) if unit in ('px', '%') else new}{unit}"
            cons = [{"kind": "style", "id": node, "breakpoint": world.layer[0], "state": world.layer[1],
                     "property": prop, "value": value}]
            out.append(Reading("estilo", cons, max(cost, 0.0), [f"{current} → {value}"], paraphrase(cons, world)))
            break
    return out


def _value_removal_readings(pieces: list[Piece], world: World) -> list[Reading]:
    """ "tira o negrito do título", "remove the bold from the title": a removal verb whose object names a value;
    the element's property goes back to its normal value."""
    out = []
    for k, p in enumerate(pieces):
        if p.case or not p.words:
            continue
        pairs = [pv for lem in _common_lemmas(p) for pv in value_index().get(lem, [])]
        if not pairs:
            continue
        for j, q in enumerate(pieces):
            if j == k or not q.case:
                continue
            ref, c, notes, ex = _reference(q, world)
            if len(ref) != 1:
                continue
            node = ref[0]
            best = min(pairs, key=lambda pv: _prior(pv[0], world.nodes[node]["type"]))
            prop = best[0]
            reset = "normal" if "normal" in values_mod._keywords(prop) else "initial"
            cons = [{"kind": "style", "id": node, "breakpoint": world.layer[0], "state": world.layer[1],
                     "property": prop, "value": reset}]
            cost = c + _prior(prop, world.nodes[node]["type"]) + _unexplained(pieces, {k, j}, {k: len(p.lemmas),
                                                                                                j: ex})
            out.append(Reading("remover", cons, cost, list(notes), paraphrase(cons, world)))
            break
    return out


def _family_readings(pieces: list[Piece], world: World) -> list[Reading]:
    """ "mude a cor do título para #ff0000": "cor" labels no property alone but heads a family of them (cor do texto,
    cor de fundo, cor da borda...). The element and the value say which one: the properties of the family that take
    the value, weighed by how likely each is for that element (``_prior``)."""
    from . import grounding

    types = values_mod._builder_properties()
    readings = []
    for k, p in enumerate(pieces):
        if p.case or not p.lemmas:
            continue
        family = next((m.target for m in grounding.direct(p.words[0].form) if m.kind == "familia"), None)
        if family is None or any(n == len(p.lemmas[:1]) for _, n in lexicon.match(p.lemmas[:1], {"propriedade"})):
            continue  # no family, or the word alone is a property's label ("altura")
        for j, q in enumerate(pieces):
            if j == k or q.case[:1] != _OF():
                continue
            ref, c, notes, ex = _reference(q, world)
            if not ref:
                continue
            node = ref[0]
            used, explained = {k, j}, {k: 1, j: ex}
            v = _value(pieces, used)
            if v is None:
                continue
            used.add(v[1])
            explained[v[1]] = len(pieces[v[1]].lemmas)
            for prop, info in types.items():
                # the value must be of the family's kind by its form (a color, a length) or be a keyword or a
                # Portuguese value name of the property: a free phrase says nothing about which property
                kind = _value_kind(v[0])
                typed = kind in ACCEPTS.get(family, ()) and kind != "other" or                     str(v[0]).lower() in values_mod._keywords(prop) or values_mod.translate(str(v[0]), prop)
                if info.get("valueType") != family or not typed or not _value_fits(prop, v[0]):
                    continue
                value = _as_keyword(v[0], prop)
                cons = [{"kind": "style", "id": node, "breakpoint": world.layer[0], "state": world.layer[1],
                         "property": prop, "value": value}]
                cost = c + 0.5 + _prior(prop, world.nodes[node]["type"]) + _unexplained(pieces, used, explained)
                readings.append(Reading("estilo", cons, cost, list(notes), paraphrase(cons, world),
                                        ambiguous=ref if len(ref) > 1 else []))
            break
    return readings


def _dictionary_readings(lemma: str, pieces: list[Piece], world: World, given=None) -> list[Reading]:
    """A verb the system does not know, read through what the dictionary says it means (``grounding``): a synonym
    that is a known verb or command ("esconder" ~ "ocultar"), a translation that is a value ("sublinhar" ->
    underline), or the property family its definition names ("pintar: aplicar ... uma cor" -> a color property).
    Each meaning gives the readings it allows for this sentence; abduction then weighs them against everything the
    sentence says ("pinte o título de vermelho": only the color meaning explains "vermelho")."""
    from . import grounding

    out: list[Reading] = []
    value_frame = next(f for f in FRAMES["quadros"] if f.get("valor_rotulado"))
    meanings = list(grounding.meanings(lemma, "V") if given is None else given)
    for m in meanings:
        rs: list[Reading] = []
        if m.kind == "comando":
            import dataclasses

            verbs = [cv for vs in command_verbs.table().values() for cv in vs if cv.command == m.target]
            # reached through its meaning ("subir" ~ "move up"), the label's rest is already said by the verb
            verbs = [dataclasses.replace(cv, rest=()) for cv in verbs[:1]]
            rs = _command_readings(lemma, pieces, world, in_frame=False, verbs=verbs)
        elif m.kind == "acao":
            rs = [r for f in FRAMES["quadros"] if f["id"] == m.target for r in _frame_readings(f, pieces, world)]
        elif m.kind == "verbo":
            for f in FRAMES["quadros"]:
                if _in_frame(m.target, f):
                    rs += _frame_readings(f, pieces, world)
            rs += _command_readings(m.target, pieces, world, in_frame=_in_frame(m.target))
        elif m.kind == "valor":
            # the verb is the value's own word ("underline"): direct, not inferred
            rs = _verb_value_readings(lemma, pieces, world, pairs=[m.target], inferred=bool(m.path))
        elif m.kind in ("familia", "propriedade"):
            # a verb that means a property ("pintar" -> a color property) means changing a property of that kind:
            # the sentence's value says which one, and the element's kind which property of the family
            types = values_mod._builder_properties()
            family = m.target if m.kind == "familia" else types.get(m.target, {}).get("valueType")
            for r in _value_readings(value_frame, pieces, world):
                prop = r.constraints[0].get("property")
                if types.get(prop, {}).get("valueType") == family:
                    rs.append(r)
        if m.kind == "valor" and any(o.kind in ("comando", "acao") and o.cost <= m.cost + 1.0 for o in meanings):
            for r in rs:
                r.cost += 1.0  # "throw away": the action is a likelier meaning of a verb than a keyword it matches
        for r in rs:
            r.cost += m.cost + COST["significado_pelo_dicionario"]
            r.assumptions.insert(0, m.explain(lemma))
            # a synonym or a translation is near; a chain through definitions to a secondary property is not
            props = values_mod._builder_properties()
            prop = r.constraints[0].get("property") if r.constraints else None
            # the value itself came from a chain of definitions, and nothing else in the sentence says it
            # ("arredonde o botão": "tornar redondo" -> round): confirm. A value the sentence says ("pinte ... de
            # vermelho") or a synonym/translation of a known action is corroborated.
            r.uncertain = m.kind == "valor" and any(how == "definicao" for how, _ in m.path) or                 (m.cost > 1.0 and bool(prop) and not props.get(prop, {}).get("essential"))
        out += rs
    return out


def _unexplained(pieces: list[Piece], used: set, partial: dict) -> float:
    """Each word no part of the reading explains costs; a word that names something the builder knows (a state, a
    property, a type, a value such as "vermelho") costs more, because leaving it out would silently drop part of
    what was asked."""
    cost = 0.0
    for k, p in enumerate(pieces):
        lem = p.lemmas
        start = partial.get(k, len(lem)) if k in used else 0
        rest = lem[start:]
        common = [not (t.i > 1 and t.form[:1].isupper()) for t in p.words
                  if not is_literal(t.form) and t.form.lower() not in lexicon.stop()][start:]
        if k not in used and not lem and p.words:
            cost += COST["palavra_sem_explicacao"]
        for i in range(len(rest)):
            named = bool(lexicon.match(tuple(rest), KINDS, i)) or                 (i < len(common) and common[i] and rest[i] in value_index())
            cost += COST["palavra_com_significado_ignorada"] if named else COST["palavra_sem_explicacao"]
    return cost


@lru_cache(maxsize=1)
def _property_facts() -> dict:
    """property -> (appliesTo, essential), and element type -> content kind, from the builder's manifest."""
    import json as _json

    from ..builder.client import DEFAULT_BUILDER

    man = pathlib.Path(DEFAULT_BUILDER) / "manifest"
    props = _json.loads((man / "properties.json").read_text(encoding="utf-8"))["properties"]
    elements = _json.loads((man / "elements.json").read_text(encoding="utf-8"))["elements"]
    return ({p["id"]: (p.get("appliesTo", "always"), bool(p.get("essential"))) for p in props},
            {e["id"]: e.get("content") for e in elements})


def _value_candidates(piece: Piece, node_type: str | None) -> list[tuple[str, str, float]]:
    """(property, value, cost) for a phrase that names a CSS value in Portuguese ("à direita", "em negrito"), by the
    value lexicon induced from MDN; cheaper when the property applies to the element and is an essential one."""
    return [(prop, value, _prior(prop, node_type)) for lem in _common_lemmas(piece)
            for prop, value in value_index().get(lem, [])]


def _participle_commands(piece: Piece) -> list:
    """Commands whose verb has the piece's only word as its participle ("escondidas" <- esconder -> Ocultar)."""
    words = [t for t in piece.words if not is_literal(t.form)]
    if len(words) != 1:
        return []
    form = words[0].form.lower()
    if langs.current() == "pt":
        from .morph import analyses

        verbs = [lem for lem, tags in analyses(form) if tags.startswith("V+PTPST")]
    else:
        verbs = [langs.english_lemma(form, "VERB")] if form.endswith(("ed", "en", "den")) else []
    out = []
    for v in verbs:
        out += [cv for cv in command_verbs.table().get(v, []) if not cv.rest]
    return out[:1]


def _value_words(piece: Piece, prop: str, value: str) -> int:
    """How many lemmas of a value phrase this (property, value) explains: the words naming the value, and the
    property's own label if the phrase says it ("com fundo preto": "fundo" labels background-color, not color)."""
    lem = piece.lemmas
    n = sum(1 for x in lem if (prop, value) in value_index().get(x, []))
    for e in lexicon.load():
        if e.kind == "propriedade" and e.id == prop and e.lemmas and                 any(lem[i:i + len(e.lemmas)] == e.lemmas for i in range(len(lem) - len(e.lemmas) + 1)):
            n += len(e.lemmas)
            break
    return min(n, len(lem))


def _common_lemmas(piece: Piece) -> tuple:
    """The lemmas of the piece's common words: a capitalized word inside the sentence is part of a name ("Café
    Serra"), never the name of a CSS value."""
    return tuple(lexicon.lemma_of(t.form) for t in piece.words
                 if not is_literal(t.form) and t.form.lower() not in lexicon.stop()
                 and not (t.i > 1 and t.form[:1].isupper()))


def _prior(prop: str, node_type: str | None) -> float:
    """How unlikely a property is as the meaning for this element: the builder shows essential properties first;
    a property that does not apply to the element's content (a text property on a section) is unlikely; and on a
    text element, a property of any element is less specific than one of text ("o título branco": the text's
    color, not the background)."""
    props, contents = _property_facts()
    applies, essential = props.get(prop, ("always", False))
    cost = 0.0 if essential else 1.0
    if applies == "text" and contents.get(node_type) != "text":
        cost += 3.0
    elif applies == "always" and contents.get(node_type) == "text":
        cost += 1.0
    elif applies == "hasBox":
        cost += 0.5
    elif applies not in ("always", "text"):
        # applies only under a layout the element may not have (a flex or grid container, a positioned box...):
        # unlikely unless the request says so
        cost += 2.0
    return cost


def _descends(node: str, ancestor: str, world: World) -> bool:
    n = world.nodes[node]["parent"]
    while n is not None:
        if n == ancestor:
            return True
        n = world.nodes[n]["parent"]
    return False


def _within(ref: list, pieces: list[Piece], k: int, world: World) -> tuple[list, dict]:
    """Several candidates, and the next phrase names where the one meant is ("o título do CardA", "the heading in
    the Plans section"): only the candidates inside that element. Returns the candidates and the phrase it used."""
    if len(ref) <= 1 or k + 1 >= len(pieces):
        return ref, {}
    q = pieces[k + 1]
    kind, skip = _place(q.case, q) if q.case else (None, 0)
    if q.case[:1] != _OF() and kind != "dentro":
        return ref, {}
    container, _, _, ex = _reference(q, world, skip if kind == "dentro" else 0)
    if len(container) != 1:
        return ref, {}
    inside = [n for n in ref if _descends(n, container[0], world)]
    if not inside or len(inside) == len(ref):
        return ref, {}
    return inside, {k + 1: (skip if kind == "dentro" else 0) + ex}


def _objects(pieces: list[Piece], world: World):
    """(piece index, candidate nodes, cost, notes, lemmas explained, other phrases used) for each phrase that can be
    the object."""
    for k, p in enumerate(pieces):
        if p.case and not (len(p.case) == 1 and p.case[0] in ARTICLE_FORMS):
            continue
        ref, c, notes, ex = _reference(p, world)
        if ref:
            narrowed, extra = _within(ref, pieces, k, world)
            if extra:
                ref, c = narrowed, (COST["referente_por_tipo"] if len(narrowed) == 1 else c)
            yield k, ref, c, list(notes), ex, extra


def _verb_value_readings(lemma: str, pieces: list[Piece], world: World, pairs=None, inferred: bool = True
                         ) -> list[Reading]:
    """ "centralize o parágrafo", "justifique o texto": a verb whose participle names a value ("centralizado"),
    applied to the element the sentence names."""
    pairs = _verb_value_pairs(lemma) if pairs is None else pairs
    readings = []
    for k, ref, c, notes, ex, extra in _objects(pieces, world) if pairs else ():
        node = ref[0]
        for prop, value in pairs:
            used, explained = {k} | set(extra), {k: ex, **extra}
            bp, st, more, extra = _layer(pieces, used, world)
            used |= set(more)
            for m in more:
                explained[m] = more[m]
            # a meaning inferred through a translation or a participle is weaker evidence than a frame or the
            # builder's own label for the action
            cost = COST["significado_inferido"] * inferred + c + _prior(prop, world.nodes[node]["type"]) +                 _unexplained(pieces, used, explained)
            cons = [{"kind": "style", "id": node, "breakpoint": bp, "state": st, "property": prop, "value": value}]
            r = Reading("estilo_por_verbo", cons, cost, notes, paraphrase(cons, world),
                        ambiguous=ref if len(ref) > 1 else [])
            # the verb is the only evidence for the value: when that rests on one dictionary translation alone
            # ("arredondado" <- "round"), confirm before acting
            word = PARTICIPLE_WORD.get((lemma, prop, value))
            r.uncertain = word is not None and values_mod.only_translated(word, prop, value)
            readings.append(r)
    return readings


def _command_readings(lemma: str, pieces: list[Piece], world: World, in_frame: bool, verbs=None) -> list[Reading]:
    """ "duplique o botão", "oculte o parágrafo", "mova o título para cima": a verb that labels a builder command
    (``command_verbs``) applied to the element the sentence names. The rest of the label must be said too. A verb
    that also has a frame only takes the commands whose label says more than the verb ("Mover para cima")."""
    readings = []
    for cv in (command_verbs.table().get(lemma, []) if verbs is None else verbs):
        if in_frame and not cv.rest:
            continue
        for k, ref, c, notes, ex, extra in _objects(pieces, world):
            used, explained = {k} | set(extra), {k: ex, **extra}
            if cv.rest:
                j = next((j for j, q in enumerate(pieces) if j != k and (q.case + q.lemmas)[:len(cv.rest)] == cv.rest),
                         None)
                if j is not None:
                    used.add(j)
                    explained[j] = len(pieces[j].lemmas)
                elif pieces[k].lemmas[ex:ex + len(cv.rest)] == cv.rest:
                    explained[k] = ex + len(cv.rest)  # said at the end of the object's phrase ("the paragraph up")
                else:
                    continue
            node = ref[0]
            already = bool(cv.flag) and world.nodes[node].get("flags", {}).get(cv.flag) is True
            cons = [{"kind": "command", "command": cv.command, "id": node, "label": cv.label, "already": already}]
            cost = c + _unexplained(pieces, used, explained)
            readings.append(Reading(f"comando:{cv.command}", cons, cost, notes, paraphrase(cons, world),
                                    ambiguous=ref if len(ref) > 1 else []))
    return readings


def _frame_readings(f: dict, pieces: list[Piece], world: World) -> list[Reading]:
    if f.get("valor_rotulado"):
        return _value_readings(f, pieces, world)
    extra = _naming_readings(f, pieces, world) if f["resultado"] == "field:name" and f["objeto"] == "no" else []
    return extra + _frame_readings_core(f, pieces, world)


def _naming_readings(f: dict, pieces: list[Piece], world: World) -> list[Reading]:
    """ "call the section Intro", "chame a seção Destaque": the new name follows the element with no preposition
    (two objects); the last name-like word is the name, the words before it are the element."""
    out = []
    for k, p in enumerate(pieces):
        if p.case or len(p.words) < 2:
            continue
        last = p.words[-1]
        if not (last.form[:1].isupper() or is_literal(last.form)):
            continue
        head = Piece((), p.words[:-1], p.det)
        ref, c, notes, ex = _reference(head, world)
        if len(ref) != 1:
            continue
        cons = [{"kind": "field", "id": ref[0], "field": "name", "value": literal_value(last.form)}]
        cost = c + 0.5 + _unexplained(pieces, {k}, {k: len(p.lemmas)})
        out.append(Reading(f["id"], cons, cost, list(notes), paraphrase(cons, world)))
    return out


def _frame_readings_core(f: dict, pieces: list[Piece], world: World) -> list[Reading]:
    obj_kind = f["objeto"]
    readings = []
    for k, p in enumerate(pieces):
        cost, notes, used, explained = 0.0, [], {k}, {}
        amb: list = []  # candidates of any referent that was not unique: such a reading is asked, never executed
        if p.case:
            if len(p.case) == 1 and p.case[0] in ARTICLE_FORMS:
                cost += COST["artigo_como_preposicao"]  # the tagger's "a" (preposition) read as the article
                notes.append(f"'{p.case[0]}' lido como artigo")
            elif obj_kind == "no":
                cost += COST["objeto_com_preposicao"]
            elif obj_kind == "propriedade" and p.case == ("em",):
                cost += COST["valor_primeiro"]  # "coloque 24px na margem direita": the value is the bare phrase
            else:
                continue  # the object of these frames is a bare phrase
        det = p.det or (p.case[0] if len(p.case) == 1 and p.case[0] in ARTICLE_FORMS else None)
        constraints = []
        if obj_kind == "literal":
            # "escreva Olá no parágrafo": the object is the text itself, the element is where it goes
            if p.case or not p.words:
                continue
            literal = next((literal_value(t.form) for t in p.words if is_literal(t.form)), None)
            value = literal if literal is not None else " ".join(t.form for t in p.words)
            explained[k] = len(p.lemmas)
            target = None
            for j, q in enumerate(pieces):
                if j == k or not q.case:
                    continue
                kind, skip = _place(q.case, q)
                if kind != "dentro":
                    continue
                ref, c, n, ex = _reference(q, world, skip)
                if ref:
                    amb = ref if len(ref) > 1 else amb
                    target, cost, notes = ref[0], cost + c, notes + n
                    used.add(j)
                    explained[j] = skip + ex
                    break
            if target is None:
                continue
            constraints.append({"kind": "field", "id": target, "field": "text", "value": value})
        elif obj_kind == "tipo":
            # a type's label may go on across a preposition ("bloco | de link")
            span = _span_match(pieces, k, {"tipo"})
            if span is None and len(p.lemmas) > 1:
                # the type after adjectives ("a new button", "um outro botão"): found anywhere in the phrase
                for i in range(1, len(p.lemmas)):
                    hits = lexicon.match(p.lemmas, {"tipo"}, i)
                    if hits and i + hits[0][1] == len(p.lemmas):
                        span = (hits[0][0], len(p.lemmas), [])
                        break
            from . import grounding

            if span is None and p.words and not lexicon.match(p.lemmas[:1], {"propriedade"}) and                     not any(m.kind in ("familia", "propriedade") for m in grounding.direct(p.words[0].form)):
                # (a word that names properties, "margem", is never an element type)
                hit = next((m for m in grounding.meanings(p.words[0].form, "N") if m.kind == "tipo" and m.cost <= 1.5),
                           None)
                if hit is not None:
                    span = (SimpleNamespace(id=hit.target), 1, [])
                    cost += hit.cost
            if span is None:
                continue
            entity, length, whole = span
            typ = entity.id
            # newness words ("novo", "outro", "new", "another") belong to the insertion
            newness = sum(1 for t in p.words if fold(t.form.lower()) in langs.profile()["new"])
            explained[k] = min(len(p.lemmas), length + newness)
            for j in whole:
                used.add(j)
                explained[j] = len(pieces[j].lemmas)
            if det in DEFINITE:
                # a definite phrase presupposes its referent (DRT): "o título" when a title exists is that title,
                # not a new one
                existing = any(n["type"] == typ for n in world.nodes.values())
                cost += COST["definido_com_referente" if existing else "definido_para_novo"]
                notes.append("artigo definido para algo novo")
            extras = _insert_extras(pieces, k, used, explained)
            parent = index = None
            place_found = False
            for j, q in enumerate(pieces):
                if j == k or not q.case:
                    continue
                kind, skip = _place(q.case, q)
                if kind is None:
                    continue
                ref, c, n, ex = _reference(q, world, skip)
                if not ref:
                    continue
                if len(ref) > 1:
                    amb = ref
                node = ref[0]
                cost += c
                notes += n
                used.add(j)
                explained[j] = skip + ex
                place_found = True
                parent, index = _placement(kind, node, world)
                break
            if not place_found:
                said = any(q.case and _place(q.case, q)[0] is not None for j, q in enumerate(pieces) if j != k)
                if said:
                    # a place was said ("after the title") but names no element: never insert elsewhere
                    cost += COST["referente_nao_resolvido"]
                    notes.append("o lugar dito não foi encontrado")
                else:
                    cost += COST["local_ausente"]
                    notes.append("sem local: onde o editor puser")
            constraints.append({"kind": "added", "type": typ, "parent": parent, "index": index, **extras})
        elif obj_kind in ("no",):
            if any(fold(t.form.lower()) in langs.profile()["new"] for t in p.words) or \
                    p.det and fold(p.det) in langs.profile()["new"]:
                continue  # "um botão novo", "another button": an element that does not exist yet
            ref, c, n, ex = _reference(p, world)
            if not ref:
                continue
            narrowed, extra = _within(ref, pieces, k, world)
            if extra and f["resultado"] != "moved":  # (a move's place phrase is its destination, not a restriction)
                ref, c = narrowed, (COST["referente_por_tipo"] if len(narrowed) == 1 else c)
                for j, n_ in extra.items():
                    used.add(j)
                    explained[j] = n_
            if len(ref) > 1:
                amb = ref
            if det in INDEFINITE:
                cost += COST["indefinido_para_existente"]
                notes.append("artigo indefinido para algo que já existe")
            cost += c
            notes += n
            explained[k] = ex
            node = ref[0]
            if f["resultado"] == "removed":
                constraints.append({"kind": "removed", "id": node})
            elif f["resultado"] == "moved":
                target = None
                for j, q in enumerate(pieces):
                    if j == k or not q.case:
                        continue
                    kind, skip = _place(q.case, q)
                    if kind is None:
                        continue
                    r2, c2, n2, ex2 = _reference(q, world, skip)
                    if r2 and len(r2) > 1:
                        amb = r2
                    if r2 and r2[0] != node:
                        target = (kind, r2[0])
                        cost += c2
                        notes += n2
                        used.add(j)
                        explained[j] = skip + ex2
                        break
                if target is None:
                    continue
                parent, index = _placement(target[0], target[1], world, moving=node)
                constraints.append({"kind": "moved", "id": node, "parent": parent, "index": index})
            elif f["resultado"] == "field:name":
                v = _value(pieces, used, cases=f.get("valor_casos") if langs.current() == "pt" else None)
                cost += _literal_cost(pieces, v)
                if v is None:
                    cost += COST["valor_ausente"]
                    notes.append("falta o novo nome")
                else:
                    used.add(v[1])
                    explained[v[1]] = len(pieces[v[1]].lemmas)
                    constraints.append({"kind": "field", "id": node, "field": "name", "value": v[0]})
        else:  # propriedade | atributo | campo:<x>
            kinds = {"propriedade"} if obj_kind == "propriedade" else {"atributo"} if obj_kind == "atributo" else None
            compound_owner = None
            if kinds:
                span = _span_match(pieces, k, kinds)
                if span is None and obj_kind == "propriedade" and len(p.lemmas) > 1:
                    # "the title font size": the property's label after the element it belongs to
                    for i in range(1, len(p.lemmas)):
                        hits = lexicon.match(p.lemmas, kinds, i)
                        if hits and i + hits[0][1] == len(p.lemmas):
                            ref_o = _reference(Piece((), p.words[:i], p.det), world)
                            if len(ref_o[0]) == 1:
                                compound_owner = ref_o[0][0]
                                span = (hits[0][0], len(p.lemmas), [])
                            break
                if span is None:
                    continue
                entity, length, extra_pieces = span
                for j in extra_pieces:
                    used.add(j)
                    explained[j] = len(pieces[j].lemmas)
            else:
                field_word = obj_kind.split(":")[1]
                # the frame names the field in Portuguese ("campo:texto"); the field itself ("text") is the same in
                # every language, and the current language's words for it come from its profile
                field_id = dict.__getitem__(FRAMES, "campos").get(field_word, field_word)
                words = [fold(w) for w, fld in FRAMES["campos"].items() if w == field_word or fld == field_id]
                if not p.lemmas or p.lemmas[0] not in words:
                    continue
                entity, length = None, 1
            explained[k] = length
            # the owner: the rest of this piece after "de", or a following "de ..." piece, or the selection
            owner = compound_owner
            rest = Piece(p.case, p.words)
            if owner is None and len(p.lemmas) > length:
                skip = length + (1 if p.lemmas[length:length + 1] == _OF() else 0)
                ref, c, n, ex = _reference(rest, world, skip)
                if ref:
                    amb = ref if len(ref) > 1 else amb
                    owner, cost, notes = ref[0], cost + c, notes + n
                    explained[k] = skip + ex
            owner_at = (k, explained[k]) if owner is not None and compound_owner is None else None
            if owner is None:
                for j, q in enumerate(pieces):
                    if j != k and j not in used and q.case[:1] == _OF():
                        ref, c, n, ex = _reference(q, world)
                        if ref:
                            amb = ref if len(ref) > 1 else amb
                            owner, cost, notes = ref[0], cost + c, notes + n
                            used.add(j)
                            explained[j] = ex
                            owner_at = (j, ex)
                            break
            if owner is None:
                if len(world.selection) == 1:
                    owner = world.selection[0]
                    cost += COST["referente_pela_selecao"]
                    notes.append("dono: o que está selecionado")
                else:
                    cost += COST["referente_nao_resolvido"]
                    notes.append("não sei de qual elemento")
                    continue
            v = _value(pieces, used, entity.id if entity is not None and entity.kind == "propriedade" else None,
                       bare_ok=p.case == ("em",), cases=f.get("valor_casos") if langs.current() == "pt" else None)
            if v is None and owner_at is not None and entity is not None and entity.kind == "propriedade":
                # the value left at the end of the owner's phrase: "o fundo da seção azul"
                j, n = owner_at
                content = [t for t in pieces[j].words if not is_literal(t.form) and t.form.lower() not in lexicon.stop()]
                tail = " ".join(t.form for t in content[n:])
                if tail and values_mod.translate(tail, entity.id):
                    v = (tail, j)
            cost += _literal_cost(pieces, v, entity.id if entity is not None and entity.kind == "propriedade" else None)
            if v is None:
                cost += COST["valor_ausente"]
                notes.append("falta o valor")
                continue
            used.add(v[1])
            explained[v[1]] = len(pieces[v[1]].lemmas)
            if obj_kind == "propriedade":
                prop_id, value = entity.id, v[0]
                if not _value_fits(prop_id, value):
                    # "a fonte ... para 32px": the value tells which property of that family was meant
                    other = _property_for_value(entity, value)
                    if other is None:
                        continue  # a value the property cannot take is no reading at all ("direita" = texto)
                    else:
                        prop_id = other.id
                        cost += COST["propriedade_pelo_valor"]
                        notes.append(f"{other.label}, pelo valor {value}")
                value = _as_keyword(value, prop_id)
                bp, st, more, extra = _layer(pieces, used, world)
                used |= set(more)
                for j in more:
                    explained[j] = more[j]
                for j, n in extra.items():
                    explained[j] = explained.get(j, 0) + n
                constraints.append({"kind": "style", "id": owner, "breakpoint": bp, "state": st,
                                    "property": prop_id, "value": value})
            elif obj_kind == "atributo":
                cost += 1.0  # an HTML attribute is a secondary property: the builder's own field is likelier
                constraints.append({"kind": "field", "id": owner, "field": "attributes", "value": {entity.id: v[0]}})
            else:
                field = next(f for w, f in FRAMES["campos"].items() if fold(w) == p.lemmas[0])
                constraints.append({"kind": "field", "id": owner, "field": field, "value": v[0]})
        cost += _unexplained(pieces, used, explained)
        if constraints:
            readings.append(Reading(f["id"], constraints, cost, notes, paraphrase(constraints, world),
                                    ambiguous=amb))
    return readings


def _span_match(pieces: list[Piece], k: int, kinds: set):
    """The longest label of `kinds` starting at piece k, allowed to continue into the following "de ..." pieces
    ("a cor | do texto | do parágrafo Intro" -> "cor de texto"). Returns (entry, lemmas used in piece k, the
    following pieces it consumed whole) or None."""
    seq = list(pieces[k].lemmas)
    bounds = [(k, len(seq))]
    for j in range(k + 1, len(pieces)):
        if len(pieces[j].case) != 1:
            break
        # a label can go on across a preposition ("espaçamento | entre letras", "cor | do texto")
        seq += list(pieces[j].case) + list(pieces[j].lemmas)
        bounds.append((j, len(seq)))
    hits = lexicon.match(tuple(seq), kinds)
    if not hits:
        return None
    entry, n = hits[0]
    own = len(pieces[k].lemmas)
    if n <= own:
        return entry, n, []
    whole = [j for j, end in bounds[1:] if end <= n]
    if not whole or bounds[len(whole)][1] != n:
        return entry, min(n, own), []  # the label would end inside a piece: keep only what fits piece k
    return entry, own, whole


def _value_readings(f: dict, pieces: list[Piece], world: World) -> list[Reading]:
    """ "coloque o título à direita", "deixe o parágrafo em negrito": the object is an element, and another phrase
    names a value; the value tells which property (one reading per candidate property)."""
    readings = []
    for k, p in enumerate(pieces):
        if p.case and not (len(p.case) == 1 and p.case[0] in ARTICLE_FORMS):
            continue
        ref, c, notes, ex = [], 0.0, [], 0
        rp = k  # the piece that names the element
        if k + 1 < len(pieces) and pieces[k + 1].case[:1] == _OF() and p.lemmas and \
                p.lemmas[0] in {fold(w) for w in FRAMES["campos"]} | {"elemento", "bloco"}:
            # possession: "o texto do parágrafo Intro", "o conteúdo da seção" refer to that element
            ref, c, notes, ex = _reference(pieces[k + 1], world)
            rp = k + 1
        within = {}
        if not ref:  # possession first: "o texto do parágrafo" is the paragraph, not "the text element"
            ref, c, notes, ex = _reference(p, world)
            rp = k
            narrowed, within = _within(ref, pieces, k, world)
            if within:
                ref, c = narrowed, (COST["referente_por_tipo"] if len(narrowed) == 1 else c)
        if not ref:
            continue
        node = ref[0]
        amb = ref if len(ref) > 1 else []
        # the value is its own phrase ("à direita"), or the rest of the naming phrase when no preposition separated
        # them ("o titulo a direita", "o conteúdo do título Title centralizado")
        content = [t for t in pieces[rp].words if not is_literal(t.form) and t.form.lower() not in lexicon.stop()]
        tail = Piece((), content[ex:]) if len(content) > ex else None
        options = [(j, q) for j, q in enumerate(pieces) if j not in (k, rp) and j not in within] +             ([(rp, tail)] if tail else [])
        for j, n_ in within.items():  # a value left at the end of the place phrase ("the heading in CardB red")
            rest_w = [t for t in pieces[j].words if not is_literal(t.form) and t.form.lower() not in lexicon.stop()]
            if len(rest_w) > n_:
                options.append((j, Piece((), rest_w[n_:])))
        for j, q in options:
            # a state named by the participle of a command's verb ("as imagens escondidas", "the button hidden"): that
            # command on the element
            for cv in _participle_commands(q):
                used = {k, rp, j} | set(within)
                explained = {k: len(p.lemmas)} if rp != k else {}
                explained.update(within)
                explained[rp] = ex + (len(q.lemmas) if j == rp else 0)
                if j != rp:
                    explained[j] = within.get(j, 0) + len(q.lemmas)
                cons = [{"kind": "command", "command": cv.command, "id": node, "label": cv.label,
                         "already": bool(cv.flag) and world.nodes[node].get("flags", {}).get(cv.flag) is True}]
                cost = c + 0.5 + _unexplained(pieces, used, explained)
                readings.append(Reading(f"comando:{cv.command}", cons, cost, list(notes), paraphrase(cons, world),
                                        ambiguous=amb))
            for prop, value, vc in _value_candidates(q, world.nodes[node]["type"]):
                used = {k, rp, j} | set(within)
                explained = {k: len(p.lemmas)} if rp != k else {}
                explained.update(within)
                explained[rp] = ex + (len(q.lemmas) if j == rp else 0)
                if j != rp:
                    # (a value at the end of the place phrase: the place's words plus the value's)
                    explained[j] = within.get(j, 0) + _value_words(q, prop, value)
                bp, st, more, extra = _layer(pieces, used, world)
                used |= set(more)
                for m in more:
                    explained[m] = more[m]
                cost = c + vc + _unexplained(pieces, used, explained)
                cons = [{"kind": "style", "id": node, "breakpoint": bp, "state": st, "property": prop, "value": value}]
                readings.append(Reading(f["id"], cons, cost, list(notes), paraphrase(cons, world), ambiguous=amb))
    return readings


def _insert_extras(pieces: list[Piece], k: int, used: set, explained: dict) -> dict:
    """What an insertion also asks of the new node: "com o texto X", "com o nome X", "chamado X"."""
    extras = {}
    # inside the object's own phrase, after the type ("um botão chamado Enviar")
    obj = pieces[k]
    consumed = explained.get(k, 0)
    rest = [t for t in obj.words if not is_literal(t.form)][consumed:]
    rest_lits = [literal_value(t.form) for t in obj.words if is_literal(t.form)]
    if rest and rest[0].lemma.lower() in ("chamar", "chamado", "nomear", "nomeado"):
        value = rest_lits[0] if rest_lits else " ".join(t.form for t in rest[1:])
        if value:
            extras["name"] = value
            explained[k] = consumed + len(rest)
    for j, q in enumerate(pieces):
        if j in used or j == k:
            continue
        lem = q.lemmas
        field = next((f for w, f in FRAMES["campos"].items() if fold(w) == lem[0]), None) if lem else None
        literal = next((literal_value(t.form) for t in q.words if is_literal(t.form)), None)
        if field and q.case[-1:] == ("com",):
            value = literal if literal is not None else " ".join(t.form for t in q.words[1:])
            if value:
                extras[field] = value
                used.add(j)
                explained[j] = len(lem)
        elif lem and lem[0] in ("chamar", "chamado", "nomear", "nomeado"):
            value = literal if literal is not None else " ".join(t.form for t in q.words[1:])
            if value:
                extras["name"] = value
                used.add(j)
                explained[j] = len(lem)
    return extras


def _placement(kind: str, node: str, world: World, moving: str | None = None) -> tuple[str | None, int | None]:
    n = world.nodes[node]
    if kind == "dentro":
        return node, None
    if kind == "inicio":
        return node, 0
    if kind == "fim":
        kids = [c for c in n["children"] if c != moving]
        return node, len(kids)
    parent = n["parent"]
    siblings = [c for c in world.nodes[parent]["children"] if c != moving] if parent else []
    pos = siblings.index(node) if node in siblings else n["index"]
    return parent, pos + (1 if kind == "depois" else 0)


# -- generation (L6): what was understood, said back in Portuguese ---------------------------------------------
def _label(kind: str, id_: str) -> str:
    for e in lexicon.load():
        if e.kind == kind and e.id == id_ and e.label != id_:
            return e.label
    return id_


def paraphrase(constraints: list, world: World) -> str:
    """What was understood, said back in the request's language: the action verbs are the builder's own labels in
    that language, the names are the document's, and the function words come from the language profile."""
    lang = langs.current()
    say = langs.profile()["say"]

    def name(nid):
        n = world.nodes.get(nid) if nid else None
        return f"«{n['name']}»" if n else say["element"]

    parts = []
    for c in constraints:
        if c["kind"] == "added":
            where = f" {say['in']} {name(c['parent'])}" if c.get("parent") else ""
            pos = "" if c.get("index") is None else f"{say['at']} {c['index'] + 1}"
            extra = "".join(f" {say['with_text'] if f == 'text' else say['with_name']} \"{c[f]}\""
                            for f in ("text", "name") if c.get(f))
            parts.append(f"{langs.action_word('insert', lang)} {_label('tipo', c['type']).lower()}{extra}{where}{pos}")
        elif c["kind"] == "removed":
            parts.append(f"{langs.action_word('remove', lang)} {name(c['id'])}")
        elif c["kind"] == "moved":
            pos = "" if c.get("index") is None else f"{say['at']} {c['index'] + 1}"
            parts.append(f"{langs.action_word('move', lang)} {name(c['id'])} {say['to']} {name(c['parent'])}{pos}")
        elif c["kind"] == "style":
            layer = "" if (c["breakpoint"], c["state"]) == ("desktop", "base") else \
                f" ({_label('breakpoint', c['breakpoint'])}, {_label('estado', c['state'])})"
            parts.append(f"{langs.action_word('set', lang)} {_label('propriedade', c['property']).lower()} "
                         f"{_OF()[0]} {name(c['id'])} {say['as']} {c['value']}{layer}")
        elif c["kind"] == "field":
            field = say.get(c["field"], c["field"])
            parts.append(f"{langs.action_word('set', lang)} {field} {_OF()[0]} {name(c['id'])} {say['as']} "
                         f"{json.dumps(c['value'], ensure_ascii=False)}")
        elif c["kind"] == "command":
            parts.append(f"{c['label'].lower()} {name(c['id'])}" + (f" {say['already']}" if c.get("already") else ""))
    text = "; ".join(parts)
    return text[:1].upper() + text[1:] + "." if parts else ""


def _why_nothing(tokens: list[Token], world: World) -> str:
    """When no reading was built at all, say which part was missing rather than a generic failure."""
    pred = _predicate(tokens)
    if pred is None:
        return langs.msg("no_verb")
    pieces = _pieces(tokens, pred)
    known = {(n["name"] or "").lower() for n in world.nodes.values()}
    for p in pieces:
        for t in p.words:
            if is_literal(t.form) and t.form[:1] not in "\"'“":
                continue  # a value, not a name
            if (t.upos == "PROPN" or t.form[:1].isupper()) and t.form.lower() not in known and \
                    not lexicon.match((lexicon.lemma_of(t.form),), KINDS):
                return langs.msg("no_such_element", name=t.form)
    # a value phrase: a literal, or a "para/como/em ..." phrase that is not an element ("no botão" names a place)
    has_value = any(is_literal(t.form) for p in pieces for t in p.words) or any(
        p.case[-1:] and p.case[-1] in FRAMES["valor_casos"] and p.words and not _reference(p, world)[0]
        for p in pieces)
    # a word of some property's label ("borda" in "Largura da borda superior") also says a property was meant
    label_words = {x for e in lexicon.load() if e.kind == "propriedade" for x in e.lemmas if x not in _OF()}
    names_prop = any(lexicon.match(p.lemmas, {"propriedade", "atributo"}) or set(p.lemmas) & label_words
                     for p in pieces if not _reference(p, world)[0])
    if names_prop and not has_value:
        return langs.msg("missing_value")
    if not _in_frame(pred.lemma):
        return langs.msg("unknown_verb", verb=pred.lemma)
    return langs.msg("verb_without_object", verb=pred.lemma)


def _definition(tokens: list[Token], text: str, world: World, by: str) -> Understanding | None:
    """ "X significa Y": teach X. Accepted only when Y is understood (a verb's definition must be a request the
    core language understands; a phrase's must name an entity the lexicon grounds)."""
    k = next((i for i, t in enumerate(tokens) if "significar" in morph_lemmas(t.form, "V")), None)
    if k is None or k == 0 or k == len(tokens) - 1:
        return None
    x = " ".join(t.form for t in tokens[:k]).strip().lower()
    y = " ".join(t.form for t in tokens[k + 1:]).strip().strip(".")
    first = tokens[0].form.lower()
    invented_infinitive = not _analyses(first) and first[-2:] in ("ar", "er", "ir") and len(first) > 3
    if k == 1 and (invented_infinitive or first in [lem for lem, tags in _analyses(first) if tags.startswith("V+INF")]):
        probe = World(world.nodes, world.selection[:1] or list(world.nodes)[:1], world.layer)
        rs = _readings(analyse(y), probe)
        if not rs or rs[0].unknown_verb or rs[0].cost > LIMIT:
            return Understanding(text, tokens, [], "nao_entendi",
                                 f"Não aprendi «{first}»: não entendi a definição «{y}».")
        learned.add_verb(first, y, text, by)
        return Understanding(text, tokens, [], "aprendido",
                             f"Aprendi: «{first}» = «{y}» (sobre o elemento que você disser).")
    structure = _structure_definition(y)
    if structure is not None:
        if isinstance(structure, str):
            return Understanding(text, tokens, [], "nao_entendi", f"Não aprendi «{x}»: {structure}.")
        head, parts = structure
        learned.add_structure(x, head, parts, text, by)
        said = ", ".join(p["type"] + (f' «{p["text"]}»' if p.get("text") else "") for p in parts)
        return Understanding(text, tokens, [], "aprendido", f"Aprendi: «{x}» = {head} com {said}.")
    seq = lexicon.lemma_seq(y)
    hits = [e for e in lexicon.load() if e.lemmas == seq and e.kind in KINDS]
    if not hits:
        return Understanding(text, tokens, [], "nao_entendi",
                             f"Não aprendi «{x}»: «{y}» não é algo que eu conheça no builder.")
    learned.add_phrase(x, hits[0].kind, hits[0].id, text, by)
    return Understanding(text, tokens, [], "aprendido", f"Aprendi: «{x}» = «{hits[0].label}» ({hits[0].id}).")


def _split_outside_quotes(text: str) -> list[str]:
    parts, cur, quoted = [], "", False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in "\"“”":
            quoted = not quoted
        if not quoted and (ch == "," or text[i:i + 3] == " e "):
            parts.append(cur.strip())
            cur = ""
            i += 1 if ch == "," else 3
            continue
        cur += ch
        i += 1
    if cur.strip():
        parts.append(cur.strip())
    return parts


def _type_of(phrase: str):
    hits = [(e, n) for e, n in lexicon.match(lexicon.lemma_seq(phrase), {"tipo"}) if not e.id.startswith("estrutura:")]
    return hits[0] if hits else None


def _structure_definition(body: str):
    """ "um artigo com um título com o texto "X" e um parágrafo" -> (head type, [{"type", "text"?}]); a message when
    it looks like a structure but a part is not understood; None when it is not a structure definition."""
    m = re.match(r"(?:um|uma)\s+(.+?)\s+(?:com|contendo)\s+(.+)$", body.strip(), flags=re.I)
    if not m:
        return None
    head = _type_of(m.group(1))
    if head is None or head[1] != len(lexicon.lemma_seq(m.group(1))):
        return None
    parts = []
    for raw in _split_outside_quotes(m.group(2)):
        pm = re.match(r"(?:um|uma|dois|duas)?\s*(.+?)(?:\s+com\s+o\s+texto\s+[\"“](.*)[\"”])?$", raw.strip(), flags=re.I)
        t = _type_of(pm.group(1)) if pm else None
        if t is None or t[1] != len(lexicon.lemma_seq(pm.group(1))):
            return f"não conheço a parte «{raw}»"
        part = {"type": t[0].id}
        if pm.group(2):
            part["text"] = pm.group(2)
        parts.append(part)
    return head[0].id, parts


def _analyses(word: str):
    from .morph import analyses

    return analyses(word)


LINKS = {"depois", "também", "em", "seguida", "então", "logo", "ainda"}


def split_clauses(text: str) -> list[str]:
    """A compound request ("insira X e depois apague Y") as its clauses, in order. A clause starts at "e" (or ";")
    when, after optional linking words ("depois", "também", "em seguida"), a word that can be a request verb comes."""
    words = tokenize(text)
    parts, current = [], []
    k = 0
    while k < len(words):
        w = words[k]
        if w.lower() in ("e", ";") and current:
            j = k + 1
            while j < len(words) and words[j].lower() in LINKS:
                j += 1
            if j < len(words) and _frame_verb(words[j]):
                parts.append(current)
                current = []
                k = j
                continue
        current.append(w)
        k += 1
    if current:
        parts.append(current)
    return [" ".join(p).replace(" ,", ",").strip(" ,;") for p in parts]


def _replace_node(constraints: list, old: str, new: str) -> list:
    def rep(x):
        if isinstance(x, dict):
            return {k: rep(v) for k, v in x.items()}
        if isinstance(x, list):
            return [rep(v) for v in x]
        return new if x == old else x

    return rep(constraints)


def _regular_infinitives(form: str) -> list[str]:
    """Infinitives a verb form unknown to MorphoBr can have by the regular conjugation ("blorfe" -> "blorfar"):
    a word the user invented and taught is used in any of its forms."""
    w = form.lower()
    if _analyses(w):
        return []
    out = []
    # formal imperative/subjunctive and informal imperative/indicative: "-e" and "-a" can come from any class
    # ("delete" de deletar, "deleta" de deletar, "escreve" de escrever)
    every = ("ar", "er", "ir")
    for ending, infs in (("em", every), ("es", every), ("e", every), ("am", every), ("as", every),
                         ("a", every), ("ou", ("ar",)), ("ei", ("ar",))):
        if w.endswith(ending) and len(w) > len(ending) + 2:
            out += [w[:-len(ending)] + i for i in infs]
            break
    return out


def gapped_clauses(text: str) -> list[str] | None:
    """Coordination without a second verb (gapping): "insira um título e um parágrafo", "deixe a seção com fundo preto
    e o título branco" are two requests sharing the first verb. Returns the clauses with the verb repeated, or None
    when the sentence has no such "e"."""
    words = tokenize(text)
    verb = next((k for k, w in enumerate(words) if _frame_verb(w) and not _politeness_words(words, k)), None)
    if verb is None:
        return None
    parts, current = [], []
    for w in words[verb:]:
        if w.lower() == "e" and current:
            parts.append(current)
            current = []
            continue
        current.append(w)
    if current:
        parts.append(current)
    if len(parts) < 2 or any(not p for p in parts):
        return None
    head = " ".join(words[:verb + 1])
    out = [" ".join(words[:verb]) + " " + " ".join(parts[0]) if verb else " ".join(parts[0])]
    out += [head + " " + " ".join(p) for p in parts[1:]]
    return [c.strip() for c in out]


def _politeness_words(words: list[str], k: int) -> bool:
    return words[k].lower() == "por" and k + 1 < len(words) and words[k + 1].lower() == "favor"


def understand(text: str, world: World, by: str = "usuario", lang: str | None = None) -> Understanding:
    """The request's language is detected (or given), and the whole pipeline runs in it."""
    with langs.use(lang or langs.detect(text)):
        u = _understand(text, world, by)
    u.lang = lang or langs.detect(text)
    return u


def _understand(text: str, world: World, by: str = "usuario") -> Understanding:
    tokens = analyse(text)
    taught = _definition(tokens, text, world, by)
    if taught is not None:
        return taught
    pred = _predicate(tokens)
    definition = None
    if pred is not None:
        taught = learned.verbs()
        for cand in [pred.lemma] + _regular_infinitives(pred.form):
            if cand in taught:
                definition, pred.lemma = taught[cand], cand
                break
    if definition and not _in_frame(pred.lemma):
        # a taught verb: its definition, applied to what this sentence says after the verb
        rest = " ".join(t.form for t in tokens if t.i > pred.i and t.upos != "PUNCT")
        expanded = f"{definition['definicao']} de {rest}" if rest else definition["definicao"]
        u = _understand(expanded, world, by)
        u.text = text
        if u.message and u.decision == "executar":
            u.message = f"{u.message} (pois «{pred.lemma}» = «{definition['definicao']}»)"
        return u
    readings = _readings(tokens, world)
    if not readings or readings[0].cost > LIMIT:
        if readings and readings[0].unknown_verb:
            why = langs.msg("unknown_verb", verb=readings[0].verb)  # not "the verb is outside frame X": that is internal
        else:
            why = ("; ".join(readings[0].assumptions) if readings else "") or _why_nothing(tokens, world)
        return Understanding(text, tokens, readings, "nao_entendi", langs.msg("not_understood", why=why))
    best = readings[0]
    if best.unknown_verb:
        # the action itself was not understood: never executed, and no guess offered as if it were an answer
        verb = best.assumptions[0].split("'")[1]
        # the rest of the sentence may still be fully explained: say what it would mean, as a question, not an act
        # (only when the rest of the sentence says a value that singles out one meaning: "pinte o título de
        # vermelho"; "blorfe o botão" says nothing but the element, and any action would be a guess)
        second = next((r for r in readings[1:] if r.constraints != best.constraints), None)
        single = (second is None or second.cost - best.cost >= 1.0) and             all(c["kind"] in ("style", "field") for c in best.constraints)
        if single and best.cost - COST["verbo_fora_do_quadro"] <= 1.0:
            # abduction: everything but the verb is explained, and it explains one change only ("pinte o título de
            # vermelho"): that change is the likeliest meaning. It is carried out and said, and an undo teaches
            # (preferences) that it was not this.
            return Understanding(text, tokens, readings, "executar",
                                 langs.msg("unknown_verb_guess", what=best.paraphrase, verb=verb))
        infinitive = (_regular_infinitives(verb) or [verb])[0]
        return Understanding(text, tokens, readings, "perguntar",
                             langs.msg("ask_unknown_verb", verb=infinitive))
    if getattr(best, "ask_value", None):
        node, prop = best.ask_value
        return Understanding(text, tokens, readings, "perguntar",
                             langs.msg("ask_amount", prop=_label("propriedade", prop).lower(),
                                       name=world.nodes[node]["name"] or node))
    universal = langs.profile()["universal"]
    if best.ambiguous and any(fold(t.form.lower()) in universal for t in tokens):
        # "todos os títulos", "all the headings": the same change for each one
        each = [c for n in best.ambiguous for c in _replace_node(best.constraints, best.ambiguous[0], n)]
        best.constraints, best.ambiguous = each, []
        best.paraphrase = paraphrase(each, world)
        return Understanding(text, tokens, readings, "executar", best.paraphrase)
    if best.ambiguous:
        names = ", ".join(f"«{world.nodes[n]['name']}»" for n in best.ambiguous[:6])
        return Understanding(text, tokens, readings, "perguntar", langs.msg("which", names=names))
    # (readings of an unknown verb, the fallback when nothing else applies, never rival a grounded reading)
    rivals = [r for r in readings[1:] if r.cost - best.cost < 1.0 and r.constraints != best.constraints
              and not (r.unknown_verb and not best.unknown_verb)]
    if rivals:
        options = langs.msg("or").join(f"«{r.paraphrase}»" for r in [best] + rivals[:2])
        return Understanding(text, tokens, readings, "perguntar", langs.msg("did_you_mean", options=options))
    corroborated = any(not r.uncertain and r.constraints == best.constraints and r.cost - best.cost < 1.0
                       for r in readings[1:])
    if best.uncertain and not corroborated:
        why = f" ({best.assumptions[0]})" if best.assumptions else ""
        return Understanding(text, tokens, readings, "perguntar",
                             langs.msg("confirm", why=why, what=best.paraphrase))
    return Understanding(text, tokens, readings, "executar", best.paraphrase)
