"""Versioned persistence of the knowledge base in SQLite.

Nothing is ever overwritten.

* Every change happens inside a **transaction** (``tx``), which records who
  made it, why, and when.
* A sentence (fact, rule, world declaration or priority) is a row, stored in its
  canonical text, with the context it belongs to, its source, the tx that
  asserted it and, once retracted, the tx that retracted it.
* ``contexts(as_of=t)`` rebuilds the knowledge exactly as it was after tx ``t``.
  The sentences active at ``t`` are those asserted at or before ``t`` and not
  retracted at or before ``t``. Context definitions are versioned the same way.

The canonical text is the parser's own rendering (``str`` of the parsed item),
so re-asserting the same sentence written differently is recognised as the
same sentence. The round trip ``parse(str(x)) == x`` is tested.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass

from ..kb.contexts import Contexts
from ..kb.syntax import parse_program

SCHEMA = """
CREATE TABLE IF NOT EXISTS tx (
    id INTEGER PRIMARY KEY,
    quando TEXT NOT NULL,
    autor TEXT NOT NULL,
    nota TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contexto (
    nome TEXT NOT NULL,
    pais TEXT NOT NULL,           -- JSON list, parents defined before children
    criado_tx INTEGER NOT NULL REFERENCES tx(id),
    removido_tx INTEGER REFERENCES tx(id)
);
CREATE TABLE IF NOT EXISTS sentenca (
    id INTEGER PRIMARY KEY,
    contexto TEXT NOT NULL,
    tipo TEXT NOT NULL,           -- fato | regra | mundo | prioridade
    texto TEXT NOT NULL,          -- canonical text
    fonte TEXT,
    add_tx INTEGER NOT NULL REFERENCES tx(id),
    rem_tx INTEGER REFERENCES tx(id)
);
CREATE INDEX IF NOT EXISTS sentenca_ativa ON sentenca(contexto, texto, rem_tx);
CREATE INDEX IF NOT EXISTS sentenca_tx ON sentenca(add_tx, rem_tx);
"""


class StoreError(ValueError):
    pass


def sentences(src: str) -> list[tuple[str, str]]:
    """(kind, canonical text) of every sentence in `src`, in order."""
    prog = parse_program(src)
    out = [("mundo", f"pred {n}/{a} {w}.") for (n, a), w in prog.worlds.items()]
    out += [("fato", f"{f}.") for f in prog.facts]
    out += [("regra", str(r)) for r in prog.rules]
    out += [("prioridade", f"@{hi} > @{lo}.") for hi, lo in sorted(prog.priorities)]
    return out


@dataclass
class Row:
    id: int
    contexto: str
    tipo: str
    texto: str
    fonte: str | None
    add_tx: int
    rem_tx: int | None


class Transaction:
    def __init__(self, store: "Store", tx: int) -> None:
        self.store = store
        self.id = tx
        self._db = store._db

    def define(self, name: str, parents: tuple[str, ...] | list[str] = ()) -> None:
        active = self.store._active_contexts(self._db, None)
        if name in active:
            raise StoreError(f"contexto já existe: {name}")
        for p in parents:
            if p not in active:
                raise StoreError(f"contexto pai inexistente: {p}")
        self._db.execute("INSERT INTO contexto(nome, pais, criado_tx) VALUES (?,?,?)",
                         (name, json.dumps(list(parents)), self.id))

    def drop(self, name: str) -> None:
        active = self.store._active_contexts(self._db, None)
        if name not in active:
            raise StoreError(f"contexto inexistente: {name}")
        children = [c for c, ps in active.items() if name in ps]
        if children:
            raise StoreError(f"{name} tem contextos filhos: {children}")
        self._db.execute("UPDATE contexto SET removido_tx=? WHERE nome=? AND removido_tx IS NULL", (self.id, name))
        self._db.execute("UPDATE sentenca SET rem_tx=? WHERE contexto=? AND rem_tx IS NULL", (self.id, name))

    def _require(self, ctx: str) -> None:
        if ctx not in self.store._active_contexts(self._db, None):
            raise StoreError(f"contexto inexistente: {ctx}")

    def assert_(self, ctx: str, src: str, fonte: str | None = None) -> list[int]:
        """Assert every sentence of `src` in `ctx`. An already-active sentence is left as it is."""
        self._require(ctx)
        ids = []
        for kind, text in sentences(src):
            row = self._db.execute(
                "SELECT id FROM sentenca WHERE contexto=? AND texto=? AND rem_tx IS NULL", (ctx, text)
            ).fetchone()
            if row:
                ids.append(row[0])
                continue
            cur = self._db.execute(
                "INSERT INTO sentenca(contexto, tipo, texto, fonte, add_tx) VALUES (?,?,?,?,?)",
                (ctx, kind, text, fonte, self.id),
            )
            ids.append(cur.lastrowid)
        # every view must stay loadable (a parent's change can break a child's view): check now, not at the next read
        kb = self.store._load(self._db, None)
        for name in kb.names():
            kb.view(name)
        return ids

    def retract(self, ctx: str, src: str) -> None:
        self._require(ctx)
        for _, text in sentences(src):
            cur = self._db.execute(
                "UPDATE sentenca SET rem_tx=? WHERE contexto=? AND texto=? AND rem_tx IS NULL", (self.id, ctx, text)
            )
            if cur.rowcount == 0:
                raise StoreError(f"{ctx}: sentença não está ativa: {text}")


class Store:
    def __init__(self, path: str) -> None:
        self.path = path
        self._db = sqlite3.connect(path, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def head(self) -> int:
        return self._db.execute("SELECT COALESCE(MAX(id), 0) FROM tx").fetchone()[0]

    @contextmanager
    def transaction(self, autor: str, nota: str):
        """All-or-nothing: an error inside the block rolls back every change of the transaction."""
        self._db.execute("BEGIN IMMEDIATE")
        try:
            quando = datetime.datetime.now(datetime.timezone.utc).isoformat()
            tx = self._db.execute("INSERT INTO tx(quando, autor, nota) VALUES (?,?,?)", (quando, autor, nota)).lastrowid
            yield Transaction(self, tx)
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        self._db.execute("COMMIT")

    @staticmethod
    def _active_contexts(db, as_of: int | None) -> dict[str, list[str]]:
        t = as_of if as_of is not None else 1 << 62
        rows = db.execute(
            "SELECT nome, pais FROM contexto WHERE criado_tx<=? AND (removido_tx IS NULL OR removido_tx>?) "
            "ORDER BY criado_tx, rowid",
            (t, t),
        ).fetchall()
        return {name: json.loads(parents) for name, parents in rows}

    def _load(self, db, as_of: int | None) -> Contexts:
        t = as_of if as_of is not None else 1 << 62
        kb = Contexts()
        for name, parents in self._active_contexts(db, as_of).items():
            kb.define(name, parents)
        order = {"mundo": 0, "fato": 1, "regra": 2, "prioridade": 3}
        texts: dict[str, list[tuple[int, int, str]]] = {}
        for ctx, kind, text, rid in db.execute(
            "SELECT contexto, tipo, texto, id FROM sentenca WHERE add_tx<=? AND (rem_tx IS NULL OR rem_tx>?)", (t, t)
        ):
            texts.setdefault(ctx, []).append((order[kind], rid, text))
        for ctx, items in texts.items():
            if ctx in kb:
                kb.add(ctx, "\n".join(text for _, _, text in sorted(items)))
        return kb

    def contexts(self, as_of: int | None = None) -> Contexts:
        """The knowledge base as it was right after transaction `as_of` (default: now)."""
        return self._load(self._db, as_of)

    def history(self, ctx: str, src: str) -> list[Row]:
        """Every assertion and retraction of the sentences of `src` in `ctx`."""
        out = []
        for _, text in sentences(src):
            for r in self._db.execute(
                "SELECT id, contexto, tipo, texto, fonte, add_tx, rem_tx FROM sentenca "
                "WHERE contexto=? AND texto=? ORDER BY id", (ctx, text)
            ):
                out.append(Row(*r))
        return out

    def transactions(self) -> list[tuple[int, str, str, str]]:
        return self._db.execute("SELECT id, quando, autor, nota FROM tx ORDER BY id").fetchall()
