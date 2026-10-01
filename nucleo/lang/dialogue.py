"""Dialogue state: what is under discussion, and how a short reply continues it (GoDiS-style information state).

After the system asks ("Qual deles: «Título», «Subtítulo»?", "Você quer dizer A ou B?", "É isso? (sim/não)", "Não
conheço o verbo «x». O que ele deve fazer?"), the question stays open for the next message. A reply is read against
it before anything else:
- yes / no ("sim", "isso", "pode"; "não", "cancela");
- an ordinal ("o segundo", "2", "o último");
- words that pick one option (an element's name, a word of one paraphrase: "o fundo", "Subtítulo");
- for an unknown verb: a request that shows what the verb does ("deixe o texto vermelho").

After an action, its constraints stay as the last thing done, so an elliptical follow-up repeats it on another
element ("faça o mesmo no botão", "no parágrafo também").

Answers are learning evidence (``learned.add_to_class``): a verb confirmed in a meaning joins that meaning's verb
class, by induction from one example, with its provenance.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

from .lexicon import lemma_of
from .values import fold

YES = {"sim", "isso", "pode", "ok", "exato", "certo", "correto", "claro", "confirmo", "isso mesmo", "pode ser",
       "faz", "faca", "manda", "s", "yes", "yeah", "yep", "sure", "right", "do it", "go ahead", "correct", "y"}
NO = {"nao", "cancela", "cancelar", "esquece", "nenhum", "nenhuma", "n", "deixa", "deixa pra la", "no", "nope",
      "cancel", "never mind", "none"}
ORDINALS = {"primeiro": 0, "primeira": 0, "1": 0, "um": 0, "segundo": 1, "segunda": 1, "2": 1, "dois": 1,
            "terceiro": 2, "terceira": 2, "3": 2, "tres": 2, "quarto": 3, "quarta": 3, "4": 3,
            "first": 0, "one": 0, "second": 1, "two": 1, "third": 2, "three": 2, "fourth": 3}
ELLIPSIS = {"mesmo", "mesma", "tambem", "igual", "igualmente", "same", "too", "also", "likewise"}


@dataclass
class Pending:
    text: str  # the request that raised the question
    options: list  # Readings, in the order they were offered
    verb: str = ""  # an unknown verb, when that was the question


@dataclass
class State:
    pending: Pending | None = None
    last_constraints: list = field(default_factory=list)
    last_nodes: list = field(default_factory=list)
    last_reading: object = None  # the reading of the last action (for "por quê?")


def _words(text: str) -> list[str]:
    return [fold(w) for w in re.findall(r"[\wÀ-ÿ#-]+", text.lower())]


def options_from(u, world) -> Pending | None:
    """The question an understanding asked, as options a reply can choose from."""
    if u.decision != "perguntar" or not u.readings:
        return None
    best = u.readings[0]
    if best.unknown_verb:
        return Pending(u.text, [], best.verb)
    if best.ambiguous:
        opts = []
        for n in best.ambiguous:
            r = copy.deepcopy(best)
            r.constraints = _replace(r.constraints, best.ambiguous[0], n)
            r.ambiguous = []
            r.paraphrase = f"{best.paraphrase} [{world.nodes[n]['name']}]"
            r.target_name = world.nodes[n]["name"]
            opts.append(r)
        return Pending(u.text, opts)
    rivals = [r for r in u.readings[1:] if r.cost - best.cost < 1.0 and r.constraints != best.constraints
              and not (r.unknown_verb and not best.unknown_verb)][:2]
    return Pending(u.text, [best] + rivals)


def _replace(obj, old, new):
    if isinstance(obj, dict):
        return {k: _replace(v, old, new) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_replace(v, old, new) for v in obj]
    return new if obj == old else obj


def choose(p: Pending, reply: str):
    """The option a reply picks: a Reading, "nao" for a refusal, or None when the reply is not an answer."""
    ws = _words(reply)
    if not ws or not p.options:
        return None
    joined = " ".join(ws)
    if joined in NO or ws[0] in NO:
        return "nao"
    if joined in YES or (ws[0] in YES and len(ws) <= 3):
        return p.options[0]
    for w in ws:
        if w in ORDINALS and ORDINALS[w] < len(p.options):
            return p.options[ORDINALS[w]]
        if w in ("ultimo", "ultima", "last"):
            return p.options[-1]
    # words that pick one option: an element's name, or words of its paraphrase ("o fundo", "a cor do texto")
    lem = {fold(lemma_of(w)) for w in ws if len(w) > 2}
    scores = []
    for r in p.options:
        name = fold(getattr(r, "target_name", "") or "")
        para = {fold(lemma_of(w)) for w in re.findall(r"[\wÀ-ÿ]+", r.paraphrase.lower()) if len(w) > 2}
        scores.append((2 if name and name in ws else 0) + len(lem & para))
    top = max(scores)
    if top > 0 and scores.count(top) == 1:
        return p.options[scores.index(top)]
    return None


def is_ellipsis(text: str) -> bool:
    return bool(set(_words(text)) & ELLIPSIS)


def ellipsis_target(text: str, world) -> str | None:
    """The element an elliptical follow-up names ("faça o mesmo no botão" -> the button): by name, else by a type
    that has one element."""
    from . import lexicon

    ws = _words(text)
    named = [n for n, v in world.nodes.items() if v["name"] and fold(v["name"]) in ws]
    if len(named) == 1:
        return named[0]
    for i in range(len(ws)):
        hits = lexicon.match(tuple(fold(lemma_of(w)) for w in ws), {"tipo"}, i)
        if hits:
            typ = hits[0][0].id
            of_type = [n for n, v in world.nodes.items() if v["type"] == typ]
            if len(of_type) == 1:
                return of_type[0]
            sel = [n for n in of_type if n in world.selection]
            if len(sel) == 1:
                return sel[0]
    return None


def repeat_on(constraints: list, old_nodes: list, node: str) -> list:
    out = copy.deepcopy(constraints)
    for old in old_nodes:
        out = _replace(out, old, node)
    return out
