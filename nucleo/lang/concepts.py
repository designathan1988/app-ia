"""The concept graph: words of any language -> language-independent concepts -> what the machine can do.

Nodes:
- **concepts**, identified by the Interlingual Index (ILI) of the Global WordNet, shared by the Portuguese
  (OpenWordNet-PT) and English (Open English WordNet) wordnets;
- **entities** of the machine (an element type, a property, a value of a property, a command, an action frame).

Edges:
- word (of a language) -> concept: a sense of the word in that language's wordnet; earlier senses (more frequent)
  cost less;
- concept -> concept: the wordnet relations, which are the same in every language (similar, also, attribute,
  derivation, pertainym, hypernym...), each with a cost;
- concept -> entity: anchors computed from the builder's own English and Portuguese labels and the W3C keywords
  (English words), through the same word -> concept edges. Nothing is listed by hand.

The meaning of a word for the machine is every entity reachable from it, with the cost of the cheapest path (Dijkstra,
bounded), and the path as its explanation. Learned edges (from the user's answers) are added by ``learned``.

Built once into ``data/cache/conceitos.sqlite`` (``python -m nucleo.lang.concepts``).
"""

from __future__ import annotations

import gzip
import heapq
import json
import pathlib
import re
import sqlite3
import xml.etree.ElementTree as ET
from functools import lru_cache

from .values import fold

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "dicionario"
DB = ROOT / "data" / "cache" / "conceitos.sqlite"
# cost of following a relation between concepts (a synonym is the same concept: cost 0)
REL_COST = {"similar": 0.6, "also": 1.4, "attribute": 0.6, "derivation": 0.5, "pertainym": 0.6,
            "participle": 0.4, "hypernym": 1.2, "instance_hypernym": 1.5, "entails": 1.0, "causes": 1.0}
# (definition edges, concept -> the words of its English definition, are stored but not followed: measured, they
# added more noise than meaning — "sumir" reached "forma flexionada", "round" reached "along" — and did not lead
# "desaparecer" to hiding; docs/significado.md)
SENSE_STEP = 0.25  # each later sense of a word costs this much more
MAX_COST = 3.0
TRANSLATION_COST = 0.5


def _parse_lmf(path: pathlib.Path, lang: str, con: sqlite3.Connection) -> dict:
    opener = gzip.open if path.suffix == ".gz" else open
    ili_of: dict[str, str] = {}
    lex_rows, rel_rows, gloss_rows, sense_syn = [], [], [], {}
    sense_rels = []
    with opener(path, "rb") as f:
        for _, el in ET.iterparse(f, events=("end",)):
            tag = el.tag
            if tag == "LexicalEntry":
                lemma = el.find("Lemma")
                if lemma is not None:
                    word = fold(lemma.get("writtenForm") or "")
                    pos = lemma.get("partOfSpeech")
                    for rank, sense in enumerate(el.findall("Sense")):
                        syn = sense.get("synset")
                        sense_syn[sense.get("id")] = syn
                        lex_rows.append((lang, word, syn, pos, rank))
                        for r in sense.findall("SenseRelation"):
                            sense_rels.append((syn, r.get("target"), r.get("relType")))
                el.clear()
            elif tag == "Synset":
                sid = el.get("id")
                ili = el.get("ili")
                ili_of[sid] = ili if ili and ili != "in" else sid  # "in": a new concept without an ILI yet
                d = el.find("Definition")
                if d is not None and d.text:
                    gloss_rows.append((sid, lang, d.text))
                for r in el.findall("SynsetRelation"):
                    rel_rows.append((sid, r.get("target"), r.get("relType")))
                el.clear()
    # a lemma is a word or a short phrase; some entries of the Portuguese wordnet are example sentences
    lex_rows = [r for r in lex_rows if len(r[1].split()) <= 3 and re.fullmatch(r"[\w' -]+", r[1])]
    con.executemany("INSERT INTO lex VALUES (?,?,?,?,?)",
                    [(lg, w, ili_of.get(s, s), p, k) for lg, w, s, p, k in lex_rows])
    if lang != "en":
        # relations between concepts are the same in every language: they are taken from the English wordnet,
        # which is curated; the Portuguese one contributes its words (and definitions) only
        rel_rows, sense_rels = [], []
    con.executemany("INSERT INTO rel VALUES (?,?,?)",
                    [(ili_of.get(a, a), ili_of.get(b, b), t) for a, b, t in rel_rows if t in REL_COST])
    con.executemany("INSERT INTO rel VALUES (?,?,?)",
                    [(ili_of.get(a, a), ili_of.get(sense_syn.get(b, ""), ""), t) for a, b, t in sense_rels
                     if t in REL_COST and sense_syn.get(b)])
    con.executemany("INSERT INTO gloss VALUES (?,?,?)", [(ili_of.get(s, s), lg, g) for s, lg, g in gloss_rows])
    return {"palavras": len(lex_rows), "relacoes": len(rel_rows) + len(sense_rels), "definicoes": len(gloss_rows)}


def build() -> dict:
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.executescript("""
        CREATE TABLE lex (lang TEXT, word TEXT, concept TEXT, pos TEXT, rank INTEGER);
        CREATE TABLE rel (a TEXT, b TEXT, type TEXT);
        CREATE TABLE gloss (concept TEXT, lang TEXT, text TEXT);
    """)
    stats = {"en": _parse_lmf(SRC / "english-wordnet-2024.xml.gz", "en", con),
             "pt": _parse_lmf(SRC / "own-pt" / "own-pt-lmf.xml", "pt", con)}
    con.executescript("""
        CREATE INDEX lex_w ON lex(lang, word);
        CREATE INDEX lex_c ON lex(concept);
        CREATE INDEX gloss_c ON gloss(concept);
    """)
    stats["definicoes"] = _definition_edges(con)
    con.executescript("""
        CREATE INDEX rel_a ON rel(a);
        CREATE INDEX rel_b ON rel(b);
    """)
    con.commit()
    con.close()
    _anchors.cache_clear()
    return stats


GLOSS_SKIP = {"be", "have", "do", "make", "get", "give", "take", "put", "set", "go", "come", "become", "cause",
              "something", "someone", "somebody", "thing", "one", "way", "kind", "act", "state", "quality",
              "used", "especially", "usually", "often", "very", "more", "less", "much", "many", "other"}


def _definition_edges(con) -> int:
    """A concept -> the concepts of the content words of its English definition ("disappear: become invisible or
    unnoticeable" -> invisible, unnoticeable), each word in its first sense: the meaning a reader gets from a
    definition. Function words and the most general verbs ("become", "make") carry no meaning of their own and
    are skipped (they would connect everything)."""
    first: dict[str, str] = {}
    for word, concept, rank in con.execute("SELECT word, concept, rank FROM lex WHERE lang = 'en'"):
        if rank == 0 and word not in first:
            first[word] = concept
    rows = []
    for concept, text in con.execute("SELECT concept, text FROM gloss WHERE lang = 'en'").fetchall():
        seen = set()
        for w in re.findall(r"[a-z]+", text.lower()):
            if len(w) < 4 or w in GLOSS_SKIP or w in seen:
                continue
            seen.add(w)
            target = first.get(w) or (first.get(w[:-1]) if w.endswith("s") else None)
            if target and target != concept:
                rows.append((concept, target, "definition"))
    con.executemany("INSERT INTO rel VALUES (?,?,?)", rows)
    return len(rows)


@lru_cache(maxsize=1)
def _con():
    if not DB.exists():
        return None
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True, check_same_thread=False)


@lru_cache(maxsize=100_000)
def concepts_of(word: str, lang: str = "pt", pos: str | None = None) -> tuple[tuple[str, float], ...]:
    """(concept, cost) for each sense of a word in a language: the first sense costs least."""
    con = _con()
    if con is None:
        return ()
    rows = con.execute("SELECT concept, pos, rank FROM lex WHERE lang = ? AND word = ? ORDER BY rank",
                       (lang, fold(word))).fetchall()
    out: dict[str, float] = {}
    for c, p, rank in rows:
        if pos and p and p[0] != pos[0] and not (pos == "a" and p == "s"):
            continue
        out.setdefault(c, SENSE_STEP * rank)
    return tuple(sorted(out.items(), key=lambda x: x[1]))


DIRECTED = {"hypernym", "instance_hypernym", "entails", "causes", "definition"}  # followed only towards the more general


@lru_cache(maxsize=100_000)
def neighbours(concept: str) -> tuple[tuple[str, str], ...]:
    """Concepts one relation away. Generalization is followed upwards only: going up and then down again would
    connect every concept to every other through a few hubs ("act", "change")."""
    con = _con()
    out = con.execute("SELECT b, type FROM rel WHERE a = ?", (concept,)).fetchall()
    back = con.execute("SELECT a, type FROM rel WHERE b = ?", (concept,)).fetchall()
    return tuple(out) + tuple((a, t) for a, t in back if t not in DIRECTED)


def words_of(concept: str, lang: str) -> list[str]:
    con = _con()
    return [r[0] for r in con.execute("SELECT word FROM lex WHERE concept = ? AND lang = ? ORDER BY rank",
                                      (concept, lang))]


# -- anchors: the machine's entities as concepts --------------------------------------------------------------
def _catalogs():
    from ..builder.client import DEFAULT_BUILDER

    base = pathlib.Path(DEFAULT_BUILDER) / "src" / "i18n" / "locales"
    return (json.loads((base / "en.json").read_text(encoding="utf-8")),
            json.loads((base / "pt-BR.json").read_text(encoding="utf-8")))


def _label_concepts(label: str, lang: str) -> list[tuple[str, float]]:
    """Concepts a label names: the whole label if the wordnet has it ("background color"), else its head word
    (the last word in English, "text color" -> color; the first in Portuguese, "cor do texto" -> cor), costlier."""
    words = re.findall(r"[A-Za-zÀ-ÿ]+", label.lower())
    if not words:
        return []
    whole = concepts_of(" ".join(words), lang)
    if whole:
        return list(whole)
    head = words[-1] if lang == "en" else words[0]
    return [(c, k + 0.5 * (len(words) > 1)) for c, k in concepts_of(head, lang)]


@lru_cache(maxsize=1)
def _anchors() -> dict[str, list[tuple[tuple, float]]]:
    """concept -> [(entity, cost)]. Entities: ("tipo", id), ("propriedade", id), ("valor", (prop, keyword)),
    ("comando", id), ("acao", frame id)."""
    from ..builder.client import DEFAULT_BUILDER
    from . import command_verbs
    from .values import _builder_properties, _keywords, color_properties, named_colors, GLOBAL

    en, pt = _catalogs()
    man = pathlib.Path(DEFAULT_BUILDER) / "manifest"
    out: dict[str, list] = {}

    def anchor(entity, label, lang, extra=0.0, limit=6):
        for c, k in _label_concepts(label, lang)[:limit]:
            out.setdefault(c, []).append((entity, k + extra))

    for e in json.loads((man / "elements.json").read_text(encoding="utf-8"))["elements"]:
        key = e.get("labelKey")
        for cat, lang in ((en, "en"), (pt, "pt")):
            if key in cat:
                anchor(("tipo", e["id"]), cat[key], lang)
    for pid, p in _builder_properties().items():
        key = p.get("labelKey")
        for cat, lang in ((en, "en"), (pt, "pt")):
            if key in cat:
                anchor(("propriedade", pid), cat[key], lang, extra=0.3)
        # its keywords are English words: each names a value of this property
        for kw in sorted(_keywords(pid) - GLOBAL):
            if re.fullmatch(r"[a-z]+(-[a-z]+)*", kw):
                anchor(("valor", (pid, kw)), kw.replace("-", " "), "en", extra=0.2, limit=2)
    for color in sorted(named_colors()):
        for c, k in concepts_of(color, "en")[:1]:  # a color word's first sense is the color
            for p in color_properties():
                out.setdefault(c, []).append((("valor", (p, color)), k))
    from ..builder.scenarios import load_commands as _lc

    _cmds = _lc()
    # (the Portuguese table, which carries each command's English verb: the same whatever language is read first)
    for verbs in command_verbs._table("pt").values():
        for cv in verbs:
            if cv.english and not cv.rest:
                for c, k in concepts_of(cv.english, "en", "v")[:3]:
                    out.setdefault(c, []).append((("comando", cv.command), k))
            elif cv.rest:
                # a multiword label ("Move up") is one verb in the wordnet ("move up" = rise), or the verbs whose
                # definition says it ("descend: move downward", "rise: move upward")
                label = en.get(_cmds.get(cv.command, {}).get("labelKey") or "", "").lower()
                for c, k in concepts_of(label, "en", "v")[:2]:
                    out.setdefault(c, []).append((("comando", cv.command), k))
                for c in _defined_as(tuple(re.findall(r"[a-z]+", label))):
                    out.setdefault(c, []).append((("comando", cv.command), 0.3))
    # actions: anchored by the English label of the builder command that performs them, first sense only
    # (a Portuguese verb like "apagar" also means "to conceal": anchoring through it would mix the actions)
    from .builder_commands import FRAME_COMMANDS
    from ..builder.scenarios import load_commands

    commands = load_commands()
    for frame, cid in FRAME_COMMANDS.items():
        label = en.get(commands.get(cid, {}).get("labelKey") or "", "")
        verb = (re.findall(r"[A-Za-z]+", label) or [""])[0].lower()
        for c, k in concepts_of(verb, "en", "v")[:1]:
            out.setdefault(c, []).append((("acao", frame), 0.2))
        # and by the frame's own name, a Portuguese verb, in its first sense ("remover" = remove, take away)
        for c, k in concepts_of(frame, "pt", "v")[:1]:
            out.setdefault(c, []).append((("acao", frame), 0.3))
    return out


@lru_cache(maxsize=256)
def _defined_as(words: tuple) -> list[str]:
    """Verb concepts whose English definition begins with these words, each word or a longer form of it ("move
    down" -> "move downward ..."): the verbs the wordnet defines as that phrase."""
    if not words:
        return []
    con = _con()
    pattern = r"^\W*" + r"\W+".join(re.escape(w) + r"\w*" for w in words) + r"\b"
    out = []
    for concept, text in con.execute("SELECT g.concept, g.text FROM gloss g JOIN lex l ON l.concept = g.concept "
                                     "WHERE g.lang = 'en' AND l.lang = 'en' AND l.pos = 'v' AND g.text LIKE ?",
                                     (words[0] + " %",)):
        if re.match(pattern, text.lower()) and concept not in out:
            out.append(concept)
    return out[:6]


def meanings(word: str, lang: str = "pt", pos: str | None = None, limit: float = MAX_COST) -> list[tuple]:
    """[(entity, cost, path)] reachable from a word through concepts, cheapest first. The path lists the concepts
    and relations followed, in a readable form (the words of each concept)."""
    anchors = _anchors()
    start = list(concepts_of(word, lang, pos))
    if lang != "en":
        # a word the language's wordnet lacks (or lacks a sense of) also reaches concepts through its dictionary
        # translations into English ("negrito" -> "bold")
        from . import dictionary

        for t in dictionary.translations(word):
            start += [(c, k + TRANSLATION_COST) for c, k in concepts_of(t, "en", pos)]
    dist: dict[str, float] = {}
    heap = [(k, c, ((c, "sentido"),)) for c, k in start]
    best: dict[tuple, tuple] = {}
    seen = 0
    while heap and seen < 4000:
        d, c, path = heapq.heappop(heap)
        if c in dist or d > limit:
            continue
        dist[c] = d
        seen += 1
        for entity, k in anchors.get(c, ()):
            total = d + k
            if total <= limit and (entity not in best or total < best[entity][0]):
                best[entity] = (total, path)
        for nb, t in neighbours(c):
            step = REL_COST.get(t)
            if step is not None and nb not in dist and d + step <= limit:
                heapq.heappush(heap, (d + step, nb, path + ((nb, t),)))
    # Consumers cap the retrieved list: ties must not inherit set/cache order.
    return sorted(((e, v[0], v[1]) for e, v in best.items()), key=lambda x: (x[1], x[0]))


def explain(path: tuple, lang: str = "pt") -> str:
    parts = []
    for c, how in path:
        ws = words_of(c, lang) or words_of(c, "en")
        parts.append(f"{ws[0] if ws else c}" + ("" if how == "sentido" else f" ({how})"))
    return " → ".join(parts)


if __name__ == "__main__":
    import sys
    import time

    sys.path.insert(0, str(ROOT))
    from nucleo.session import low_priority

    low_priority()
    t = time.time()
    print(build(), f"{time.time() - t:.0f}s")
