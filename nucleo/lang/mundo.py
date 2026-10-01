"""Grounding a meaning (``ir.Plan``) against the ActionSchema and the page, and running it in a sandbox copy of the
builder (A1, roteiro CCG).

The grounding is by argument *type*, read from the schema: a ``node`` argument takes the grounded node, a ``nodes``
argument the grounded list, a ``palette-entry`` the entry that inserts the element type, a ``property``/``string``
argument the value (relative values are resolved against the node's current style), and an operation available
only on the selection is preceded by selecting its target. Nothing is per command.

``Sandbox.run`` executes a plan on a copy of a document in the headless builder and returns the resulting
document; ``same_state`` compares two documents ignoring the ids the builder gives to new nodes.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field

from . import esquema as E
from . import ir

FIELDS = {"tag": "div", "attributes": {}, "classes": [], "styles": {}, "text": None, "children": []}


def full_document(pages: list[dict]) -> dict:
    """A builder document from page trees that may omit the node fields the builder requires (the tag of each
    element type is the manifest's)."""
    tags = {e["id"]: e.get("tag") for e in E.manifest()["elements"]["elements"]}

    def fill(n):
        out = {"id": n["id"], "type": n["type"], "name": n.get("name") or n["id"]}
        for k, v in FIELDS.items():
            out[k] = copy.deepcopy(n.get(k, v))
        out["tag"] = n.get("tag") or tags.get(n["type"]) or "div"
        out["children"] = [fill(c) for c in n.get("children", [])]
        return out
    return {"version": 1, "pages": [{"id": p.get("id", f"page-{i}"), "name": p.get("name", "Home"),
                                      "file": p.get("file", "index.html" if i == 0 else f"page-{i}.html"),
                                      "tree": fill(p["tree"])} for i, p in enumerate(pages)]}


def walk(node, parent=None, depth=0):
    yield node, parent, depth
    for c in node.get("children", []):
        yield from walk(c, node, depth + 1)


@dataclass
class Page:
    """A read-only view of a document for grounding: nodes by id, parents, order, current styles."""
    doc: dict
    selection: list = field(default_factory=list)

    def __post_init__(self):
        self.nodes, self.parent, self.order = {}, {}, []
        for p in self.doc.get("pages", []):
            for n, par, _ in walk(p["tree"]):
                self.nodes[n["id"]] = n
                self.parent[n["id"]] = par["id"] if par else None
                self.order.append(n["id"])

    def of_type(self, t: str) -> list:
        return [i for i in self.order if self.nodes[i]["type"] == t]

    def style(self, node: str, prop: str, bp: str = "desktop", state: str = "base"):
        return ((self.nodes.get(node, {}).get("styles") or {}).get(bp) or {}).get(state, {}).get(prop)

    def index_in_parent(self, node: str) -> int:
        par = self.parent.get(node)
        if par is None:
            return 0
        return [c["id"] for c in self.nodes[par]["children"]].index(node)


@dataclass
class Discourse:
    """What the conversation has made salient: the last entity acted on and the last plan."""
    referent: str | None = None
    last: ir.Plan | None = None
    previous: list = field(default_factory=list)  # entities acted on, most recent last


def ground_ref(ref: ir.Ref | None, page: Page, disc: Discourse) -> list:
    if ref is None:
        return []
    if ref.kind == "node":
        return [ref.node] if ref.node in page.nodes else []
    if ref.kind == "selected":
        return list(page.selection[:1])
    if ref.kind == "context":
        return [disc.referent] if disc.referent else list(page.selection[:1])
    if ref.kind == "all":
        return page.of_type(ref.type)
    return []


def _palette_entry(etype: str) -> str | None:
    for entry, t in E.palette().items():
        if t == etype:
            return entry
    return None


def dispatches(plan: ir.Plan, page: Page, disc: Discourse) -> list | None:
    """The builder commands that carry out a plan, or None when it cannot be grounded."""
    schemas = E.schemas()
    out = []
    for a in plan.steps:
        if a.negated:
            continue
        sc = schemas.get(a.op)
        if sc is None:
            return None
        targets = ground_ref(a.target, page, disc)
        if a.target is not None and a.target.kind != "new" and not targets:
            return None
        for tgt in (targets or [None]):
            args, used = {}, False
            for spec in sc.args:
                v = a.arg(spec.name)
                if spec.type == "node":
                    if isinstance(v, ir.Ref):
                        g = ground_ref(v, page, disc)
                        if not g:
                            return None
                        args[spec.name] = g[0]
                    elif spec.name == "target" and tgt is not None:
                        args[spec.name] = tgt
                        used = True
                elif spec.type == "nodes":
                    if tgt is not None:
                        args[spec.name] = [tgt]
                        used = True
                elif spec.type == "palette-entry":
                    t = a.target.type if a.target is not None and a.target.kind == "new" else \
                        (v.data if isinstance(v, ir.Value) else None)
                    entry = _palette_entry(t) if t else None
                    if entry is None:
                        return None
                    args[spec.name] = entry
                elif isinstance(v, ir.Value):
                    if v.op != "SET":
                        prop = a.arg("property")
                        cur = page.style(tgt, prop.data) if tgt and isinstance(prop, ir.Value) else None
                        val = ir.resolve_value(v, cur)
                        if val is None:
                            return None
                        args[spec.name] = val
                    else:
                        args[spec.name] = int(v.data) if spec.type == "integer" else v.data
                elif v is None and not spec.optional and spec.name != "target":
                    return None
            if tgt is not None and (sc.acts_on_selection() or not used) and a.op != "selection.select":
                # (an operation that acts on the selection, or whose arguments did not take the target, is
                # preceded by selecting it)
                out.append(("selection.select", {"target": tgt}))
            out.append((a.op, args))
    return out


class Sandbox:
    """Runs plans on copies of documents in one headless builder."""

    def __init__(self, builder=None):
        from ..builder.client import Builder

        self.b = builder or Builder()

    def run(self, doc: dict, selection: list, steps: list) -> tuple[dict, list, bool]:
        self.b.reset(copy.deepcopy(doc), list(selection))
        ok = True
        for cmd, args in steps:
            r = self.b.dispatch(cmd, **args)
            ok = ok and r.get("status") == "done"
        st = self.b.state()
        return st["document"], st.get("selection", []), ok

    def close(self):
        self.b.close()


def _canon_node(n: dict, known: set) -> dict:
    out = {k: n.get(k) for k in ("type", "name", "tag", "attributes", "classes", "styles", "text", "hidden")}
    if n.get("id") in known:
        out["id"] = n["id"]
    out["children"] = [_canon_node(c, known) for c in n.get("children", [])]
    return out


def same_state(a: dict, b: dict, original: dict) -> bool:
    """Equal documents, ignoring the ids the builder gave to nodes created during the run."""
    known = {n["id"] for p in original.get("pages", []) for n, _, _ in walk(p["tree"])}
    ca = [_canon_node(p["tree"], known) for p in a.get("pages", [])]
    cb = [_canon_node(p["tree"], known) for p in b.get("pages", [])]
    return json.dumps(ca, sort_keys=True) == json.dumps(cb, sort_keys=True)
