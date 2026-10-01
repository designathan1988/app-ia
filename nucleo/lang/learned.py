"""Vocabulary taught in Portuguese, by definition (Voxelurn: a user extends a core language by defining new words
in terms of words it already understands).

Two kinds of definition, both said as "X significa Y":

* **a verb** — "centralizar significa definir o alinhamento do texto como center". The definition is a request in
  the core language, without its object. When "centralize o título" arrives, the object of the new sentence is put
  into the definition ("definir o alinhamento do texto como center de o título"), and that is understood as usual.
  The learned verb therefore means exactly what its definition means, with the same checks.
* **a phrase** — "cor de fundo significa fundo". Y must name something the lexicon already grounds (a property, a
  type, ...). X becomes another label of the same entity.

A definition is accepted only if its body is understood. It is stored with the sentence, the date and who taught it
(``data/vocabulario.json``) and can be removed. Nothing is learned from a definition that is itself not understood.
"""

from __future__ import annotations

import datetime
import json
import pathlib

from . import lexicon

STORE = pathlib.Path(__file__).resolve().parents[2] / "data" / "vocabulario.json"


def _load() -> dict:
    if STORE.exists():
        return json.loads(STORE.read_text(encoding="utf-8"))
    return {"verbos": {}, "expressoes": {}, "estruturas": {}}


def _save(d: dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def verbs() -> dict:
    return _load()["verbos"]


def structures() -> dict:
    return _load().get("estruturas", {})


def add_structure(name: str, head: str, parts: list[dict], sentence: str, by: str) -> None:
    """A composite element: `head` (an element type) holding `parts` ([{"type", "text"?}], in order)."""
    d = _load()
    d.setdefault("estruturas", {})[name] = {"cabeca": head, "partes": parts, "frase": sentence, "por": by,
                                           "quando": datetime.datetime.now().isoformat(timespec="seconds")}
    _save(d)
    lexicon.load.cache_clear()


def phrases() -> dict:
    return _load()["expressoes"]


def add_verb(lemma: str, body: str, sentence: str, by: str) -> None:
    d = _load()
    d["verbos"][lemma] = {"definicao": body, "frase": sentence, "por": by,
                          "quando": datetime.datetime.now().isoformat(timespec="seconds")}
    _save(d)


def add_phrase(phrase: str, kind: str, entity: str, sentence: str, by: str) -> None:
    d = _load()
    d["expressoes"][phrase] = {"tipo": kind, "entidade": entity, "frase": sentence, "por": by,
                               "quando": datetime.datetime.now().isoformat(timespec="seconds")}
    _save(d)
    lexicon.load.cache_clear()


def classes() -> dict:
    """verb -> the frame it was induced to belong to, from use."""
    return {v: e["quadro"] for v, e in _load().get("classes", {}).items()}


def add_to_class(verb: str, frame: str, sentence: str, by: str) -> None:
    """Induction from use (one confirmed example): a verb the system did not know, used in a request whose meaning
    was confirmed (the user kept the result, or answered the question), joins the verb class of that meaning's frame,
    the way a verb class is learned from the frames it is seen in (Levin, VerbNet). It then works with any object
    and value, not only the ones of that sentence."""
    d = _load()
    d.setdefault("classes", {})[verb] = {"quadro": frame, "frase": sentence, "por": by,
                                         "quando": datetime.datetime.now().isoformat(timespec="seconds")}
    _save(d)


def forget(word: str) -> bool:
    d = _load()
    hit = d["verbos"].pop(word, None) or d["expressoes"].pop(word, None) or \
        d.setdefault("estruturas", {}).pop(word, None) or d.setdefault("classes", {}).pop(word, None)
    _save(d)
    lexicon.load.cache_clear()
    return hit is not None
