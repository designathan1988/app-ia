"""M4 (web): robots.txt per RFC 9309, the polite fetcher, registry parsing, and claims -> verification -> approval.

The robots.txt expectations are the examples table of Google's published robots.txt specification (an external
source), not answers written for this code. The HTTP transport is simulated; experiments/m4_packages.py talks to the
real registries.
"""

from __future__ import annotations

import io
import urllib.error

import pytest

from nucleo.store.db import Store
from nucleo.web.claims import KNOWN, Claims
from nucleo.web.fetcher import Fetcher
from nucleo.web.registries import lookup, npm, pypi
from nucleo.web.robots import Rules

# (pattern, path, matches) from the "URL matching based on path values" table of Google's specification
GOOGLE_TABLE = [
    ("/fish", "/fish", True), ("/fish", "/fish.html", True), ("/fish", "/fish/salmon.html", True),
    ("/fish", "/fishheads", True), ("/fish", "/fishheads/yummy.html", True), ("/fish", "/fish.php?id=anything", True),
    ("/fish", "/Fish.asp", False), ("/fish", "/catfish", False), ("/fish", "/?id=fish", False),
    ("/fish", "/desert/fish", False),
    ("/fish*", "/fish", True), ("/fish*", "/fishheads/yummy.html", True), ("/fish*", "/catfish", False),
    ("/fish/", "/fish/", True), ("/fish/", "/fish/?id=anything", True), ("/fish/", "/fish/salmon.htm", True),
    ("/fish/", "/fish", False), ("/fish/", "/fish.html", False), ("/fish/", "/animals/fish/", False),
    ("/*.php", "/index.php", True), ("/*.php", "/filename.php", True), ("/*.php", "/folder/filename.php", True),
    ("/*.php", "/folder/filename.php?parameters", True), ("/*.php", "/folder/any.php.file.html", True),
    ("/*.php", "/filename.php/", True), ("/*.php", "/", False), ("/*.php", "/windows.PHP", False),
    ("/*.php$", "/filename.php", True), ("/*.php$", "/folder/filename.php", True),
    ("/*.php$", "/filename.php?parameters", False), ("/*.php$", "/filename.php/", False),
    ("/*.php$", "/filename.php5", False), ("/*.php$", "/windows.PHP", False),
    ("/fish*.php", "/fish.php", True), ("/fish*.php", "/fishheads/catfish.php?parameters", True),
    ("/fish*.php", "/Fish.PHP", False),
]


@pytest.mark.parametrize("pattern, path, matches", GOOGLE_TABLE)
def test_robots_matching_follows_the_published_table(pattern, path, matches):
    rules = Rules.parse(f"User-agent: *\nDisallow: {pattern}\n")
    assert rules.allowed("nucleo", "https://x.test" + path) is (not matches)


def test_robots_precedence_and_groups():
    rules = Rules.parse("""
User-agent: *
Allow: /p
Disallow: /
User-agent: nucleo
Disallow: /page
Allow: /page.html
""")
    assert rules.allowed("outro", "https://x.test/page")  # longest match: Allow /p over Disallow /
    assert not rules.allowed("outro", "https://x.test/other")
    assert not rules.allowed("nucleo/0.1", "https://x.test/pages")  # our own group applies, not *
    assert rules.allowed("nucleo/0.1", "https://x.test/page.html")  # longer Allow wins


def test_pypi_json_api_is_forbidden_although_stdlib_parser_allows_it():
    import urllib.robotparser

    text = "User-agent: *\nDisallow: /pypi/*/json\nDisallow: /simple/\n"
    std = urllib.robotparser.RobotFileParser()
    std.parse(text.splitlines())
    assert std.can_fetch("nucleo", "https://pypi.org/pypi/clingo/json")  # the stdlib ignores the wildcard
    assert not Rules.parse(text).allowed("nucleo", "https://pypi.org/pypi/clingo/json")
    assert Rules.parse(text).allowed("nucleo", "https://pypi.org/rss/project/clingo/releases.xml")


class FakeWeb:
    """A scripted web: url -> (status, body, headers). Records every request."""

    def __init__(self, pages: dict):
        self.pages = pages
        self.requests: list = []

    def __call__(self, req, timeout):
        self.requests.append((req.full_url, dict(req.header_items())))
        status, body, headers = self.pages.get(req.full_url, (404, b"", {}))
        if callable(status):
            status, body, headers = status(req)
        if status >= 400 or status == 304:
            raise urllib.error.HTTPError(req.full_url, status, "x", headers, io.BytesIO(body))
        resp = io.BytesIO(body)
        resp.status = status
        resp.headers = headers
        return resp


class Clock:
    def __init__(self):
        self.t = 0.0
        self.slept = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def test_fetcher_obeys_robots_caches_and_waits(tmp_path):
    def conditional(req):
        if req.get_header("If-none-match") == '"v1"':
            return 304, b"", {}
        return 200, b'{"ok": 1}', {"ETag": '"v1"'}

    web = FakeWeb({
        "https://a.test/robots.txt": (200, b"User-agent: *\nDisallow: /secreto\n", {}),
        "https://a.test/dado": (conditional, None, None),
        "https://b.test/robots.txt": (503, b"", {}),
    })
    clock = Clock()
    f = Fetcher(tmp_path, min_delay=1.0, opener=web, clock=clock, sleep=clock.sleep, respect_robots=True)
    assert f.get("https://a.test/secreto/x").origin == "robots"
    r1 = f.get("https://a.test/dado")
    r2 = f.get("https://a.test/dado")
    assert (r1.origin, r2.origin, r2.json()) == ("rede", "cache", {"ok": 1})
    assert f.get("https://b.test/qualquer").origin == "robots"  # robots.txt unreachable: disallow everything
    assert all(s <= 1.0 for s in clock.slept) and len(clock.slept) >= 2  # waited between requests to a.test
    assert sum(1 for u, _ in web.requests if u.endswith("robots.txt")) == 2  # robots.txt fetched once per host


def test_fetcher_reports_a_challenge_and_never_parses_it(tmp_path):
    web = FakeWeb({
        "https://c.test/robots.txt": (404, b"", {}),
        "https://c.test/p": (200, b"<html><title>Client Challenge</title></html>", {}),
    })
    clock = Clock()
    r = Fetcher(tmp_path, opener=web, clock=clock, sleep=clock.sleep, respect_robots=True).get("https://c.test/p")
    assert r.origin == "bloqueado" and r.body == b""


def test_registries_parse_structured_answers(tmp_path):
    rss = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>
      <item><title>2.0.0</title></item><item><title>1.9.1</title></item></channel></rss>"""
    web = FakeWeb({
        "https://registry.npmjs.org/robots.txt": (200, b'{"_id":"robots.txt"}', {}),  # a package, not rules
        "https://registry.npmjs.org/left-pad": (200, b'{"dist-tags":{"latest":"1.3.0"},"versions":{"1.3.0":{}}}', {}),
        "https://pypi.org/robots.txt": (200, b"User-agent: *\nDisallow: /pypi/*/json\n", {}),
        "https://pypi.org/rss/project/algo/releases.xml": (200, rss, {}),
        "https://pypi.org/pypi/algo/json": (503, b"", {}),  # JSON unusable: the RSS feed answers
        "https://pypi.org/pypi/outro/json": (200, b'{"info": {"version": "3.1"}, "releases": {"3.0": [], "3.1": []}}', {}),
    })
    clock = Clock()
    f = Fetcher(tmp_path, opener=web, clock=clock, sleep=clock.sleep)  # the default: robots.txt not obeyed
    a = npm(f, "left-pad")
    b = npm(f, "nao-existe-zz")
    c = pypi(f, "algo")
    assert (a.exists, a.latest, b.exists, c.exists, c.latest, c.versions) == (True, "1.3.0", False, True, "2.0.0",
                                                                              ["2.0.0", "1.9.1"])
    assert npm(f, "Nome Inválido").exists is False
    d = pypi(f, "outro")
    assert (d.exists, d.latest, d.versions) == (True, "3.1", ["3.0", "3.1"])
    assert pypi(f, "nao-existe-zz").exists is False  # JSON 404
    assert lookup(None, "pypi", "pytest").source.startswith("local:")  # installed: answered locally


def test_claims_need_verification_and_approval(tmp_path):
    claims = Claims(Store(str(tmp_path / "kb.db")))
    fact = 'pacote_existe("npm", "left-pad").'
    claims.record(fact, "https://registry.npmjs.org/left-pad", structured=True)
    assert not claims.verified() and not claims.can_suggest("npm", "left-pad")  # seen once: not verified
    claims.record(fact, "https://registry.npmjs.org/left-pad", structured=True)  # reproduced
    assert fact in claims.verified() and claims.pending() == [fact]
    assert not claims.can_suggest("npm", "left-pad")  # verified but not approved: still not knowledge
    claims.approve([fact], by="jonathan")
    assert claims.can_suggest("npm", "left-pad") and claims.pending() == []
    text_claim = 'suporta("chrome", "css-has").'
    claims.record(text_claim, "https://blog.um.test/post", structured=False)
    claims.record(text_claim, "https://outro.blog.um.test/x", structured=False)  # same site: not independent
    assert text_claim not in claims.verified()
    claims.record(text_claim, "https://docs.dois.test/p", structured=False)
    assert text_claim in claims.verified()
    with pytest.raises(ValueError):
        claims.approve(['pacote_existe("npm", "inventado").'], by="jonathan")
    assert KNOWN in claims.store.contexts()


def test_local_reference_search_finds_the_web_platform_entry():
    from nucleo.web.search import local

    hits = local("grid template areas")
    assert hits and any(h.title.endswith("grid-template-areas") for h in hits[:3])
    assert any(h.source == "webref" and "none | <string>+" in h.summary for h in hits)
