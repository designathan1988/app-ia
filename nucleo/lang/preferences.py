"""Preferences learned from use: which reading of a verb the user keeps, and which one they undo.

Every executed request is evidence for its reading (verb lemma, frame). Undoing it right after is evidence against.
The cost of a reading grows with the share of times it was undone (a frequency with a confidence that grows with
the number of observations, in the spirit of NARS truth values): ``PENALTY * undone / (kept + undone + 1)``. A
reading undone once costs a little more; one undone every time costs up to PENALTY, which is enough for another
reading to win, or for a close call to be asked instead of executed.

Stored in ``data/preferencias.json``; nothing else is inferred from it.
"""

from __future__ import annotations

import json
import pathlib

STORE = pathlib.Path(__file__).resolve().parents[2] / "data" / "preferencias.json"
PENALTY = 2.0


def _load() -> dict:
    return json.loads(STORE.read_text(encoding="utf-8")) if STORE.exists() else {}


def _save(d: dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def _key(verb: str, frame: str) -> str:
    return f"{verb}|{frame}"


def kept(verb: str, frame: str) -> None:
    d = _load()
    e = d.setdefault(_key(verb, frame), {"mantido": 0, "desfeito": 0})
    e["mantido"] += 1
    _save(d)


def undone(verb: str, frame: str) -> None:
    d = _load()
    e = d.setdefault(_key(verb, frame), {"mantido": 0, "desfeito": 0})
    e["mantido"] = max(0, e["mantido"] - 1)
    e["desfeito"] += 1
    _save(d)


def penalty(verb: str, frame: str) -> float:
    e = _load().get(_key(verb, frame))
    if not e:
        return 0.0
    return PENALTY * e["desfeito"] / (e["mantido"] + e["desfeito"] + 1)
