"""Teaching by definition: "X significa Y" / "X means Y" (plan Part I §5: vocabulary, constructions, structures).

What is taught is accepted only when its definition is understood, by the same engine that understands requests:

- **a verb** ("blorfar significa definir o alinhamento do texto como center"): the definition is a request the
  engine understands on some element; the verb is then read through it ("blorfe o título");
- **a structure** ("card significa um artigo com um título com o texto "Plano" e um botão"): the head type and
  its parts, each a type with, optionally, its text; read from the definition's logical form (the head phrase, the
  phrases attached to it and their coordination, the fields of each part), not from a pattern of words;
- **a phrase** ("zorbo significa fundo"): another name for an entity of the builder's catalog.

The verb of definition ("significar", "mean") is the language profile's closed class ``means``.
"""

from __future__ import annotations

from . import alternatives, langs, learned, lexicon
from . import ground as gr
from . import logic_form as lf
from .values import fold

KINDS = {"tipo", "propriedade", "atributo", "estado", "breakpoint"}


def definition(text: str, world, by: str = "usuario"):
    """The Understanding of a definition, or None when the text is not one."""
    from .base import Understanding, World

    analyses = alternatives.analyses(text)
    if not analyses:
        return None
    tokens = analyses[0].tokens
    means = {fold(w) for w in langs.profile().get("means", set())}
    k = next((i for i, t in enumerate(tokens) if fold(t.lemma) in means or fold(t.form.lower()) in means), None)
    if k is None or k == 0 or k == len(tokens) - 1:
        return None
    x = " ".join(t.form for t in tokens[:k]).strip().lower()
    y = " ".join(t.form for t in tokens[k + 1:]).strip().strip(".")
    said = lambda pt, en: pt if langs.current() == "pt" else en  # noqa: E731
    # a verb: one word that is (or is formed as) an infinitive, defined by a request
    if k == 1 and _infinitive(tokens[0].form):
        from .interpret import understand

        verb = tokens[0].form.lower()
        probe = World(world.nodes, world.selection[:1] or list(world.nodes)[:1], world.layer)
        u = understand(y, probe)
        if u.decision != "executar" and not (u.decision == "perguntar" and u.best and u.best.constraints):
            return Understanding(text, tokens, [], "nao_entendi",
                                 said(f"Não aprendi «{verb}»: não entendi a definição «{y}».",
                                      f"I did not learn «{verb}»: I did not understand «{y}»."))
        learned.add_verb(verb, y, text, by)
        return Understanding(text, tokens, [], "aprendido",
                             said(f"Aprendi: «{verb}» = «{y}» (sobre o elemento que você disser).",
                                  f"Learned: «{verb}» = «{y}» (on the element you name)."))
    structure = _structure(y, world)
    if structure is not None:
        if isinstance(structure, str):
            return Understanding(text, tokens, [], "nao_entendi", said(f"Não aprendi «{x}»: {structure}.",
                                                                       f"I did not learn «{x}»: {structure}."))
        head, parts = structure
        learned.add_structure(x, head, parts, text, by)
        listed = ", ".join(p["type"] + (f' «{p["text"]}»' if p.get("text") else "") for p in parts)
        return Understanding(text, tokens, [], "aprendido", said(f"Aprendi: «{x}» = {head} com {listed}.",
                                                                 f"Learned: «{x}» = {head} with {listed}."))
    seq = lexicon.lemma_seq(y)
    hits = [e for e in lexicon.load() if e.lemmas == seq and e.kind in KINDS]
    if not hits:
        return Understanding(text, tokens, [], "nao_entendi",
                             said(f"Não aprendi «{x}»: «{y}» não é algo que eu conheça no builder.",
                                  f"I did not learn «{x}»: «{y}» is nothing I know in the builder."))
    learned.add_phrase(x, hits[0].kind, hits[0].id, text, by)
    return Understanding(text, tokens, [], "aprendido", said(f"Aprendi: «{x}» = «{hits[0].label}» ({hits[0].id}).",
                                                             f"Learned: «{x}» = «{hits[0].label}» ({hits[0].id})."))


def _infinitive(word: str) -> bool:
    """A verb's citation form: an infinitive in the morphology, or a word formed as one (an invented verb)."""
    if langs.current() != "pt":
        return word.isalpha()
    from .morph import analyses

    w = word.lower()
    found = analyses(w)
    return any(tags.startswith("V+INF") for _, tags in found) or (not found and w[-2:] in ("ar", "er", "ir")
                                                                   and len(w) > 3)


def _structure(body: str, world):
    """A composite element described by its definition's logical form: an indefinite phrase naming a type, with
    phrases attached to it naming the parts ("um artigo com um título com o texto "X" e um botão"). Returns (head
    type, parts), a message when a part is not understood, or None when the definition is no structure."""
    from .interpret import _new_element_fields

    analyses = alternatives.analyses(body)
    if not analyses:
        return None
    sentence = lf.build(analyses[0].tokens)
    heads = [m for p in sentence.predicates for r, _, m in p.roles if isinstance(m, lf.Mention)]
    roots = [t for t in analyses[0].tokens if t.head == 0]
    if roots and roots[0].upos in ("NOUN", "PROPN"):
        kids = {}
        for t in analyses[0].tokens:
            kids.setdefault(t.head, []).append(t)
        heads.insert(0, lf.mention(roots[0], kids))
    for m in heads:
        if m.det != "indefinite" or not m.attached:
            continue
        kinds = gr.kinds(m)
        if not kinds:
            continue
        parts = []
        # the parts: every phrase reached through the phrases attached to the head and their coordinations, at any
        # depth ("com um título com o texto 'X' e um botão": the button may hang under the title's text phrase);
        # a phrase that says a field ("o texto 'X'") is that part's text, not a part
        terms, stack = [], [x for _, x in m.attached]
        while stack:
            term = stack.pop(0)
            if any(d.kind == "field" for d in gr.properties(term, world)):
                stack = list(term.conj) + stack
                continue
            terms.append(term)
            stack = list(term.conj) + [x for _, x in term.attached] + stack
        for term in terms:
            part_kinds = gr.kinds(term) or gr.kinds(lf.Mention(term.head, term.words, det="indefinite"))
            own = {t.i for t in gr._content(term)}
            if not part_kinds or not own <= set(part_kinds[0].words):
                # (every word of the part must be explained by the type it names: "um carrossel mágico" is not)
                return f"não conheço a parte «{' '.join(t.form for t in term.words)}»"
            part = {"type": part_kinds[0].data}
            fields, _ = _new_element_fields(term, world)
            if fields.get("text"):
                part["text"] = fields["text"]
            for _ in range(next((int(n.split("=")[1]) for n in part_kinds[0].notes if n.startswith("n=")), 1)):
                parts.append(dict(part))
        if parts:
            return kinds[0].data, parts
    return None
