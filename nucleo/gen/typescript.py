"""Model -> a TypeScript project: types, validators, an in-memory store with referential integrity, and tests.

Every file is derived from the model; nothing is written by hand per project. Error codes are "<field>:<rule>",
the same in every generated language and in the model's reference meaning (``model.reference_errors``), so the
implementations can be compared mechanically.
"""

from __future__ import annotations

import json

TS_TYPE = {"texto": "string", "inteiro": "number", "decimal": "number", "booleano": "boolean"}


def _field_type(f: dict) -> str:
    if f["tipo"] == "enum":
        return " | ".join(json.dumps(v) for v in f["valores"])
    return TS_TYPE[f["tipo"]]


def model_ts(model: dict) -> str:
    out = ["// Generated from the project model. Do not edit: change the model and generate again.", ""]
    for e in model["entidades"]:
        out.append(f"export interface {e['nome']} {{")
        out.append("  readonly id?: string;")
        for f in e.get("campos", []):
            opt = "" if f.get("obrigatorio") else "?"
            out.append(f"  {f['nome']}{opt}: {_field_type(f)}{'' if f.get('obrigatorio') else ' | null'};")
        for r in e.get("relacoes", []):
            out.append(f"  {r['nome']}?: {'string[]' if r.get('muitos') else 'string'} | null;  // ids of {r['alvo']}")
        out.append("}")
        out.append("")
    return "\n".join(out)


def _check(f: dict) -> list[str]:
    n, t = f["nome"], f["tipo"]
    v = f"o[{json.dumps(n)}]"
    lines = [f"  if ({v} === undefined || {v} === null) {{"]
    if f.get("obrigatorio"):
        lines.append(f"    errors.push({json.dumps(n + ':obrigatorio')});")
    lines.append("  } else {")
    if t == "texto":
        lines.append(f"    const s = {v};")
        lines.append(f"    if (typeof s !== 'string') errors.push({json.dumps(n + ':tipo')});")
        lines.append("    else {")
        lines.append("      const length = [...s].length;  // characters, not UTF-16 units")
        if "min" in f:
            lines.append(f"      if (length < {f['min']}) errors.push({json.dumps(n + ':min')});")
        if "max" in f:
            lines.append(f"      if (length > {f['max']}) errors.push({json.dumps(n + ':max')});")
        if f.get("formato") == "email":
            lines.append(f"      if (!/^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$/.test(s)) errors.push({json.dumps(n + ':formato')});")
        lines.append("    }")
    elif t in ("inteiro", "decimal"):
        lines.append(f"    const x = {v};")
        cond = "typeof x !== 'number' || !Number.isFinite(x)" + (" || !Number.isInteger(x)" if t == "inteiro" else "")
        lines.append(f"    if ({cond}) errors.push({json.dumps(n + ':tipo')});")
        lines.append("    else {")
        if "min" in f:
            lines.append(f"      if (x < {f['min']}) errors.push({json.dumps(n + ':min')});")
        if "max" in f:
            lines.append(f"      if (x > {f['max']}) errors.push({json.dumps(n + ':max')});")
        lines.append("    }")
    elif t == "booleano":
        lines.append(f"    if (typeof {v} !== 'boolean') errors.push({json.dumps(n + ':tipo')});")
    else:
        lines.append(f"    if (!({json.dumps(f['valores'])} as unknown[]).includes({v})) "
                     f"errors.push({json.dumps(n + ':valores')});")
    lines.append("  }")
    return lines


def validate_ts(model: dict) -> str:
    out = ["// Generated from the project model. Do not edit: change the model and generate again.", "",
           "type Obj = Record<string, unknown>;", ""]
    for e in model["entidades"]:
        out.append(f"/** What is wrong with a candidate {e['nome']}: codes \"<field>:<rule>\"; empty when valid. */")
        out.append(f"export function validate{e['nome']}(value: unknown): string[] {{")
        out.append("  if (typeof value !== 'object' || value === null || Array.isArray(value)) return ['$:objeto'];")
        out.append("  const o = value as Obj;")
        out.append("  const errors: string[] = [];")
        for f in e.get("campos", []):
            out += _check(f)
        for r in e.get("relacoes", []):
            v = f"o[{json.dumps(r['nome'])}]"
            if r.get("muitos"):
                cond = f"!Array.isArray({v}) || !({v} as unknown[]).every((x) => typeof x === 'string')"
            else:
                cond = f"typeof {v} !== 'string'"
            out.append(f"  if ({v} !== undefined && {v} !== null && ({cond})) errors.push({json.dumps(r['nome'] + ':tipo')});")
        out.append("  return errors;")
        out.append("}")
        out.append("")
    # one key per entity, exactly: indexing it with an entity name is always defined (strict indexed access)
    out.append("export const VALIDATORS = {")
    for e in model["entidades"]:
        out.append(f"  {e['nome']}: validate{e['nome']},")
    out.append("} as const;")
    return "\n".join(out) + "\n"


def store_ts(model: dict) -> str:
    rels = {e["nome"]: e.get("relacoes", []) for e in model["entidades"]}
    out = ["// Generated from the project model. Do not edit: change the model and generate again.", "",
           "import { VALIDATORS } from './validate';", "",
           "export type Result = { ok: true; id: string } | { ok: false; errors: string[] };", "",
           f"export type EntityName = {' | '.join(json.dumps(e['nome']) for e in model['entidades'])};", "",
           f"const RELATIONS: Record<EntityName, ReadonlyArray<{{ field: string; target: EntityName; many: boolean }}>> = {{"]
    for name, rs in rels.items():
        items = ", ".join(f"{{ field: {json.dumps(r['nome'])}, target: {json.dumps(r['alvo'])}, many: "
                          f"{'true' if r.get('muitos') else 'false'} }}" for r in rs)
        out.append(f"  {name}: [{items}],")
    out += ["};", "",
            "/** In-memory store: every write is validated, and relations must point to existing records. */",
            "export class Store {",
            "  private readonly tables = new Map<EntityName, Map<string, Record<string, unknown>>>();",
            "  private next = 1;", "",
            "  private table(kind: EntityName): Map<string, Record<string, unknown>> {",
            "    let t = this.tables.get(kind);",
            "    if (!t) {", "      t = new Map();", "      this.tables.set(kind, t);", "    }", "    return t;", "  }", "",
            "  private check(kind: EntityName, value: Record<string, unknown>): string[] {",
            "    const errors = VALIDATORS[kind](value);",
            "    for (const rel of RELATIONS[kind]) {",
            "      const v = value[rel.field];",
            "      if (v === undefined || v === null) continue;",
            "      const ids = rel.many ? (Array.isArray(v) ? v : []) : [v];",
            "      if (ids.some((id) => typeof id !== 'string' || !this.table(rel.target).has(id))) errors.push(`${rel.field}:referencia`);",
            "    }",
            "    return errors;", "  }", "",
            "  create(kind: EntityName, value: Record<string, unknown>): Result {",
            "    const errors = this.check(kind, value);",
            "    if (errors.length > 0) return { ok: false, errors };",
            "    const id = `${kind}-${this.next++}`;",
            "    this.table(kind).set(id, { ...value, id });",
            "    return { ok: true, id };", "  }", "",
            "  get(kind: EntityName, id: string): Record<string, unknown> | undefined {",
            "    const v = this.table(kind).get(id);", "    return v ? { ...v } : undefined;", "  }", "",
            "  list(kind: EntityName): Record<string, unknown>[] {",
            "    return [...this.table(kind).values()].map((v) => ({ ...v }));", "  }", "",
            "  update(kind: EntityName, id: string, changes: Record<string, unknown>): Result {",
            "    const current = this.table(kind).get(id);",
            "    if (!current) return { ok: false, errors: ['$:inexistente'] };",
            "    const next = { ...current, ...changes, id };",
            "    const errors = this.check(kind, next);",
            "    if (errors.length > 0) return { ok: false, errors };",
            "    this.table(kind).set(id, next);", "    return { ok: true, id };", "  }", "",
            "  /** Refused while another record still points to this one. */",
            "  remove(kind: EntityName, id: string): Result {",
            "    if (!this.table(kind).has(id)) return { ok: false, errors: ['$:inexistente'] };",
            "    for (const [other, rels] of Object.entries(RELATIONS) as [EntityName, typeof RELATIONS[EntityName]][]) {",
            "      for (const rel of rels) {",
            "        if (rel.target !== kind) continue;",
            "        for (const rec of this.table(other).values()) {",
            "          const v = rec[rel.field];",
            "          if (v === id || (Array.isArray(v) && v.includes(id))) return { ok: false, errors: ['$:referenciado'] };",
            "        }", "      }", "    }",
            "    this.table(kind).delete(id);", "    return { ok: true, id };", "  }", "}", ""]
    return "\n".join(out)


def index_ts(model: dict) -> str:
    return ("// Generated from the project model.\nexport * from './model';\nexport * from './validate';\n"
            "export * from './store';\n")


def tests_ts(model: dict, examples: dict) -> str:
    """Tests from the model: a valid example of each entity is accepted, each single violation gives exactly its
    code, and the store keeps referential integrity. `examples` = {entity: {"valido": obj, "violacoes": [[obj, code]]}}."""
    out = ["// Generated from the project model.", "import { Store, VALIDATORS } from '../src/index';", "",
           "let failures = 0;",
           "function eq(name: string, got: unknown, want: unknown): void {",
           "  if (JSON.stringify(got) !== JSON.stringify(want)) {",
           "    failures++;",
           "    console.log(`FALHOU ${name}: ${JSON.stringify(got)} != ${JSON.stringify(want)}`);", "  }", "}", ""]
    for e in model["entidades"]:
        ex = examples[e["nome"]]
        out.append(f"eq({json.dumps(e['nome'] + ' válido')}, VALIDATORS.{e['nome']}({json.dumps(ex['valido'])}), []);")
        for obj, codes in ex["violacoes"]:
            out.append(f"eq({json.dumps(e['nome'] + ' ' + ','.join(codes))}, "
                       f"[...VALIDATORS.{e['nome']}({json.dumps(obj)})].sort(), {json.dumps(sorted(codes))});")
    out += ["", "{", "  const s = new Store();"]
    order = _creation_order(model)
    for name in order:
        ent = next(e for e in model["entidades"] if e["nome"] == name)
        obj = dict(examples[name]["valido"])
        for r in ent.get("relacoes", []):
            obj.pop(r["nome"], None)
        out.append(f"  const r{name} = s.create({json.dumps(name)}, {json.dumps(obj)});")
        out.append(f"  eq({json.dumps('criar ' + name)}, r{name}.ok, true);")
        out.append(f"  if (r{name}.ok) eq({json.dumps('ler ' + name)}, s.get({json.dumps(name)}, r{name}.id)?.id, r{name}.id);")
    for e in model["entidades"]:
        for r in e.get("relacoes", []):
            bad = ["nao-existe"] if r.get("muitos") else "nao-existe"
            obj = dict(examples[e["nome"]]["valido"])
            obj[r["nome"]] = bad
            out.append(f"  eq({json.dumps(e['nome'] + '.' + r['nome'] + ' referência inexistente')}, "
                       f"s.create({json.dumps(e['nome'])}, {json.dumps(obj)}), "
                       f"{{ ok: false, errors: [{json.dumps(r['nome'] + ':referencia')}] }});")
    out += ["}", "", "console.log(failures === 0 ? 'OK' : `${failures} falha(s)`);",
            "if (failures > 0) (globalThis as unknown as { process: { exitCode: number } }).process.exitCode = 1;", ""]
    return "\n".join(out)


def _creation_order(model: dict) -> list[str]:
    return [e["nome"] for e in model["entidades"]]


def project(model: dict, examples: dict) -> dict[str, str]:
    return {
        "src/model.ts": model_ts(model),
        "src/validate.ts": validate_ts(model),
        "src/store.ts": store_ts(model),
        "src/index.ts": index_ts(model),
        "test/run.ts": tests_ts(model, examples),
        "tsconfig.json": json.dumps({"compilerOptions": {
            "strict": True, "target": "ES2022", "module": "CommonJS", "outDir": "out", "rootDir": ".",
            "noUncheckedIndexedAccess": True, "exactOptionalPropertyTypes": False, "types": [],
            "lib": ["ES2022", "DOM"], "skipLibCheck": True}, "include": ["src", "test"]}, indent=1),
    }
