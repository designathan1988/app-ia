"""Independent proof checker.

Trusted base: this module plus ``nucleo.kb.syntax``, which only holds data
structures and the parser. It deliberately does **not** import ``nucleo.logic``.
Matching, comparison and closure checking are re-implemented here in a simple,
different way (naive nested loops), so that a bug in the engine is not repeated
in the checker.

Checks:

1. ``check_model`` — the certified set S is exactly the stable model of the
   program. Two conditions together are sufficient (Fages: well-supported models
   are the stable models, and a stratified program has exactly one):

   * **support**: every atom of S is an asserted fact, or has a rule instance
     whose positive premises are in S with strictly smaller rank, whose absent
     atoms are not in S, and whose comparisons hold;
   * **closure**: every rule instance whose positive body is in S, whose
     comparisons hold and whose absent atoms are not in S, has its head in S; and
     every fact is in S.

2. ``check_proof`` — each step of a proof tree is a correct instance of a rule
   (or an asserted fact); absences are checked against the verified S.

3. ``check_status`` — recomputes the status from S, the facts and the worlds,
   and compares it with the claim.
"""

from __future__ import annotations

from ..kb.syntax import Atom, Cmp, Naf, NaoConsta, Pos, Program, Sym, Text, Var


class CheckError(AssertionError):
    pass


# -- own implementations (intentionally independent of the engine) ----------


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


def _subst_term(t, s: dict):
    if isinstance(t, Var):
        if t.name not in s:
            raise CheckError(f"variável {t.name} sem valor na substituição")
        return s[t.name]
    return t


def _subst_atom(a: Atom, s: dict) -> Atom:
    return Atom(a.pred, tuple(_subst_term(t, s) for t in a.args))


def _instances(rule, S_by_pred: dict, S: set):
    """All substitutions (var name -> value) satisfying the positive body over S, naive order."""
    positives = [lit for lit in rule.body if isinstance(lit, Pos)]

    def rec(i: int, s: dict):
        if i == len(positives):
            yield s
            return
        pat = positives[i].atom
        for cand in S_by_pred.get(pat.pred, ()):
            s2 = dict(s)
            ok = True
            for t, v in zip(pat.args, cand.args):
                if isinstance(t, Var):
                    if t.name in s2 and s2[t.name] != v:
                        ok = False
                        break
                    s2[t.name] = v
                elif t != v:
                    ok = False
                    break
            if ok:
                yield from rec(i + 1, s2)

    yield from rec(0, {})


def _rest_holds(rule, s: dict, S: set) -> bool:
    for lit in rule.body:
        if isinstance(lit, Cmp):
            if not _cmp_holds(lit.op, _subst_term(lit.left, s), _subst_term(lit.right, s)):
                return False
        elif isinstance(lit, (Naf, NaoConsta)):
            if _subst_atom(lit.atom, s) in S:
                return False
    return True


# -- 1. model ---------------------------------------------------------------


def check_model(program: Program, certificate: dict) -> set:
    S = set(certificate)
    facts = set(program.facts)
    rules = {r.id: r for r in program.rules}
    for f in facts:
        if f not in S:
            raise CheckError(f"fato afirmado ausente do modelo: {f}")
    # support
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
        if _subst_atom(rule.head, subst) != atom:
            raise CheckError(f"cabeça da regra {rule_id} não produz {atom}")
        expected = [_subst_atom(l.atom, subst) for l in rule.body if isinstance(l, Pos)]
        if list(premises) != expected:
            raise CheckError(f"premissas de {atom} não correspondem à regra {rule_id}")
        for p in expected:
            if p not in S:
                raise CheckError(f"premissa {p} de {atom} fora do modelo")
            if certificate[p][0] >= rank:
                raise CheckError(f"suporte circular ou rank não decrescente: {p} -> {atom}")
        if not _rest_holds(rule, subst, S):
            raise CheckError(f"comparação ou ausência falha no suporte de {atom}")
    # closure
    by_pred: dict = {}
    for a in S:
        by_pred.setdefault(a.pred, []).append(a)
    for rule in program.rules:
        for s in _instances(rule, by_pred, S):
            if _rest_holds(rule, s, S):
                head = _subst_atom(rule.head, s)
                if head not in S:
                    raise CheckError(f"modelo não fechado: regra {rule.id} deriva {head}")
    return S


# -- 2. proofs ----------------------------------------------------------------


def check_proof(program: Program, tree: dict, S: set) -> int:
    """Verifies a proof tree against the program and the verified model S. Returns its size."""
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
    if _subst_atom(rule.head, s) != atom:
        raise CheckError(f"regra {rule.id} com essa substituição não conclui {atom}")
    expected_pos = [_subst_atom(l.atom, s) for l in rule.body if isinstance(l, Pos)]
    got_pos = [p["atomo"] for p in tree["premissas"]]
    if got_pos != expected_pos:
        raise CheckError(f"premissas do passo de {atom} não correspondem à regra {rule.id}")
    expected_abs = [
        ("not" if isinstance(l, Naf) else "nao_consta", _subst_atom(l.atom, s))
        for l in rule.body
        if isinstance(l, (Naf, NaoConsta))
    ]
    got_abs = [(a["tipo"], a["atomo"]) for a in tree["ausencias"]]
    if sorted(map(str, got_abs)) != sorted(map(str, expected_abs)):
        raise CheckError(f"ausências do passo de {atom} não correspondem à regra {rule.id}")
    for _, a in expected_abs:
        if a in S:
            raise CheckError(f"ausência falsa: {a} pertence ao modelo")
    for lit in rule.body:
        if isinstance(lit, Cmp):
            if not _cmp_holds(lit.op, _subst_term(lit.left, s), _subst_term(lit.right, s)):
                raise CheckError(f"comparação falsa no passo de {atom}: {lit}")
    size = 1 + len(expected_abs) + sum(1 for l in rule.body if isinstance(l, Cmp))
    for p in tree["premissas"]:
        size += check_proof(program, p, S)
    return size


def proof_uses_absence_assumption(tree: dict) -> bool:
    if tree["tipo"] == "fato":
        return False
    if any(a["tipo"] == "nao_consta" for a in tree["ausencias"]):
        return True
    return any(proof_uses_absence_assumption(p) for p in tree["premissas"])


# -- 3. status ----------------------------------------------------------------


def check_status(program: Program, atom: Atom, claimed_value: str, claimed_qualifier, S: set,
                 proof: dict | None = None, neg_proof: dict | None = None) -> None:
    neg = Atom(atom.pred.negated(), atom.args)
    facts = set(program.facts)
    closed = program.is_closed(atom.pred)
    pos_in, neg_in = atom in S, neg in S
    if pos_in and neg_in:
        expected = "CONTRADITORIO"
    elif pos_in:
        expected = "VERDADEIRO"
    elif neg_in:
        expected = "FALSO"
    elif closed:
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
        if claimed_qualifier == "inferido" and proof_uses_absence_assumption(tree):
            raise CheckError(f"{target} declarado inferido mas a prova usa nao_consta")
    if expected == "CONTRADITORIO":
        if proof is None or neg_proof is None:
            raise CheckError(f"{atom}: contradição exige as duas provas")
        check_proof(program, proof, S)
        check_proof(program, neg_proof, S)
