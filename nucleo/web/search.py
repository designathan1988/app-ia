"""Technical search without API keys: a local index of the web platform's reference data, plus the npm registry.

* **Local** (offline, exact): MDN's browser-compat-data (every CSS property, HTML element, JS/Web API with its MDN
  page, spec, status and browser support) and the W3C CSS definitions (@webref/css: property value grammars),
  both installed with builder-6, indexed in SQLite FTS5 (``data/cache/busca.sqlite``).
* **Live**: the npm registry's search (key-free JSON; the registry has no robots.txt restriction), through the polite
  fetcher, and MDN's own search (JSON) for its articles.

Results say where they come from. A search result is a document, not knowledge: using it as knowledge goes through
claims, verification and approval (``claims.py``).
"""

from __future__ import annotations

import json
import pathlib
import re
import sqlite3
from dataclasses import dataclass
from urllib.parse import quote

from ..builder.client import DEFAULT_BUILDER
from .fetcher import Fetcher

INDEX = pathlib.Path(__file__).resolve().parents[2] / "data" / "cache" / "busca.sqlite"
BROWSERS = ("chrome", "firefox", "safari", "edge")


@dataclass
class Hit:
    title: str
    summary: str
    url: str
    source: str  # "mdn-bcd" | "webref" | "npm"


def _support(compat: dict) -> str:
    parts = []
    for b in BROWSERS:
        s = (compat.get("support") or {}).get(b)
        s = s[0] if isinstance(s, list) and s else s
        if isinstance(s, dict):
            parts.append(f"{b} {s.get('version_added')}")
    st = compat.get("status") or {}
    flags = [k for k in ("deprecated", "experimental") if st.get(k)]
    return ", ".join(parts) + (f" ({', '.join(flags)})" if flags else "")


def build_index(root: str | None = None) -> int:
    nm = pathlib.Path(root or DEFAULT_BUILDER) / "node_modules"
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    if INDEX.exists():
        INDEX.unlink()
    con = sqlite3.connect(INDEX)
    con.execute("CREATE VIRTUAL TABLE doc USING fts5(title, body, url UNINDEXED, source UNINDEXED)")
    rows = []
    bcd = json.loads((nm / "@mdn" / "browser-compat-data" / "data.json").read_text(encoding="utf-8"))

    def walk(node, path):
        for k, v in node.items():
            if k == "__compat" or not isinstance(v, dict):
                continue
            p = path + [k]
            c = v.get("__compat")
            if c:
                title = ".".join(p)
                words = " ".join(re.split(r"[._\-]", title))
                rows.append((title, f"{words}. {c.get('description', '')} Suporte: {_support(c)}",
                             c.get("mdn_url") or "", "mdn-bcd"))
            walk(v, p)

    for top in ("css", "html", "api", "javascript", "http", "svg"):
        walk(bcd.get(top, {}), [top])
    webref = json.loads((nm / "@webref" / "css" / "css.json").read_text(encoding="utf-8"))
    for kind in ("properties", "functions", "types", "atrules", "selectors"):
        for item in webref.get(kind, []):
            name = item.get("name")
            if name:
                rows.append((f"css {kind[:-1]} {name}", f"{name}: {item.get('syntax') or item.get('value') or ''}",
                             item.get("href") or "", "webref"))
    con.executemany("INSERT INTO doc VALUES (?,?,?,?)", rows)
    con.commit()
    con.close()
    return len(rows)


def local(query: str, limit: int = 8) -> list[Hit]:
    if not INDEX.exists():
        build_index()
    terms = [t for t in re.findall(r"[\w-]+", query.lower()) if len(t) > 1]
    if not terms:
        return []
    quoted = ['"' + t.replace('"', "") + '"' for t in terms]
    con = sqlite3.connect(INDEX)
    rows = []
    # every term first; any term only when nothing has them all (and then only for one-word misses)
    for expr in (" AND ".join(quoted), " OR ".join(quoted) if len(quoted) <= 2 else None):
        if expr is None:
            continue
        rows = con.execute("SELECT title, body, url, source, bm25(doc, 10.0, 1.0) FROM doc WHERE doc MATCH ? "
                           "ORDER BY bm25(doc, 10.0, 1.0) LIMIT ?", (expr, limit * 4)).fetchall()
        if rows:
            break
    con.close()
    # main entries before their sub-entries (css.properties.display before css.properties.display.grid)
    rows.sort(key=lambda r: (r[4] + 0.5 * r[0].count("."), r[0]))
    return [Hit(t, b[:220], u, s) for t, b, u, s, _ in rows[:limit]]


def npm(fetcher: Fetcher, query: str, limit: int = 5) -> list[Hit]:
    r = fetcher.get(f"https://registry.npmjs.org/-/v1/search?text={quote(query)}&size={limit}")
    if r.status != 200:
        return []
    out = []
    for o in r.json().get("objects", []):
        p = o.get("package", {})
        out.append(Hit(f"{p.get('name')} {p.get('version')}", (p.get("description") or "")[:200],
                       (p.get("links") or {}).get("npm") or f"https://www.npmjs.com/package/{p.get('name')}", "npm"))
    return out


def mdn(fetcher: Fetcher, query: str, locale: str = "pt-BR", limit: int = 5) -> list[Hit]:
    """MDN's own search (its site's JSON API)."""
    r = fetcher.get(f"https://developer.mozilla.org/api/v1/search?q={quote(query)}&locale={locale}&size={limit}")
    if r.status != 200:
        return []
    out = []
    for d in r.json().get("documents", [])[:limit]:
        out.append(Hit(d.get("title", ""), (d.get("summary") or "")[:220],
                       "https://developer.mozilla.org" + d.get("mdn_url", ""), "mdn"))
    return out


def search(query: str, fetcher: Fetcher | None = None) -> list[Hit]:
    """Local reference data first; the npm registry too when the network may be used."""
    hits = local(query)
    if fetcher is not None:
        hits = mdn(fetcher, query) + hits + npm(fetcher, query)
    return hits
