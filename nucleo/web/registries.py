"""Package facts from structured, key-free sources: first what is installed locally, then the public registries.

* **npm:** ``registry.npmjs.org/<name>`` (package metadata JSON; the registry has no robots.txt restrictions).
* **PyPI:** the JSON API ``pypi.org/pypi/<name>/json`` (the fetcher does not obey robots.txt by the user's
  decision), with the releases RSS feed as fallback. Project HTML pages answer bots with a JavaScript challenge,
  which is never bypassed; the JSON API does not need them.

Every answer carries where it came from, so a claim built on it can be traced and re-checked.
"""

from __future__ import annotations

import json
import pathlib
import re
import sysconfig
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from urllib.parse import quote

from .fetcher import Fetcher

_NPM_NAME = re.compile(r"^(@[a-z0-9-~][a-z0-9-._~]*/)?[a-z0-9-~][a-z0-9-._~]*$")
_PYPI_NAME = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$")


@dataclass
class PackageInfo:
    ecosystem: str
    name: str
    exists: bool | None  # None: could not be determined (robots, challenge, network)
    latest: str | None = None
    versions: list = field(default_factory=list)
    source: str = ""  # "local:<path>" | URL
    why: str = ""


def local_npm(name: str, roots: list[str]) -> PackageInfo | None:
    for root in roots:
        p = pathlib.Path(root) / "node_modules" / name / "package.json"
        if p.exists():
            j = json.loads(p.read_text(encoding="utf-8"))
            return PackageInfo("npm", name, True, j.get("version"), [j.get("version")], f"local:{p}")
    return None


def local_pypi(name: str) -> PackageInfo | None:
    site = pathlib.Path(sysconfig.get_paths()["purelib"])
    norm = re.sub(r"[-_.]+", "_", name).lower()
    for d in site.glob("*.dist-info"):
        dist, _, ver = d.name[: -len(".dist-info")].rpartition("-")
        if re.sub(r"[-_.]+", "_", dist).lower() == norm:
            return PackageInfo("pypi", name, True, ver, [ver], f"local:{d}")
    return None


def npm(fetcher: Fetcher, name: str) -> PackageInfo:
    if not _NPM_NAME.match(name):
        return PackageInfo("npm", name, False, why="nome inválido para o npm")
    url = "https://registry.npmjs.org/" + quote(name, safe="@")
    r = fetcher.get(url, {"Accept": "application/vnd.npm.install-v1+json"})
    if r.status == 404:
        return PackageInfo("npm", name, False, source=url, why="registro respondeu 404")
    if r.status != 200:
        return PackageInfo("npm", name, None, source=url, why=f"sem resposta utilizável ({r.origin}, {r.status})")
    j = r.json()
    versions = list((j.get("versions") or {}).keys())
    return PackageInfo("npm", name, True, (j.get("dist-tags") or {}).get("latest"), versions, url)


def pypi(fetcher: Fetcher, name: str) -> PackageInfo:
    """PyPI's JSON API (versions, summary); its releases RSS feed when the JSON answer is not usable."""
    if not _PYPI_NAME.match(name):
        return PackageInfo("pypi", name, False, why="nome inválido para o PyPI")
    api = f"https://pypi.org/pypi/{quote(name)}/json"
    r = fetcher.get(api)
    if r.status == 404:
        return PackageInfo("pypi", name, False, source=api, why="registro respondeu 404")
    if r.status == 200:
        try:
            j = r.json()
            return PackageInfo("pypi", name, True, (j.get("info") or {}).get("version"),
                               list((j.get("releases") or {}).keys()), api)
        except ValueError:
            pass
    url = f"https://pypi.org/rss/project/{quote(name)}/releases.xml"
    r = fetcher.get(url)
    if r.status == 404:
        return PackageInfo("pypi", name, False, source=url, why="registro respondeu 404")
    if r.status != 200:
        return PackageInfo("pypi", name, None, source=url, why=f"sem resposta utilizável ({r.origin}, {r.status})")
    try:
        root = ET.fromstring(r.body)
    except ET.ParseError:
        return PackageInfo("pypi", name, None, source=url, why="resposta não é o feed esperado")
    versions = [it.findtext("title") for it in root.iter("item")]
    return PackageInfo("pypi", name, True, versions[0] if versions else None, versions, url)


def lookup(fetcher: Fetcher | None, ecosystem: str, name: str, npm_roots: list[str] = ()) -> PackageInfo:
    local = local_npm(name, list(npm_roots)) if ecosystem == "npm" else local_pypi(name)
    if local is not None:
        return local
    if fetcher is None:
        return PackageInfo(ecosystem, name, None, why="não instalado e sem acesso à rede")
    return npm(fetcher, name) if ecosystem == "npm" else pypi(fetcher, name)
