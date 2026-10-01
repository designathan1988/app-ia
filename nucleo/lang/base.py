"""What the understanding engine and the rest of the application share: the world model, the words of the
language profile's closed classes, the analysis of a sentence into tokens, the action frames, the builder's
property facts (priors, value kinds), placement and the paraphrase of goal constraints.

These definitions lived in ``understand.py`` with the first engine (14 reading generators over linear pieces).
That engine was replaced (docs/plano_compreensao.md, C6) and is kept only as the measurement baseline; the
application imports from here.
"""

from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass, field
from functools import lru_cache
from types import SimpleNamespace

from . import command_verbs, langs, learned, lexicon
from . import values as values_mod
from .morph import analyses as _pt_analyses
from .morph import lemmas as _pt_lemmas
from .syntax import load_models
from .tokenize import is_literal, literal_value, tokenize
from .values import fold
from .values import index as value_index


def morph_lemmas(form: str, category: str | None = None) -> list[str]:
    """Lemmas of a form: MorphoBr for Portuguese; the English treebank's lemmas (and the wordnet) for English."""
    if langs.current() == "en":
        return [langs.english_lemma(form, "VERB" if category == "V" else None)]
    return _pt_lemmas(form, category)


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


def make_tokens(words: list[str], tags: list[str], arcs: list) -> list[Token]:
    """Tokens (with lemmas and homograph alternatives) from words, tags and (head, relation) arcs."""
    _, _, lem, _ = _models()
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
                              "styles": n.get("styles") or {},
                              "text": n.get("text") if isinstance(n.get("text"), str) else None}
            for i, c in enumerate(n.get("children", [])):
                walk(c, n["id"], i)

        for p in doc.get("pages", []):
            walk(p["tree"], None, 0)
        return cls(nodes, list(selection), tuple(layer))


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


def _as_keyword(value, prop: str):
    """A Portuguese value name as the CSS keyword it names for the property ("azul" -> "blue"); other values as
    said."""
    if isinstance(value, str) and not is_literal(value):
        k = values_mod.translate(value, prop)
        if k:
            return k
    return value


def _OF() -> tuple:  # noqa: N802
    """The language's possessive preposition ("de"; "of"): "a cor do texto", "the color of the text"."""
    return (langs.profile().get("of", "de"),)


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


@lru_cache(maxsize=1)
def _form_controls() -> frozenset:
    """The element types the builder counts as form controls (``src/core/style/applies.ts``, KINDS.formControl: the
    widgets with a native appearance), by the tag each type is written with."""
    import json as _json

    from ..builder.client import DEFAULT_BUILDER

    root = pathlib.Path(DEFAULT_BUILDER)
    src = root / "src" / "core" / "style" / "applies.ts"
    m = re.search(r"formControl:\s*\[([^\]]*)\]", src.read_text(encoding="utf-8")) if src.exists() else None
    tags = set(re.findall(r"'([a-z]+)'", m.group(1))) if m else set()
    elements = _json.loads((root / "manifest" / "elements.json").read_text(encoding="utf-8"))["elements"]
    return frozenset(e["id"] for e in elements if e.get("tag") in tags)


@lru_cache(maxsize=1)
def _base_rules() -> list:
    """The builder's base stylesheet (``src/core/render/base.ts``: every page starts from it, in the canvas and in
    the export) as (selectors, declarations) pairs."""
    from ..builder.client import DEFAULT_BUILDER

    src = pathlib.Path(DEFAULT_BUILDER) / "src" / "core" / "render" / "base.ts"
    if not src.exists():
        return []
    text = src.read_text(encoding="utf-8")
    css = text[text.find("`") + 1:text.rfind("`")]
    out = []
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        sel = sel.strip()
        inner = re.fullmatch(r":where\((.*)\)", sel)
        tags = [x.strip() for x in (inner.group(1) if inner else sel).split(",")]
        decls = dict((k.strip(), v.strip()) for k, v in (d.split(":", 1) for d in body.split(";") if ":" in d))
        out.append((tags, decls))
    return out


def default_style(node_type: str | None, prop: str) -> str | None:
    """The value a property has on an element nobody styled: the builder's base stylesheet for the element's tag,
    else (for an inherited property, W3C) the page body's; rem and em resolved against the body's font size."""
    from .values import _w3c_properties

    _, _ = _property_facts()
    import json as _json

    from ..builder.client import DEFAULT_BUILDER

    elements = _json.loads((pathlib.Path(DEFAULT_BUILDER) / "manifest" / "elements.json").read_text(encoding="utf-8"))
    tag = next((e.get("tag") for e in elements["elements"] if e["id"] == node_type), None)
    rules = _base_rules()
    body = next((d.get("font-size") for tags, d in rules if "body" in tags and "font-size" in d), "16px")
    root_px = float(re.match(r"[\d.]+", body).group()) if re.match(r"[\d.]+px", body) else 16.0
    value = next((d[prop] for tags, d in rules if tag in tags and prop in d), None)
    if value is None and (_w3c_properties().get(prop) or {}).get("inherited") == "yes":
        value = next((d[prop] for tags, d in rules if "body" in tags and prop in d), None)
    m = re.fullmatch(r"(-?[\d.]+)(rem|em)", value or "")
    if m:
        px = float(m.group(1)) * root_px
        value = f"{int(px) if px == int(px) else round(px, 2)}px"
    return value


def _prior(prop: str, node_type: str | None) -> float:
    """How unlikely a property is as the meaning for this element: the builder shows essential properties first;
    a property that does not apply to the element's content (a text property on a section) is unlikely; and on a
    text element, a property of any element is less specific than one of text ("o título branco": the text's
    color, not the background)."""
    props, contents = _property_facts()
    applies, essential = props.get(prop, ("always", False))
    cost = 0.0 if essential else 1.0
    control = node_type in _form_controls()
    if applies == "text" and contents.get(node_type) != "text":
        cost += 3.0
    elif applies == "always" and contents.get(node_type) == "text" and not control:
        # (a form control is drawn as a filled box, its native appearance: on one, "o botão verde" may be its text or
        # its fill, equally; the reading then asks which)
        cost += 1.0
    elif applies == "hasBox":
        cost += 0.5
    elif applies not in ("always", "text"):
        # applies only under a layout the element may not have (a flex or grid container, a positioned box...):
        # unlikely unless the request says so
        cost += 2.0
    return cost


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


def _feminine(noun: str) -> bool:
    """Whether a Portuguese noun is feminine (MorphoBr), for the article and adjective said with it."""
    if langs.current() != "pt":
        return False
    tags = [t for _, t in _pt_analyses(noun.split()[0])]
    return any(t.startswith("N+F") for t in tags) and not any(t.startswith("N+M") for t in tags)


def paraphrase(constraints: list, world: World) -> str:
    """What was understood, said back in the request's language: the action verbs are the builder's own labels in
    that language, the names are the document's, and the function words come from the language profile."""
    lang = langs.current()
    say = langs.profile()["say"]

    # (an element the text itself creates is said by its type: "o botão novo", "the new button")
    created = [c["type"] for c in constraints if c["kind"] == "added"]

    def name(nid):
        n = world.nodes.get(nid) if nid else None
        if n and n.get("name"):
            return f"«{n['name']}»"
        typ = n["type"] if n else None
        if typ is None and str(nid).startswith("$novo"):
            k = int(str(nid)[5:]) - 1
            typ = created[k] if 0 <= k < len(created) else None
        if typ is None:
            return say["element"]
        label = _label("tipo", typ).lower()
        return say["new_f" if _feminine(label) else "new_m"].format(type=label)

    from .tokenize import contractions

    joined = {v: k for k, v in contractions().items() if len(v) == 2}

    def of(nid):
        # the preposition and the article written together as the language writes them ("de o elemento" is "do
        # elemento"), from the treebank's own contraction table read backwards
        words = f"{_OF()[0]} {name(nid)}".split(" ")
        pair = tuple(words[:2])
        return " ".join([joined[pair]] + words[2:]) if pair in joined else " ".join(words)

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
                         f"{of(c['id'])} {say['as']} {c['value']}{layer}")
        elif c["kind"] == "field":
            field = say.get(c["field"], c["field"])
            parts.append(f"{langs.action_word('set', lang)} {field} {of(c['id'])} {say['as']} "
                         f"{json.dumps(c['value'], ensure_ascii=False)}")
        elif c["kind"] == "selected":
            parts.append(f"{langs.action_word('select', lang)} {name(c['id'])}")
        elif c["kind"] == "command":
            parts.append(f"{c['label'].lower()} {name(c['id'])}" + (f" {say['already']}" if c.get("already") else ""))
    text = "; ".join(parts)
    return text[:1].upper() + text[1:] + "." if parts else ""


def _analyses(word: str):
    from .morph import analyses

    return analyses(word)


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


def analyse(text: str) -> list[Token]:
    tagger, parser, lem, _ = _models()
    words = tokenize(text)
    tags = tagger.tag([("VALOR" if is_literal(w) else w) for w in words])
    arcs = parser.parse([("VALOR" if is_literal(w) else w) for w in words], tags)
    return make_tokens(words, tags, arcs)


def _descends(node: str, ancestor: str, world: World) -> bool:
    n = world.nodes[node]["parent"]
    while n is not None:
        if n == ancestor:
            return True
        n = world.nodes[n]["parent"]
    return False
