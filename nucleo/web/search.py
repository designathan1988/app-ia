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

import html
import json
import pathlib
import re
import sqlite3
from html.parser import HTMLParser
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


def stackoverflow(fetcher: Fetcher, query: str, limit: int = 5) -> list[Hit]:
    """Stack Overflow questions (the public Stack Exchange API: no key, a daily quota per address)."""
    r = fetcher.get("https://api.stackexchange.com/2.3/search/advanced?order=desc&sort=relevance"
                    f"&q={quote(query)}&site=stackoverflow&pagesize={limit}&filter=default")
    if r.status != 200:
        return []
    out = []
    for it in r.json().get("items", [])[:limit]:
        title = html.unescape(it.get("title", ""))
        state = "respondida" if it.get("is_answered") else "sem resposta aceita"
        out.append(Hit(title, f"{state}; {it.get('score', 0)} votos; tags: {', '.join(it.get('tags', []))}",
                       it.get("link", ""), "stackoverflow"))
    return out


def github(fetcher: Fetcher, query: str, limit: int = 5) -> list[Hit]:
    """GitHub repositories (the public search API, unauthenticated: a few requests per minute)."""
    r = fetcher.get(f"https://api.github.com/search/repositories?q={quote(query)}&per_page={limit}",
                    {"Accept": "application/vnd.github+json"})
    if r.status != 200:
        return []
    return [Hit(it.get("full_name", ""), f"★{it.get('stargazers_count', 0)} {it.get('language') or ''} — "
                f"{(it.get('description') or '')[:160]}", it.get("html_url", ""), "github")
            for it in r.json().get("items", [])[:limit]]


def wikipedia(fetcher: Fetcher, query: str, lang: str = "pt", limit: int = 3) -> list[Hit]:
    r = fetcher.get(f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search&srsearch={quote(query)}"
                    f"&format=json&srlimit={limit}")
    if r.status != 200:
        return []
    out = []
    for it in r.json().get("query", {}).get("search", [])[:limit]:
        snippet = html.unescape(re.sub(r"<[^>]+>", "", it.get("snippet", "")))
        out.append(Hit(it.get("title", ""), snippet[:200],
                       f"https://{lang}.wikipedia.org/wiki/{quote(it.get('title', '').replace(' ', '_'))}",
                       "wikipedia"))
    return out


class _Text(HTMLParser):
    """The readable text of a page: headings, paragraphs, list items and code; not scripts, styles or navigation."""

    KEEP = {"h1", "h2", "h3", "h4", "p", "li", "pre", "td", "th", "blockquote", "dt", "dd"}
    SKIP = {"script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__()
        self.out: list[str] = []
        self.stack: list[str] = []
        self.skip = 0
        self.buf = ""

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag in self.KEEP and self.buf.strip():
            text = re.sub(r"\s+", " ", self.buf).strip() if tag != "pre" else self.buf.strip("\n")
            prefix = "# " if tag in ("h1", "h2") else "## " if tag in ("h3", "h4") else "- " if tag == "li" else ""
            self.out.append(prefix + text)
            self.buf = ""
        while self.stack and self.stack[-1] != tag and tag in self.stack:
            self.stack.pop()
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()

    def handle_data(self, data):
        if not self.skip and any(t in self.KEEP for t in self.stack):
            self.buf += data


def read_page(fetcher: Fetcher, url: str, max_chars: int = 4000) -> str:
    r = fetcher.get(url)
    if r.origin == "bloqueado":
        return "A página respondeu com um desafio anti-robô; não é contornado."
    if r.status != 200:
        return f"Não consegui ler a página (status {r.status})."
    p = _Text()
    p.feed(r.text())
    text = "\n".join(dict.fromkeys(p.out))
    return text[:max_chars] + ("\n..." if len(text) > max_chars else "")


def search(query: str, fetcher: Fetcher | None = None) -> list[Hit]:
    """Local reference data first; the npm registry too when the network may be used."""
    hits = local(query)
    if fetcher is not None:
        hits = (mdn(fetcher, query) + stackoverflow(fetcher, query) + hits + npm(fetcher, query)
                + github(fetcher, query) + wikipedia(fetcher, query))
    return hits
