"""A polite, key-free HTTP client: robots.txt first, identified, rate-limited per host, cached with ETags.

The fetcher follows these rules:

* With ``respect_robots=True`` it checks robots.txt (RFC 9309, see ``robots.py``) before every request, cached for
  24 h. By the user's decision the default is not to obey it.
* It never bypasses a bot challenge. A response that is an interstitial challenge page is reported as "bloqueado",
  not parsed.
* It waits at least ``min_delay`` seconds between requests to the same host.
* It sends conditional requests (If-None-Match / If-Modified-Since). A 304 is answered from the local cache.
* It caps the size of every response.

It uses only the standard library.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

from .robots import Rules

USER_AGENT = "nucleo/0.1 (motor local de programacao; consultas sob demanda, sem rastreamento)"
CHALLENGE_MARKERS = ("<title>Client Challenge</title>", "cf-challenge", "Just a moment...", "captcha")


@dataclass
class Response:
    url: str
    status: int  # HTTP status; 0 = not fetched (robots or network)
    body: bytes
    headers: dict
    origin: str  # "rede" | "cache" | "robots" | "bloqueado" | "erro"

    def json(self):
        return json.loads(self.body)

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class Fetcher:
    def __init__(self, cache_dir: str | pathlib.Path, min_delay: float = 1.0, max_bytes: int = 5_000_000,
                 opener=None, clock=time.monotonic, sleep=time.sleep, respect_robots: bool = False) -> None:
        # the user's decision (2026-09-30): robots.txt is not obeyed by default; pass respect_robots=True to obey it.
        # Rate limiting, identification and never bypassing a bot challenge stay in force either way.
        self.respect_robots = respect_robots
        self.cache = pathlib.Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.min_delay = min_delay
        self.max_bytes = max_bytes
        self.open = opener or (lambda req, timeout: urllib.request.urlopen(req, timeout=timeout))
        self.clock = clock
        self.sleep = sleep
        self._last: dict[str, float] = {}
        self._robots: dict[str, tuple[float, Rules]] = {}
        self.log: list[tuple[str, str, int]] = []  # (url, origin, status): every decision is recorded

    # -- robots ------------------------------------------------------------------------------------------------
    def _rules(self, origin: str) -> Rules:
        cached = self._robots.get(origin)
        if cached and self.clock() - cached[0] < 24 * 3600:
            return cached[1]
        status, body, _ = self._raw(origin + "/robots.txt", {})
        if status == 0 or status >= 500:
            rules = Rules(disallow_all=True)
        elif 400 <= status < 500:
            rules = Rules()
        else:
            rules = Rules.parse(body.decode("utf-8", errors="replace"))
        self._robots[origin] = (self.clock(), rules)
        return rules

    # -- transport ---------------------------------------------------------------------------------------------
    def _raw(self, url: str, headers: dict) -> tuple[int, bytes, dict]:
        host = urlsplit(url).netloc
        wait = self.min_delay - (self.clock() - self._last.get(host, -1e9))
        if wait > 0:
            self.sleep(wait)
        self._last[host] = self.clock()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
        try:
            with self.open(req, 20) as r:
                return r.status, r.read(self.max_bytes + 1)[: self.max_bytes], dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(self.max_bytes) if e.fp else b"", dict(e.headers or {})
        except (urllib.error.URLError, TimeoutError, OSError):
            return 0, b"", {}

    def _cache_path(self, url: str) -> pathlib.Path:
        return self.cache / hashlib.sha256(url.encode()).hexdigest()

    def get(self, url: str, headers: dict | None = None) -> Response:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if self.respect_robots and not self._rules(origin).allowed(USER_AGENT, url):
            self.log.append((url, "robots", 0))
            return Response(url, 0, b"", {}, "robots")
        cp = self._cache_path(url)
        meta = json.loads((cp.with_suffix(".json")).read_text()) if cp.with_suffix(".json").exists() else None
        h = dict(headers or {})
        if meta:
            if meta.get("etag"):
                h["If-None-Match"] = meta["etag"]
            if meta.get("last_modified"):
                h["If-Modified-Since"] = meta["last_modified"]
        status, body, rh = self._raw(url, h)
        if status == 304 and meta:
            self.log.append((url, "cache", 304))
            return Response(url, meta["status"], cp.read_bytes(), meta["headers"], "cache")
        if status == 0:
            self.log.append((url, "erro", 0))
            return Response(url, 0, b"", {}, "erro")
        if any(m.encode() in body[:4000] for m in CHALLENGE_MARKERS):
            self.log.append((url, "bloqueado", status))
            return Response(url, status, b"", rh, "bloqueado")
        if status == 200:
            cp.write_bytes(body)
            cp.with_suffix(".json").write_text(json.dumps({
                "status": status, "headers": rh, "etag": rh.get("ETag") or rh.get("Etag"),
                "last_modified": rh.get("Last-Modified"), "url": url}))
        self.log.append((url, "rede", status))
        return Response(url, status, body, rh, "rede")
