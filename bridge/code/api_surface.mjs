// The public API surface of an installed npm package, read by the TypeScript compiler from its type declarations.
//
//   node api_surface.mjs surface <package-dir>
//      -> {name, version, exports: [[exportName, space, signature], ...]}
//   node api_surface.mjs probe <package-dir> <json-list-of-[name, space]>
//      -> {results: {name: true|false}}: whether `import { name } from <package>` compiles and is usable in that
//         space, per the real compiler (the oracle for API-diff claims)
//
// The compiler API comes from NUCLEO_TS (a directory with node_modules/typescript, version 6).
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';

const ts = createRequire(path.join(path.resolve(process.env.NUCLEO_TS ?? '.'), 'package.json'))('typescript');
const [mode, pkgDirArg, extra] = process.argv.slice(2);
const pkgDir = path.resolve(pkgDirArg);
const pkg = JSON.parse(fs.readFileSync(path.join(pkgDir, 'package.json'), 'utf8'));

// A scratch project whose `node_modules/<name>` is the package directory, so resolution follows the package's own
// "types"/"exports" fields exactly as a user's project would.
function scratch(source) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'nucleo-api-'));
  const nm = path.join(dir, 'node_modules', ...pkg.name.split('/'));
  fs.mkdirSync(path.dirname(nm), { recursive: true });
  fs.symlinkSync(pkgDir, nm, 'junction');
  // the package's own dependencies (types it re-exports) resolve from the directory that holds it
  const holder = path.dirname(pkg.name.startsWith('@') ? path.dirname(pkgDir) : pkgDir);
  const file = path.join(dir, 'probe.ts');
  fs.writeFileSync(file, source);
  const options = {
    strict: true, noEmit: true, target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext,
    moduleResolution: ts.ModuleResolutionKind.Bundler, skipLibCheck: true, types: [],
    typeRoots: [], baseUrl: dir, paths: { '*': ['node_modules/*', path.join(holder, '*').replace(/\\/g, '/')] },
  };
  return { dir, file, program: ts.createProgram([file], options) };
}

function cleanup(dir) {
  fs.rmSync(dir, { recursive: true, force: true });
}

if (mode === 'surface') {
  const { dir, file, program } = scratch(`import * as M from '${pkg.name}';\nexport { M };\n`);
  const checker = program.getTypeChecker();
  const sf = program.getSourceFile(file);
  const imp = sf.statements[0];
  const modSym = checker.getSymbolAtLocation(imp.moduleSpecifier);
  const out = [];
  if (modSym) {
    // `export type { X }` (anywhere along the alias chain) exports only X's type meaning, even for a class
    const typeOnly = (sym) => {
      for (let s = sym, hops = 0; s && s.flags & ts.SymbolFlags.Alias && hops < 20; hops++) {
        if ((s.declarations ?? []).some((d) => (ts.isExportSpecifier(d) || ts.isImportSpecifier(d)) && (d.isTypeOnly || d.parent?.parent?.isTypeOnly) || ts.isImportClause(d) && d.isTypeOnly)) return true;
        const next = checker.getImmediateAliasedSymbol ? checker.getImmediateAliasedSymbol(s) : null;
        if (!next || next === s) break;
        s = next;
      }
      return false;
    };
    // a CommonJS `export =` module also offers a default import (the options used allow synthetic defaults)
    if (modSym.exports?.has('export=')) out.push(['default', 'valor', 'export=']);
    for (const s of checker.getExportsOfModule(modSym)) {
      const target = s.flags & ts.SymbolFlags.Alias ? checker.getAliasedSymbol(s) : s;
      const isValue = (target.flags & ts.SymbolFlags.Value) !== 0 && !typeOnly(s);
      const isType = (target.flags & ts.SymbolFlags.Type) !== 0 || (target.flags & ts.SymbolFlags.Namespace) !== 0;
      const space = isValue && isType ? 'ambos' : isValue ? 'valor' : 'tipo';
      let sig = '';
      try {
        const decl = target.declarations?.[0];
        if (isValue && decl) sig = checker.typeToString(checker.getTypeOfSymbolAtLocation(target, decl), undefined, ts.TypeFormatFlags.NoTruncation);
        else if (decl) sig = checker.typeToString(checker.getDeclaredTypeOfSymbol(target), undefined, ts.TypeFormatFlags.NoTruncation);
      } catch {
        sig = '?';
      }
      out.push([s.escapedName.toString(), space, sig.length > 400 ? sig.slice(0, 400) : sig]);
    }
  }
  cleanup(dir);
  process.stdout.write(JSON.stringify({ name: pkg.name, version: pkg.version, resolved: !!modSym, exports: out }) + '\n');
} else if (mode === 'probe') {
  const names = JSON.parse(fs.readFileSync(extra, 'utf8'));
  const results = {};
  // one file per name keeps diagnostics attributable (batched per program for speed: one probe line per name)
  const lines = names.map(([n, space], i) => (space === 'tipo'
    ? `import type { ${n} as T${i} } from '${pkg.name}';\ntype U${i} = T${i};`
    : `import { ${n} as V${i} } from '${pkg.name}';\nvoid V${i};`));
  const { dir, file, program } = scratch(lines.join('\n') + '\n');
  const sf = program.getSourceFile(file);
  // errors about how a name is used, not whether it exists: a generic type without its type arguments (TS2314,
  // TS2707), a namespace written as a type (TS2709)
  const ARITY = new Set([2314, 2707, 2709]);
  const diags = [...program.getSemanticDiagnostics(sf), ...program.getSyntacticDiagnostics(sf)].filter((d) => !ARITY.has(d.code));
  const badLines = new Set(diags.filter((d) => d.file === sf && d.start !== undefined).map((d) => sf.getLineAndCharacterOfPosition(d.start).line));
  names.forEach(([n], i) => {
    results[n] = !badLines.has(2 * i) && !badLines.has(2 * i + 1);
  });
  cleanup(dir);
  process.stdout.write(JSON.stringify({ name: pkg.name, version: pkg.version, results }) + '\n');
}
