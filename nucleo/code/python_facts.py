"""Python code facts in the same two layers as the TypeScript extractor.

1. **Syntax**, from ``ast`` only: scopes, bindings and name uses. Python's own rules are expressed here, in the
   facts, so the shared resolution rules (``resolve.py``) need no change:
   - A class body is not an enclosing scope for the functions and comprehensions inside it. Their lookup parent
     skips the class.
   - ``global x`` makes the lookup of x start at the module, and ``nonlocal x`` at the enclosing function. Neither
     binds x locally.
   - A name bound anywhere in a function is local to the whole function. Resolution is not positional, so this
     needs nothing special.
   - Decorators, default values, base classes and the first iterable of a comprehension are evaluated in the
     enclosing scope.
2. **Oracle**, from CPython's own compiler symbol tables (``symtable``): the table that binds each use. Python
   3.12 inlines list, set and dict comprehensions into the enclosing table (PEP 709), so the oracle maps those
   scopes to the enclosing table.

Output: the same dict as ``bridge/code/ts_facts.mjs`` (scopes, decls, uses, oracle). Positions are
``line * 10000 + column``.
"""

from __future__ import annotations

import ast
import symtable

INLINED = (ast.ListComp, ast.SetComp, ast.DictComp)
COMPS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _pos(node) -> int:
    return node.lineno * 10000 + node.col_offset


class _Extractor:
    def __init__(self) -> None:
        self.scopes: list = []  # [id, lookup parent, kind]
        self.decls: list = []
        self.uses: list = []
        self.kind: dict[int, str] = {}
        self.parent: dict[int, int] = {}  # syntactic parent (for the oracle mapping)
        self.node_of: dict[int, ast.AST] = {}
        self.globals: dict[int, set] = {}
        self.nonlocals: dict[int, set] = {}
        self.written: dict[int, int] = {}  # use position -> the scope it is written in

    def new_scope(self, parent: int, kind: str, node) -> int:
        sid = len(self.scopes)
        lookup = parent
        while lookup >= 0 and self.kind[lookup] == "classe" and kind != "classe-corpo":
            lookup = self.parent[lookup]
        self.scopes.append([sid, lookup, kind])
        self.kind[sid] = "classe" if kind == "classe" else kind
        self.parent[sid] = parent
        self.node_of[sid] = node
        self.globals[sid] = set()
        self.nonlocals[sid] = set()
        return sid

    def mangle(self, scope: int, name: str) -> str:
        """Inside a class, `__x` (not `__x__`) is the private name `_Class__x` (the language's own rewriting)."""
        if not name.startswith("__") or name.endswith("__"):
            return name
        s = scope
        while s >= 0:
            node = self.node_of[s]
            if isinstance(node, ast.ClassDef) and self.kind[s] == "classe":
                stripped = node.name.lstrip("_")
                return f"_{stripped}{name}" if stripped else name
            s = self.parent[s]
        return name

    def bind(self, scope: int, name: str, pos: int, kind: str) -> None:
        name = self.mangle(scope, name)
        if name in self.globals[scope]:
            scope = 0
        elif name in self.nonlocals[scope]:
            return  # binds the enclosing function's variable, which is declared there
        self.decls.append([scope, name, pos, "valor", kind])

    def use(self, scope: int, name: str, pos: int) -> None:
        name = self.mangle(scope, name)
        self.written[pos] = scope
        start = scope
        if name in self.globals[scope]:
            start = 0
        elif name in self.nonlocals[scope]:
            start = self.scopes[scope][1]
        self.uses.append([pos, name, start, "valor"])

    # -- traversal ---------------------------------------------------------------------------------------------
    def module(self, tree: ast.Module) -> None:
        s = self.new_scope(-1, "modulo", tree)
        for st in tree.body:
            self.visit(st, s)

    def _own_statements(self, body):
        """global/nonlocal statements of this scope only (not of nested functions or classes)."""
        stack = list(body)
        while stack:
            n = stack.pop()
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda) + COMPS):
                continue
            yield n
            stack.extend(ast.iter_child_nodes(n))

    def _type_params(self, node, scope) -> int:
        """PEP 695: `class C[T]`, `def f[T]`, `type A[T]` open a scope binding the type parameters."""
        params = getattr(node, "type_params", None) or []
        if not params:
            return scope
        tp = self.new_scope(scope, "tipo-params", ("tp", node))
        for p in params:
            self.bind(tp, p.name, _pos(p), "parametro-tipo")
        for p in params:
            for part in ("bound", "default_value"):
                v = getattr(p, part, None)
                if v is not None:
                    self.visit(v, tp)
        return tp

    def _function(self, node, scope) -> None:
        args = node.args
        for d in list(args.defaults) + [d for d in args.kw_defaults if d is not None]:
            self.visit(d, scope)
        if not isinstance(node, ast.Lambda):
            for d in node.decorator_list:
                self.visit(d, scope)
            self.bind(scope, node.name, _pos(node), "funcao")
            inner = self._type_params(node, scope)
            for a in [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]:
                if a is not None and a.annotation is not None:
                    self.visit(a.annotation, inner)
            if node.returns is not None:
                self.visit(node.returns, inner)
            scope = inner
        fs = self.new_scope(scope, "funcao", node)
        body = node.body if isinstance(node.body, list) else [node.body]
        for n in self._own_statements(body):
            if isinstance(n, ast.Global):
                self.globals[fs].update(self.mangle(fs, x) for x in n.names)
            elif isinstance(n, ast.Nonlocal):
                self.nonlocals[fs].update(self.mangle(fs, x) for x in n.names)
        for a in [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]:
            if a is not None:
                self.bind(fs, a.arg, _pos(a), "parametro")
        for st in body:
            self.visit(st, fs)

    def _class(self, node: ast.ClassDef, scope) -> None:
        for d in node.decorator_list:
            self.visit(d, scope)
        self.bind(scope, node.name, _pos(node), "classe")
        inner = self._type_params(node, scope)
        for d in node.bases + [k.value for k in node.keywords]:
            self.visit(d, inner)
        cs = self.new_scope(inner, "classe", node)
        for n in self._own_statements(node.body):
            if isinstance(n, ast.Global):
                self.globals[cs].update(self.mangle(cs, x) for x in n.names)
            elif isinstance(n, ast.Nonlocal):
                self.nonlocals[cs].update(self.mangle(cs, x) for x in n.names)
        for st in node.body:
            self.visit(st, cs)

    def _comprehension(self, node, scope) -> None:
        gens = node.generators
        self.visit(gens[0].iter, scope)  # the first iterable is evaluated outside
        cs = self.new_scope(scope, "compreensao", node)
        for i, g in enumerate(gens):
            if i > 0:
                self.visit(g.iter, cs)
            self._target(g.target, cs)
            for cond in g.ifs:
                self.visit(cond, cs)
        for part in (["key", "value"] if isinstance(node, ast.DictComp) else ["elt"]):
            self.visit(getattr(node, part), cs)

    def _target(self, t, scope) -> None:
        for n in ast.walk(t):
            if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                self.bind(scope, n.id, _pos(n), "atribuicao")
            elif isinstance(n, ast.Name):
                self.use(scope, n.id, _pos(n))
            elif isinstance(n, ast.Starred):
                continue
        # attribute/subscript targets contain loads (a.b = ..., a[i] = ...), handled by walk above

    def visit(self, node, scope) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            if isinstance(node, ast.Lambda):
                self._function(node, scope)
            else:
                self._function(node, scope)
            return
        if isinstance(node, ast.ClassDef):
            self._class(node, scope)
            return
        if isinstance(node, COMPS):
            self._comprehension(node, scope)
            return
        if isinstance(node, ast.NamedExpr):
            # the walrus binds in the nearest scope that is not a comprehension
            target = scope
            while self.kind[target] == "compreensao":
                target = self.parent[target]
            self.visit(node.value, scope)
            self.bind(target, node.target.id, _pos(node.target), "walrus")
            return
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load):
                self.use(scope, node.id, _pos(node))
            else:
                self.bind(scope, node.id, _pos(node), "atribuicao")
            return
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                if a.name == "*":
                    continue
                name = a.asname or a.name.split(".")[0]
                self.bind(scope, name, _pos(a) if hasattr(a, "lineno") else _pos(node), "import")
            return
        if isinstance(node, ast.ExceptHandler):
            if node.type is not None:
                self.visit(node.type, scope)
            if node.name:
                self.bind(scope, node.name, _pos(node), "except")
            for st in node.body:
                self.visit(st, scope)
            return
        if isinstance(node, (ast.MatchAs, ast.MatchStar)):
            if node.name:
                self.bind(scope, node.name, _pos(node), "match")
            for c in ast.iter_child_nodes(node):
                self.visit(c, scope)
            return
        if isinstance(node, ast.MatchMapping) and node.rest:
            self.bind(scope, node.rest, _pos(node), "match")
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            return
        if hasattr(ast, "TypeAlias") and isinstance(node, ast.TypeAlias):
            self.bind(scope, node.name.id, _pos(node.name), "tipo")
            inner = self._type_params(node, scope)
            alias = self.new_scope(inner, "tipo-alias", ("alias", node))
            self.visit(node.value, alias)
            return
        for c in ast.iter_child_nodes(node):
            self.visit(c, scope)


def _ttype(t) -> str:
    kind = t.get_type()
    return str(getattr(kind, "value", kind)).lower()


def _tables(top) -> tuple[list, dict]:
    """Every symbol table once, with its parent. get_children() builds new objects on each call, so the same
    objects must be used for indexing and for walking up."""
    order, parents = [], {}
    stack = [top]
    while stack:
        t = stack.pop()
        order.append(t)
        kids = t.get_children()
        for c in kids:
            parents[id(c)] = t
        stack.extend(reversed(kids))
    return order, parents


def _table_map(ex: _Extractor, top, order: list) -> dict[int, symtable.SymbolTable]:
    """Our scope id -> the symbol table the compiler uses for it (inlined comprehensions -> the enclosing table)."""
    pending: dict[tuple, list] = {}
    for c in order[1:]:
        pending.setdefault((_ttype(c), c.get_name(), c.get_lineno()), []).append(c)
    out = {0: top}
    for sid, _lookup, kind in ex.scopes[1:]:
        node = ex.node_of[sid]
        if isinstance(node, INLINED):
            out[sid] = out[ex.parent[sid]]
            continue
        if isinstance(node, tuple):  # ("tp", owner) / ("alias", TypeAlias)
            tag, owner = node
            name = owner.name.id if isinstance(owner, ast.TypeAlias) else owner.name
            key = ("type parameter" if tag == "tp" else "type alias", name, owner.lineno)
        elif isinstance(node, ast.ClassDef):
            key = ("class", node.name, node.lineno)
        elif isinstance(node, ast.Lambda):
            key = ("function", "lambda", node.lineno)
        elif isinstance(node, ast.GeneratorExp):
            key = ("function", "genexpr", node.lineno)
        else:
            key = ("function", node.name, node.lineno)
        cands = pending.get(key) or []
        out[sid] = cands.pop(0) if cands else None
    return out


def _binding_table(table, name, parent_tables, all_tables=()):
    """The table that binds `name` for a use in `table`, per the compiler; None for a builtin or unbound global."""
    try:
        sym = table.lookup(name)
    except KeyError:
        sym = None
    if sym is not None and sym.is_local() and not sym.is_declared_global():
        return table
    if sym is not None and sym.is_free():
        t = parent_tables.get(id(table))
        while t is not None:
            if _ttype(t) in ("function", "type parameter", "type alias"):  # annotation scopes act as functions
                try:
                    s2 = t.lookup(name)
                    if s2.is_local():
                        return t
                except KeyError:
                    pass
            t = parent_tables.get(id(t))
        return None
    top = table
    while parent_tables.get(id(top)) is not None:
        top = parent_tables[id(top)]
    try:
        if top.lookup(name).is_local():
            return top
    except KeyError:
        pass
    # a module global may be bound only by functions that declare it `global` and assign it
    for t in all_tables:
        try:
            sym = t.lookup(name)
        except KeyError:
            continue
        if sym.is_declared_global() and sym.is_assigned():
            return top
    return None


def facts_of(source: str, filename: str = "<src>") -> dict:
    tree = ast.parse(source, filename)
    ex = _Extractor()
    ex.module(tree)
    top = symtable.symtable(source, filename, "exec")
    order, parents = _tables(top)
    tmap = _table_map(ex, top, order)
    decls_by: dict = {}
    for scope, name, pos, _sp, _k in ex.decls:
        t = tmap.get(scope)
        if t is not None:
            decls_by.setdefault((id(t), name), []).append(pos)
    oracle = {}
    for pos, name, scope, _sp in ex.uses:
        # the compiler's view of the use: the table of the scope where the use is written
        written = ex.written.get(pos, scope)
        t = tmap.get(written)
        if t is None or _inlined_in_class(ex, written):
            # PEP 709 inlines the comprehension into the class's table, yet its names still skip the class scope:
            # the symbol table cannot express that use, so it has no oracle (counted apart, never judged)
            continue
        b = _binding_table(t, name, parents, order)
        oracle[str(pos)] = "externo" if b is None else decls_by.get((id(b), name), ["sem-declaracao"])
    return {"file": filename, "scopes": ex.scopes, "decls": ex.decls, "uses": ex.uses, "oracle": oracle}



def _inlined_in_class(ex: _Extractor, scope: int) -> bool:
    """Whether `scope` is an inlined comprehension (possibly nested) directly inside a class body."""
    s = scope
    if not isinstance(ex.node_of.get(s), INLINED):
        return False
    while s >= 0 and isinstance(ex.node_of.get(s), INLINED):
        s = ex.parent[s]
    return s >= 0 and ex.kind[s] == "classe"
