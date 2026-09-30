"""robots.txt per RFC 9309, including the `*` and `$` wildcards that Python's urllib.robotparser ignores.

That parser treats ``Disallow: /pypi/*/json`` as a literal prefix, so it would let a crawler fetch what the site
forbids; see docs/achados.md, M4-2.

Rules:

* **Group.** The group whose user-agent token matches ours (case-insensitive substring of the product token) applies;
  otherwise the ``*`` group applies.
* **Matching.** ``*`` matches any sequence; a trailing ``$`` anchors the end.
* **Precedence.** The longest matching rule wins; on a tie, ``Allow`` wins.
* **Errors.** An unreachable robots.txt (5xx, network error) means "disallow everything"; a 4xx means "no rules".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import quote, unquote, urlsplit


@dataclass
class Rules:
    groups: list = field(default_factory=list)  # [(agents: set[str], rules: [(allow: bool, pattern: str)])]
    disallow_all: bool = False

    @classmethod
    def parse(cls, text: str) -> "Rules":
        groups: list = []
        agents: set = set()
        rules: list = []
        last_was_agent = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (x.strip() for x in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if not last_was_agent and (agents or rules):
                    groups.append((agents, rules))
                    agents, rules = set(), []
                agents.add(value.lower())
                last_was_agent = True
            elif key in ("allow", "disallow"):
                last_was_agent = False
                if agents:
                    rules.append((key == "allow", value))
            else:
                last_was_agent = False
        if agents or rules:
            groups.append((agents, rules))
        return cls(groups)

    def _group(self, agent: str) -> list:
        token = agent.split("/", 1)[0].lower()
        specific = [r for a, r in self.groups if any(x != "*" and x in token for x in a)]
        if specific:
            return [x for r in specific for x in r]
        return [x for a, r in self.groups if "*" in a for x in r]

    def allowed(self, agent: str, url: str) -> bool:
        if self.disallow_all:
            return False
        parts = urlsplit(url)
        path = _norm(parts.path or "/") + (("?" + parts.query) if parts.query else "")
        best: tuple[int, bool] | None = None
        for allow, pattern in self._group(agent):
            if pattern == "":
                continue  # an empty Disallow allows everything; it never matches
            if _matches(_norm(pattern), path):
                key = (len(pattern), allow)
                if best is None or key > best:
                    best = key
        return True if best is None else best[1]


def _norm(p: str) -> str:
    return quote(unquote(p), safe="/?=&*$%:@!+,;-._~")


def _matches(pattern: str, path: str) -> bool:
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    regex = "".join(".*" if ch == "*" else re.escape(ch) for ch in body)
    return re.match(regex + ("$" if anchored else ""), path) is not None
