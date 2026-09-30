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
from dataclasses import dataclass, field
from functools import lru_cache

from . import learned, lexicon
from .values import fold
from .values import index as value_index
from .morph import lemmas as morph_lemmas
from .syntax import load_models
from .tokenize import is_literal, literal_value, tokenize

FRAMES = json.loads((pathlib.Path(__file__).with_name("frames.json")).read_text(encoding="utf-8"))
MODALS = {"poder", "querer", "gostar", "precisar", "conseguir", "dever", "ir", "favor"}
PRONOUNS = {"isso", "isto", "aquilo", "ele", "ela", "este", "esta", "esse", "essa", "selecionado", "selecionada",
            "selecao"}
COST = {"verbo_fora_do_quadro": 4.0, "referente_ambiguo": 2.5, "referente_por_tipo": 0.5,
        "referente_pela_selecao": 0.3, "referente_nao_resolvido": 5.0, "valor_ausente": 5.0,
        "palavra_sem_explicacao": 1.0, "tipo_diferente_do_nome": 2.0, "local_ausente": 0.5,
        "artigo_como_preposicao": 0.5, "objeto_com_preposicao": 1.0, "definido_para_novo": 1.0,
        "indefinido_para_existente": 2.0, "valor_primeiro": 0.3, "palavra_com_significado_ignorada": 3.0}
LIMIT = 4.0


@dataclass
class Token:
    i: int
    form: str
    lemma: str
    upos: str
    head: int
    deprel: str


@dataclass
class Reading:
    frame: str
    constraints: list
    cost: float
    assumptions: list = field(default_factory=list)
    paraphrase: str = ""
    ambiguous: list = field(default_factory=list)  # candidate nodes when a referent was not unique
    unknown_verb: bool = False


@dataclass
class Understanding:
    text: str
    tokens: list
    readings: list
    decision: str
    message: str = ""

    @property
    def best(self) -> Reading | None:
        return self.readings[0] if self.readings else None


@lru_cache(maxsize=1)
def _models():
    return load_models()


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
            known = [c for c in cands if any(c in f["verbos"] for f in FRAMES["quadros"]) or c in MODALS]
            lemma = (known or cands or [lem.lemma(w, t)])[0]
        else:
            lemma = lem.lemma(w, t)
        out.append(Token(i, w, lemma, t, h, lab))
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


def _frame_verb(form: str) -> str | None:
    """The lemma of a frame verb (or a verb the user taught) this form can be, per MorphoBr, whatever tag the tagger
    gave it ("ajuste": a noun to the tagger, but also the subjunctive of "ajustar")."""
    taught = learned.verbs()
    for lemma in morph_lemmas(form, "V"):
        if any(lemma in f["verbos"] for f in FRAMES["quadros"]) or lemma in taught:
            return lemma
    return None


def _predicate(tokens: list[Token]) -> Token | None:
    """The request's verb. The parser proposes (the root, or what a modal root governs); the lexicon reranks when
    the proposal is not a frame verb but another word can be one."""
    roots = [t for t in tokens if t.head == 0]
    pred = next((t for t in roots if t.upos in ("VERB", "AUX") and t.lemma not in MODALS), None)
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
            any(pred.lemma in f["verbos"] for f in FRAMES["quadros"]):
        return pred
    for t in tokens:  # lexical reranking: the first word that can be a frame verb
        lemma = _frame_verb(t.form)
        if lemma and t.lemma not in MODALS:
            t.lemma, t.upos = lemma, "VERB"
            return t
    if pred is None or pred.upos not in ("VERB", "AUX") or pred.lemma in MODALS:
        verbs = [t for t in tokens if t.upos == "VERB" and t.lemma not in MODALS]
        pred = verbs[0] if verbs else pred
    return pred


ARTICLE_FORMS = {"a", "o", "as", "os"}
DEFINITE = {"o", "a", "os", "as", "este", "esta", "esse", "essa", "aquele", "aquela"}
INDEFINITE = {"um", "uma", "uns", "umas"}


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
                     if not is_literal(t.form) and t.form.lower() not in lexicon.STOP)


def _pieces(tokens: list[Token], pred: Token) -> list[Piece]:
    """The words after (and around) the predicate, cut at prepositions into pieces, in surface order.
    Determiners and punctuation are dropped; modal/politeness words that belong to no argument are ignored."""
    used = {pred.i}
    for t in tokens:
        # a subject is dropped only when it is a pronoun ("você"): a phrase the parser mislabels as subject would
        # otherwise vanish with its whole subtree
        if t.head == pred.i and (t.deprel in ("aux", "punct", "discourse", "vocative", "mark", "cop")
                                 or t.deprel == "nsubj" and t.upos == "PRON"
                                 or t.lemma in MODALS or t.lemma in ("por", "favor") and t.deprel in ("advmod", "obl")):
            for s in _subtree(tokens, t.i):
                used.add(s.i)
    # heads of the sentence above the predicate (a modal root) are not arguments either
    for t in tokens:
        if t.i != pred.i and (t.lemma in MODALS or t.upos == "PRON" and t.deprel == "nsubj"):
            used.add(t.i)
    pieces: list[Piece] = []
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
            current.det = t.form.lower()
            continue
        if t.i in used or t.upos in ("PUNCT", "DET") or t.lemma in ("favor",):
            continue
        if t.upos == "ADP":
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
                              "children": [c["id"] for c in n.get("children", [])]}
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
            if (t.upos == "PROPN" or t.form[:1].isupper() or t.form[:1] in "\"'“") and                     literal_value(t.form).lower() not in known and not lexicon.match((lexicon.lemma_of(t.form),), KINDS):
                return [], COST["referente_nao_resolvido"], [f"nenhum elemento se chama {literal_value(t.form)}"], 1
    type_hits = lexicon.match(seq, {"tipo"})
    typ = type_hits[0][0].id if type_hits else None
    explained = (type_hits[0][1] if type_hits else 0) + (1 if names else 0)
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
        if len(of_type) == 1:
            return of_type, COST["referente_por_tipo"], [], explained
        sel = [n for n in of_type if n in world.selection]
        if len(sel) == 1:
            return sel, COST["referente_por_tipo"], ["o selecionado entre vários"], explained
        if of_type:
            return of_type, COST["referente_ambiguo"], [f"{len(of_type)} candidatos"], explained
    return [], COST["referente_nao_resolvido"], ["referente não encontrado"], explained


LITERAL_COST = 2.0


def _literal_cost(pieces: list[Piece], v) -> float:
    """Taking unquoted words that mean something known as a literal value costs (the meaning is likelier)."""
    if v is None or not isinstance(v[0], str):
        return 0.0
    words = pieces[v[1]].words
    if any(is_literal(t.form) for t in words):
        return 0.0  # quoted or CSS-like: a literal by its form
    lem = pieces[v[1]].lemmas
    meaningful = any(x in value_index() for x in lem) or bool(
        lexicon.match(lem, {"tipo", "propriedade", "atributo", "estado", "breakpoint"}))
    return LITERAL_COST if meaningful else 0.0


def _value(pieces: list[Piece], used: set, prop: str | None = None, bare_ok: bool = False) -> tuple[object, int] | None:
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
        if k in used or not p.case or p.case[-1] not in FRAMES["valor_casos"] or not p.words:
            continue
        # the words of a "para/como/em ..." phrase that grounds to nothing: the value as said (a CSS keyword, a
        # name). If it is not valid, the builder refuses it when the plan runs: never a silent change.
        # Words that also mean something known (a type, a property, a named CSS value such as "negrito") can
        # still be a literal (a new name "Topo"), but reading them literally costs: when another reading uses their
        # meaning, that reading wins (see LITERAL_COST at the callers).
        if prop is not None and lexicon.match(p.lemmas, {"tipo", "propriedade", "atributo", "estado", "breakpoint"}):
            continue
        return " ".join(t.form for t in p.words), k
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


@lru_cache(maxsize=1)
def _locution_heads() -> set:
    """The non-preposition words of the place phrases in frames.json ("depois", "início", "dentro", ...)."""
    preps = {"em", "de", "para", "a", "o"}
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


def _layer(pieces: list[Piece], used: set, world: World) -> tuple[str, str, set, dict]:
    """The breakpoint and style state a style is for: labels found anywhere in the pieces ("no tablet", "no estado
    foco", "ao passar o mouse", or left at the end of the value phrase). Returns the pieces taken whole and, for
    pieces already in use, how many extra lemmas the layer explained."""
    bp, st = world.layer
    more, extra = set(), {}
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
                more.add(k)
            break
    return bp, st, more, extra


def _readings(tokens: list[Token], world: World) -> list[Reading]:
    pred = _predicate(tokens)
    if pred is None:
        return []
    pieces = _pieces(tokens, pred)
    out: list[Reading] = []
    frames = [f for f in FRAMES["quadros"] if pred.lemma in f["verbos"]]
    base_cost = 0.0
    if not frames:
        frames = FRAMES["quadros"]
        base_cost = COST["verbo_fora_do_quadro"]
    for f in frames:
        for r in _frame_readings(f, pieces, world):
            r.cost += base_cost
            if base_cost:
                r.unknown_verb = True
                r.assumptions.insert(0, f"o verbo '{pred.lemma}' não está no quadro '{f['id']}'")
            out.append(r)
    out.sort(key=lambda r: (r.cost, r.frame))
    return out


KINDS = {"tipo", "propriedade", "atributo", "estado", "breakpoint"}


def _unexplained(pieces: list[Piece], used: set, partial: dict) -> float:
    """Each word no part of the reading explains costs; a word that names something the builder knows (a state, a
    property, a type) costs more, because leaving it out would silently drop part of what was asked."""
    cost = 0.0
    for k, p in enumerate(pieces):
        lem = p.lemmas
        rest = lem[partial.get(k, len(lem)):] if k in used else lem
        if k not in used and not lem and p.words:
            cost += COST["palavra_sem_explicacao"]
        for i in range(len(rest)):
            named = bool(lexicon.match(tuple(rest), KINDS, i))
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
    props, contents = _property_facts()
    out = []
    for lem in piece.lemmas:
        for prop, value in value_index().get(lem, []):
            applies, essential = props.get(prop, ("always", False))
            cost = 0.0 if essential else 1.0  # the builder shows essential properties first: the likelier meaning
            if applies == "text" and contents.get(node_type) != "text":
                cost += 3.0
            elif applies not in ("always", "text"):
                cost += 0.5
            out.append((prop, value, cost))
    return out


def _frame_readings(f: dict, pieces: list[Piece], world: World) -> list[Reading]:
    if f.get("valor_rotulado"):
        return _value_readings(f, pieces, world)
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
        if obj_kind == "tipo":
            hits = lexicon.match(p.lemmas, {"tipo"})
            if not hits:
                continue
            typ = hits[0][0].id
            explained[k] = hits[0][1]
            if det in DEFINITE:
                cost += COST["definido_para_novo"]
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
                cost += COST["local_ausente"]
                notes.append("sem local: onde o editor puser")
            constraints.append({"kind": "added", "type": typ, "parent": parent, "index": index, **extras})
        elif obj_kind in ("no",):
            ref, c, n, ex = _reference(p, world)
            if not ref:
                continue
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
                v = _value(pieces, used)
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
            if kinds:
                span = _span_match(pieces, k, kinds)
                if span is None:
                    continue
                entity, length, extra_pieces = span
                for j in extra_pieces:
                    used.add(j)
                    explained[j] = len(pieces[j].lemmas)
            else:
                field_word = obj_kind.split(":")[1]
                words = [fold(w) for w, fld in FRAMES["campos"].items() if w == field_word or fld == field_word]
                if not p.lemmas or p.lemmas[0] not in words:
                    continue
                entity, length = None, 1
            explained[k] = length
            # the owner: the rest of this piece after "de", or a following "de ..." piece, or the selection
            owner = None
            rest = Piece(p.case, p.words)
            if len(p.lemmas) > length:
                skip = length + (1 if p.lemmas[length:length + 1] == ("de",) else 0)
                ref, c, n, ex = _reference(rest, world, skip)
                if ref:
                    amb = ref if len(ref) > 1 else amb
                    owner, cost, notes = ref[0], cost + c, notes + n
                    explained[k] = skip + ex
            if owner is None:
                for j, q in enumerate(pieces):
                    if j != k and j not in used and q.case[:1] == ("de",):
                        ref, c, n, ex = _reference(q, world)
                        if ref:
                            amb = ref if len(ref) > 1 else amb
                            owner, cost, notes = ref[0], cost + c, notes + n
                            used.add(j)
                            explained[j] = ex
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
                       bare_ok=p.case == ("em",))
            cost += _literal_cost(pieces, v)
            if v is None:
                cost += COST["valor_ausente"]
                notes.append("falta o valor")
                continue
            used.add(v[1])
            explained[v[1]] = len(pieces[v[1]].lemmas)
            if obj_kind == "propriedade":
                bp, st, more, extra = _layer(pieces, used, world)
                used |= more
                for j in more:
                    explained[j] = len(pieces[j].lemmas)
                for j, n in extra.items():
                    explained[j] = explained.get(j, 0) + n
                constraints.append({"kind": "style", "id": owner, "breakpoint": bp, "state": st,
                                    "property": entity.id, "value": v[0]})
            elif obj_kind == "atributo":
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
        if pieces[j].case != ("de",):
            break
        seq += ["de"] + list(pieces[j].lemmas)
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
        ref, c, notes, ex = _reference(p, world)
        rp = k  # the piece that names the element
        if not ref and k + 1 < len(pieces) and pieces[k + 1].case[:1] == ("de",) and p.lemmas and \
                p.lemmas[0] in {fold(w) for w in FRAMES["campos"]} | {"elemento", "bloco"}:
            # possession: "o texto do parágrafo Intro", "o conteúdo da seção" refer to that element
            ref, c, notes, ex = _reference(pieces[k + 1], world)
            rp = k + 1
        if not ref:
            continue
        node = ref[0]
        amb = ref if len(ref) > 1 else []
        # the value is its own phrase ("à direita"), or the rest of the naming phrase when no preposition separated
        # them ("o titulo a direita", "o conteúdo do título Title centralizado")
        content = [t for t in pieces[rp].words if not is_literal(t.form) and t.form.lower() not in lexicon.STOP]
        tail = Piece((), content[ex:]) if len(content) > ex else None
        options = [(j, q) for j, q in enumerate(pieces) if j not in (k, rp)] + ([(rp, tail)] if tail else [])
        for j, q in options:
            for prop, value, vc in _value_candidates(q, world.nodes[node]["type"]):
                used = {k, rp, j}
                explained = {k: len(p.lemmas)} if rp != k else {}
                explained[rp] = ex + (len(q.lemmas) if j == rp else 0)
                if j != rp:
                    explained[j] = len(q.lemmas)
                bp, st, more, extra = _layer(pieces, used, world)
                used |= more
                for m in more:
                    explained[m] = len(pieces[m].lemmas)
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
    def name(nid):
        n = world.nodes.get(nid) if nid else None
        return f"«{n['name']}»" if n else "o elemento"

    parts = []
    for c in constraints:
        if c["kind"] == "added":
            where = f" em {name(c['parent'])}" if c.get("parent") else ""
            pos = "" if c.get("index") is None else f", na posição {c['index'] + 1}"
            extra = "".join(f" com {'o texto' if f == 'text' else 'o nome'} \"{c[f]}\"" for f in ("text", "name")
                            if c.get(f))
            parts.append(f"inserir {_label('tipo', c['type']).lower()}{extra}{where}{pos}")
        elif c["kind"] == "removed":
            parts.append(f"remover {name(c['id'])}")
        elif c["kind"] == "moved":
            pos = "" if c.get("index") is None else f", na posição {c['index'] + 1}"
            parts.append(f"mover {name(c['id'])} para {name(c['parent'])}{pos}")
        elif c["kind"] == "style":
            layer = "" if (c["breakpoint"], c["state"]) == ("desktop", "base") else \
                f" ({_label('breakpoint', c['breakpoint'])}, {_label('estado', c['state'])})"
            parts.append(f"definir {_label('propriedade', c['property']).lower()} de {name(c['id'])} como "
                         f"{c['value']}{layer}")
        elif c["kind"] == "field":
            parts.append(f"definir {c['field']} de {name(c['id'])} como {json.dumps(c['value'], ensure_ascii=False)}")
    text = "; ".join(parts)
    return text[:1].upper() + text[1:] + "." if parts else ""


def _why_nothing(tokens: list[Token], world: World) -> str:
    """When no reading was built at all, say which part was missing rather than a generic failure."""
    pred = _predicate(tokens)
    if pred is None:
        return "não achei o verbo do pedido"
    pieces = _pieces(tokens, pred)
    known = {(n["name"] or "").lower() for n in world.nodes.values()}
    for p in pieces:
        for t in p.words:
            if (t.upos == "PROPN" or t.form[:1].isupper()) and t.form.lower() not in known and \
                    not lexicon.match((lexicon.lemma_of(t.form),), KINDS):
                return f"nenhum elemento se chama «{t.form}»"
    has_value = any(is_literal(t.form) for p in pieces for t in p.words) or any(
        p.case[-1:] and p.case[-1] in FRAMES["valor_casos"] and p.words for p in pieces)
    names_prop = any(lexicon.match(p.lemmas, {"propriedade", "atributo"}) for p in pieces)
    if names_prop and not has_value:
        return "falta o valor (por exemplo: «... como 24px»)"
    if not any(pred.lemma in f["verbos"] for f in FRAMES["quadros"]):
        return f"não conheço o verbo «{pred.lemma}»"
    return f"entendi o verbo «{pred.lemma}», mas não o que ele deve alterar"


def _definition(tokens: list[Token], text: str, world: World, by: str) -> Understanding | None:
    """ "X significa Y": teach X. Accepted only when Y is understood (a verb's definition must be a request the
    core language understands; a phrase's must name an entity the lexicon grounds)."""
    k = next((i for i, t in enumerate(tokens) if "significar" in morph_lemmas(t.form, "V")), None)
    if k is None or k == 0 or k == len(tokens) - 1:
        return None
    x = " ".join(t.form for t in tokens[:k]).strip().lower()
    y = " ".join(t.form for t in tokens[k + 1:]).strip().strip(".")
    first = tokens[0].form.lower()
    if k == 1 and first in [lem for lem, tags in _analyses(first) if tags.startswith("V+INF")]:
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


def understand(text: str, world: World, by: str = "usuario") -> Understanding:
    tokens = analyse(text)
    taught = _definition(tokens, text, world, by)
    if taught is not None:
        return taught
    pred = _predicate(tokens)
    definition = learned.verbs().get(pred.lemma) if pred is not None else None
    if definition and not any(pred.lemma in f["verbos"] for f in FRAMES["quadros"]):
        # a taught verb: its definition, applied to what this sentence says after the verb
        rest = " ".join(t.form for t in tokens if t.i > pred.i and t.upos != "PUNCT")
        expanded = f"{definition['definicao']} de {rest}" if rest else definition["definicao"]
        u = understand(expanded, world, by)
        u.text = text
        if u.message and u.decision == "executar":
            u.message = f"{u.message} (pois «{pred.lemma}» = «{definition['definicao']}»)"
        return u
    readings = _readings(tokens, world)
    if not readings or readings[0].cost > LIMIT:
        why = ("; ".join(readings[0].assumptions) if readings else "") or _why_nothing(tokens, world)
        return Understanding(text, tokens, readings, "nao_entendi", f"Não entendi: {why}.")
    best = readings[0]
    if best.unknown_verb:
        # the action itself was not understood: never executed, and no guess offered as if it were an answer
        verb = best.assumptions[0].split("'")[1]
        return Understanding(text, tokens, readings, "perguntar",
                             f"Não conheço o verbo «{verb}». O que ele deve fazer? "
                             f"(por exemplo: «{verb} significa definir o alinhamento do texto como center»)")
    if best.ambiguous:
        names = ", ".join(f"«{world.nodes[n]['name']}»" for n in best.ambiguous[:6])
        return Understanding(text, tokens, readings, "perguntar", f"Qual deles: {names}?")
    rivals = [r for r in readings[1:] if r.cost - best.cost < 1.0 and r.constraints != best.constraints]
    if rivals:
        options = " ou ".join(f"«{r.paraphrase}»" for r in [best] + rivals[:2])
        return Understanding(text, tokens, readings, "perguntar", f"Você quer dizer {options}?")
    return Understanding(text, tokens, readings, "executar", best.paraphrase)
