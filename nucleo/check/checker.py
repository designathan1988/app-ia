"""Independent proof checker.

**Trusted base.** This module plus ``nucleo.kb.syntax`` (data structures and
parser). It does **not** import ``nucleo.logic``. Matching, comparison,
aggregate evaluation, strict closure and defeasible resolution are
re-implemented here in a simple, different way (naive nested loops over the
certified set), so that a bug in the engine is not repeated in the checker.

**Checks.**

1. ``check_model``: the certified set S, together with the certified
   INDETERMINADO atoms, is exactly the model of the program.
   * **Support.** Every atom of S is an asserted fact, or has a strict rule
     instance whose positive premises are in S with smaller rank, whose absent
     atoms are not in S, whose comparisons hold and whose aggregates recount to
     the same value. A defeasible conclusion must, in addition, win its conflict
     as recomputed here.
   * **Closure.** Every strict rule instance that holds in S has its head in S.
     Every ground atom with defeasible rules has the outcome recomputed here:
     it is in S, its negation is in S, or it is INDETERMINADO.

   For stratified programs the result is the unique perfect model: Fages'
   well-supported models, with the defeasible decisions checked explicitly.
2. ``check_proof``: every step of a proof tree is a correct rule instance.
3. ``check_status``: recomputes the status and compares it with the claim.
"""

from __future__ import annotations

from ..kb.syntax import Agg, Atom, Cmp, Naf, NaoConsta, Pos, PredKey, Program, Sym, Text, Var


class CheckError(AssertionError):
    pass


# -- own primitives -------------------------------------------------------------


def _order(c) -> tuple:
    if isinstance(c, bool):
        raise CheckError("booleano não é termo")
    if isinstance(c, int):
        return (0, c, "")
    if isinstance(c, Sym):
        return (1, 0, c.name)
    if isinstance(c, Text):
        return (2, 0, c.value)
    raise CheckError(f"termo desconhecido {c!r}")


def _cmp_holds(op: str, a, b) -> bool:
    if op == "=":
        return a == b
    if op == "!=":
        return not (a == b)
    oa, ob = _order(a), _order(b)
    return {"<": oa < ob, "<=": oa <= ob, ">": oa > ob, ">=": oa >= ob}[op]


def _term(t, s: dict):
    if isinstance(t, Var):
        if t.name not in s:
            raise CheckError(f"variável {t.name} sem valor na substituição")
        return s[t.name]
    return t


def _atom(a: Atom, s: dict) -> Atom:
    return Atom(a.pred, tuple(_term(t, s) for t in a.args))


def _match(pattern: Atom, cand: Atom, s: dict) -> dict | None:
    s2 = dict(s)
    for t, v in zip(pattern.args, cand.args):
        if isinstance(t, Var):
            if t.name in s2 and s2[t.name] != v:
                return None
            s2[t.name] = v
        elif t != v:
            return None
    return s2


def _pos_matches(pos: list, by_pred: dict, s: dict):
    if not pos:
        yield s
        return
    for cand in by_pred.get(pos[0].atom.pred, ()):
        s2 = _match(pos[0].atom, cand, s)
        if s2 is not None:
            yield from _pos_matches(pos[1:], by_pred, s2)


def _agg_value(func: str, elements: set):
    if func == "count":
        return len(elements)
    firsts = [e[0] for e in elements]
    if func == "sum":
        total = 0
        for x in firsts:
            if isinstance(x, int) and not isinstance(x, bool):
                total += x
        return total
    if not firsts:
        return None
    ordered = sorted(firsts, key=_order)
    return ordered[0] if func == "min" else ordered[-1]


def _agg_elements(agg: Agg, s: dict, by_pred: dict, S: set) -> set:
    pos = [l for l in agg.body if isinstance(l, Pos)]
    out = set()
    for s2 in _pos_matches(pos, by_pred, s):
        ok = True
        for l in agg.body:
            if isinstance(l, Cmp) and not _cmp_holds(l.op, _term(l.left, s2), _term(l.right, s2)):
                ok = False
            elif isinstance(l, (Naf, NaoConsta)) and _atom(l.atom, s2) in S:
                ok = False
        if ok:
            out.add(tuple(_term(t, s2) for t in agg.terms))
    return out


def _complete(rule, s: dict, by_pred: dict, S: set):
    """Given a substitution for the positive literals, evaluate aggregates, comparisons and absences.

    Yields the completed substitutions (aggregates may bind their result variable).
    """
    s = dict(s)
    for lit in rule.body:
        if isinstance(lit, Agg):
            value = _agg_value(lit.func, _agg_elements(lit, s, by_pred, S))
            if value is None:
                return
            if isinstance(lit.result, Var) and lit.result.name not in s:
                s[lit.result.name] = value
            elif _term(lit.result, s) != value:
                return
    for lit in rule.body:
        if isinstance(lit, Cmp) and not _cmp_holds(lit.op, _term(lit.left, s), _term(lit.right, s)):
            return
        if isinstance(lit, (Naf, NaoConsta)) and _atom(lit.atom, s) in S:
            return
    yield s


def _instances(rule, by_pred: dict, S: set):
    pos = [l for l in rule.body if isinstance(l, Pos)]
    for s in _pos_matches(pos, by_pred, {}):
        yield from _complete(rule, s, by_pred, S)


def _by_pred(atoms) -> dict:
    out: dict = {}
    for a in atoms:
        out.setdefault(a.pred, []).append(a)
    return out


# -- defeasible reasoning, re-implemented ----------------------------------------


def _strict_closure(program: Program, atoms: set) -> set:
    rules = [r for r in program.rules if not r.defeasible and all(isinstance(l, (Pos, Cmp)) for l in r.body)]
    known = set(atoms)
    while True:
        new = set()
        idx = _by_pred(known)
        for r in rules:
            for s in _pos_matches([l for l in r.body if isinstance(l, Pos)], idx, {}):
                if all(_cmp_holds(l.op, _term(l.left, s), _term(l.right, s)) for l in r.body if isinstance(l, Cmp)):
                    h = _atom(r.head, s)
                    if h not in known:
                        new.add(h)
        if not new:
            return known
        known |= new


def _premises(rule, s: dict) -> tuple:
    return tuple(_atom(l.atom, s) for l in rule.body if isinstance(l, Pos))


def _beats(program: Program, r, rs: dict, s, ss: dict) -> bool:
    if r.label and s.label:
        if (r.label, s.label) in program.priorities:
            return True
        if (s.label, r.label) in program.priorities:
            return False
    pr, ps = set(_premises(r, rs)), set(_premises(s, ss))
    return ps <= _strict_closure(program, pr) and not pr <= _strict_closure(program, ps)


def _decide(program: Program, base_atom: Atom, by_pred: dict, S: set) -> str:
    """'pos' | 'neg' | 'nenhum' (INDETERMINADO) | 'fato' (asserted knowledge decides) | 'sem_regra'."""
    neg_atom = Atom(base_atom.pred.negated(), base_atom.args)
    facts = set(program.facts)
    if base_atom in facts or neg_atom in facts:
        return "fato"
    sides = {}
    for target in (base_atom, neg_atom):
        inst = []
        for r in program.rules:
            if r.defeasible and r.head.pred == target.pred:
                for s in _instances(r, by_pred, S):
                    if _atom(r.head, s) == target:
                        inst.append((r, s))
        sides[target] = inst
    sup, att = sides[base_atom], sides[neg_atom]
    if not sup and not att:
        return "sem_regra"

    def wins(mine, others):
        return bool(mine) and all(any(_beats(program, m, ms, o, os) for m, ms in mine) for o, os in others)

    p, n = wins(sup, att), wins(att, sup)
    if p and not n:
        return "pos"
    if n and not p:
        return "neg"
    return "nenhum"


# -- 1. model -------------------------------------------------------------------


def check_model(program: Program, certificate: dict, indeterminate: set | frozenset = frozenset()) -> set:
    S = set(certificate)
    facts = set(program.facts)
    rules = {r.id: r for r in program.rules}
    by_pred = _by_pred(S)
    for f in facts:
        if f not in S:
            raise CheckError(f"fato afirmado ausente do modelo: {f}")
    for atom, (rank, rule_id, subst, premises) in certificate.items():
        if not isinstance(rank, int) or rank < 1:
            raise CheckError(f"rank inválido para {atom}")
        if rule_id is None:
            if atom not in facts:
                raise CheckError(f"{atom} declarado fato mas não foi afirmado")
            continue
        rule = rules.get(rule_id)
        if rule is None:
            raise CheckError(f"regra {rule_id} inexistente (suporte de {atom})")
        if _atom(rule.head, subst) != atom:
            raise CheckError(f"cabeça da regra {rule_id} não produz {atom}")
        expected = list(_premises(rule, subst))
        if list(premises) != expected:
            raise CheckError(f"premissas de {atom} não correspondem à regra {rule_id}")
        for p in expected:
            if p not in S:
                raise CheckError(f"premissa {p} de {atom} fora do modelo")
            if certificate[p][0] >= rank:
                raise CheckError(f"suporte circular ou rank não decrescente: {p} -> {atom}")
        if not any(True for _ in _complete(rule, {k: v for k, v in subst.items()}, by_pred, S)):
            raise CheckError(f"agregado, comparação ou ausência falha no suporte de {atom}")
        if rule.defeasible:
            base = Atom(PredKey(atom.pred.name, atom.pred.arity, False), atom.args)
            outcome = _decide(program, base, by_pred, S)
            if outcome != ("neg" if atom.pred.neg else "pos"):
                raise CheckError(f"{atom} sustentado por regra derrotável que não vence o conflito ({outcome})")
    # closure of the strict rules
    for rule in program.rules:
        if rule.defeasible:
            continue
        for s in _instances(rule, by_pred, S):
            head = _atom(rule.head, s)
            if head not in S:
                raise CheckError(f"modelo não fechado: regra {rule.id} deriva {head}")
    # every defeasible conflict decided as the checker decides it
    candidates = set()
    for rule in program.rules:
        if rule.defeasible:
            for s in _instances(rule, by_pred, S):
                h = _atom(rule.head, s)
                candidates.add(Atom(PredKey(h.pred.name, h.pred.arity, False), h.args))
    for base in candidates:
        outcome = _decide(program, base, by_pred, S)
        neg = Atom(base.pred.negated(), base.args)
        if outcome == "pos" and base not in S:
            raise CheckError(f"{base} deveria ter sido concluído (vence o conflito derrotável)")
        if outcome == "neg" and neg not in S:
            raise CheckError(f"{neg} deveria ter sido concluído (vence o conflito derrotável)")
        if outcome == "nenhum":
            if base in S or neg in S:
                raise CheckError(f"{base}: conflito sem vencedor mas uma conclusão foi afirmada")
            if base not in indeterminate:
                raise CheckError(f"{base}: conflito sem vencedor não declarado INDETERMINADO")
    for a in indeterminate:
        if _decide(program, a, by_pred, S) != "nenhum":
            raise CheckError(f"{a} declarado INDETERMINADO mas o conflito tem vencedor")
    return S


# -- 2. proofs ------------------------------------------------------------------


def check_proof(program: Program, tree: dict, S: set) -> int:
    atom = tree["atomo"]
    if tree["tipo"] == "fato":
        if atom not in set(program.facts):
            raise CheckError(f"{atom} não é fato afirmado")
        return 1
    if tree["tipo"] != "regra":
        raise CheckError(f"tipo de passo desconhecido: {tree['tipo']}")
    rules = {r.id: r for r in program.rules}
    rule = rules.get(tree["regra"])
    if rule is None:
        raise CheckError(f"regra {tree['regra']} inexistente")
    s = tree["subst"]
    if _atom(rule.head, s) != atom:
        raise CheckError(f"regra {rule.id} com essa substituição não conclui {atom}")
    expected_pos = list(_premises(rule, s))
    got_pos = [p["atomo"] for p in tree["premissas"]]
    if got_pos != expected_pos:
        raise CheckError(f"premissas do passo de {atom} não correspondem à regra {rule.id}")
    expected_abs = [
        ("not" if isinstance(l, Naf) else "nao_consta", _atom(l.atom, s))
        for l in rule.body if isinstance(l, (Naf, NaoConsta))
    ]
    got_abs = [(a["tipo"], a["atomo"]) for a in tree["ausencias"]]
    if sorted(map(str, got_abs)) != sorted(map(str, expected_abs)):
        raise CheckError(f"ausências do passo de {atom} não correspondem à regra {rule.id}")
    for _, a in expected_abs:
        if a in S:
            raise CheckError(f"ausência falsa: {a} pertence ao modelo")
    for lit in rule.body:
        if isinstance(lit, Cmp) and not _cmp_holds(lit.op, _term(lit.left, s), _term(lit.right, s)):
            raise CheckError(f"comparação falsa no passo de {atom}: {lit}")
    by_pred = _by_pred(S)
    claimed_aggs = {a["indice"]: a for a in tree.get("agregados", [])}
    for i, lit in enumerate(rule.body):
        if isinstance(lit, Agg):
            elements = _agg_elements(lit, s, by_pred, S)
            value = _agg_value(lit.func, elements)
            if value is None or _term(lit.result, s) != value:
                raise CheckError(f"agregado #{lit.func} não produz {_term(lit.result, s)} no passo de {atom}")
            claim = claimed_aggs.get(i)
            if claim is None or set(map(tuple, claim["elementos"])) != elements or claim["valor"] != value:
                raise CheckError(f"agregado declarado na prova difere da recontagem no passo de {atom}")
    if rule.defeasible:
        base = Atom(PredKey(atom.pred.name, atom.pred.arity, False), atom.args)
        if _decide(program, base, by_pred, S) != ("neg" if atom.pred.neg else "pos"):
            raise CheckError(f"passo derrotável de {atom} não vence o conflito")
    size = 1
    for p in tree["premissas"]:
        size += check_proof(program, p, S)
    return size


def _rule_assumes_open(program: Program, rule) -> bool:
    """A rule step assumes something about open knowledge: nao_consta, or an aggregate over open predicates."""
    for lit in rule.body:
        if isinstance(lit, NaoConsta):
            return True
        if isinstance(lit, Agg):
            for inner in lit.body:
                if isinstance(inner, NaoConsta):
                    return True
                if isinstance(inner, (Pos, Naf)) and not program.is_closed(inner.atom.pred):
                    return True
    return False


def proof_uses_absence_assumption(tree: dict, program: Program | None = None, S: set | None = None) -> bool:
    """Whether the proof rests on an assumption about open-world knowledge (decided from the program, not the tree)."""
    if tree["tipo"] == "fato":
        return False
    if any(a["tipo"] == "nao_consta" for a in tree["ausencias"]):
        return True
    if program is not None:
        rule = {r.id: r for r in program.rules}.get(tree["regra"])
        if rule is not None and _rule_assumes_open(program, rule):
            return True
    return any(proof_uses_absence_assumption(p, program, S) for p in tree["premissas"])


# -- 3. status ------------------------------------------------------------------


def check_status(program: Program, atom: Atom, claimed_value: str, claimed_qualifier, S: set,
                 proof: dict | None = None, neg_proof: dict | None = None,
                 indeterminate: set | frozenset = frozenset()) -> None:
    neg = Atom(atom.pred.negated(), atom.args)
    facts = set(program.facts)
    pos_in, neg_in = atom in S, neg in S
    if pos_in and neg_in:
        expected = "CONTRADITORIO"
    elif pos_in:
        expected = "VERDADEIRO"
    elif neg_in:
        expected = "FALSO"
    elif atom in indeterminate:
        expected = "INDETERMINADO"
    elif program.is_closed(atom.pred):
        expected = "FALSO"
    else:
        expected = "DESCONHECIDO"
    if claimed_value != expected:
        raise CheckError(f"status de {atom}: afirmado {claimed_value}, verificado {expected}")
    if expected == "FALSO" and not neg_in and claimed_qualifier != "mundo_fechado":
        raise CheckError(f"{atom}: FALSO sem prova de negação deve ser mundo_fechado")
    if expected in ("VERDADEIRO", "FALSO") and claimed_qualifier != "mundo_fechado":
        target, tree = (atom, proof) if expected == "VERDADEIRO" else (neg, neg_proof)
        if tree is None:
            raise CheckError(f"{atom}: status {expected} sem prova")
        if tree["atomo"] != target:
            raise CheckError(f"prova apresentada é de {tree['atomo']}, não de {target}")
        check_proof(program, tree, S)
        if claimed_qualifier == "afirmado" and target not in facts:
            raise CheckError(f"{target} declarado afirmado mas não é fato")
        if claimed_qualifier == "inferido" and proof_uses_absence_assumption(tree, program, S):
            raise CheckError(f"{target} declarado inferido mas a prova usa suposição sobre mundo aberto")
    if expected == "CONTRADITORIO":
        if proof is None or neg_proof is None:
            raise CheckError(f"{atom}: contradição exige as duas provas")
        check_proof(program, proof, S)
        check_proof(program, neg_proof, S)
