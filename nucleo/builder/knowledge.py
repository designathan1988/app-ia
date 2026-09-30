"""What builder-6's manifest declares, as data the planner reasons with.

Everything here is read from the manifest files; nothing is written by hand.
The manifest gives the commands (argument names and types, availability
predicate), the properties (with their declared value subsets), breakpoints,
style states, palette entries (with the element type each inserts), elements
and attributes.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

from .client import DEFAULT_BUILDER
from .scenarios import load_commands


@dataclass
class Domains:
    commands: dict[str, dict]
    properties: dict[str, list]  # property -> declared example values (from its subsets)
    breakpoints: list[str]
    states: list[str]
    palette: dict[str, str | None]  # palette entry -> element type it inserts
    element_types: list[str]
    attributes: list[str]
    unsupported_types: set = field(default_factory=lambda: {"point", "rect", "file", "files", "clipboard"})

    def args(self, command: str) -> dict[str, dict]:
        return self.commands[command]["args"]

    def availability(self, command: str) -> str:
        return (self.commands[command].get("availability") or {}).get("predicate") or "always"

    def plannable(self, command: str) -> bool:
        """A command whose every required argument has a type the headless editor can be given."""
        return all(
            spec.get("optional") or spec["type"] not in self.unsupported_types for spec in self.args(command).values()
        )


def _ids(items) -> list[str]:
    return [x["id"] if isinstance(x, dict) else x for x in items]


def load_domains(root: str | None = None) -> Domains:
    base = pathlib.Path(root or DEFAULT_BUILDER) / "manifest"
    props = json.loads((base / "properties.json").read_text(encoding="utf-8"))
    elements = json.loads((base / "elements.json").read_text(encoding="utf-8"))
    properties = {}
    for p in props["properties"]:
        values: list = []
        for sub in p.get("subsets") or []:
            values += [v for v in sub.get("values") or [] if isinstance(v, (str, int, float))]
        properties[p["id"]] = values
    palette = {}
    for group in elements["palette"]:
        for entry in group["entries"]:
            palette[entry["id"]] = entry.get("element")
    attrs = elements.get("attributes") or []
    attributes = _ids(attrs) if isinstance(attrs, list) else list(attrs)
    return Domains(
        commands=load_commands(root),
        properties=properties,
        breakpoints=_ids(props.get("breakpoints") or []),
        states=_ids(props.get("states") or []),
        palette=palette,
        element_types=[e["id"] for e in elements["elements"]],
        attributes=[a for a in attributes if isinstance(a, str)],
    )
