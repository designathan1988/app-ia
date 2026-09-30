// TypeScript code facts, in two independent layers, for one project.
//
//  1. SYNTAX (what the reasoning layer gets): scopes, declarations and identifier uses, read from the parse tree only
//     (no type checker). Scoping follows the language: var and parameters to the function, let/const/class and block
//     functions to the block, type parameters to their declaration, catch and for-heads to their own scope. Each name
//     lives in the value space, the type space or both.
//  2. ORACLE (what the reasoning layer is judged by): for every use, the declaration the TypeScript checker itself
//     resolves it to (checker.getSymbolAtLocation), or "external" when it is declared outside the project's sources.
//     Cross-file: for every import binding, the declaration the checker's aliased symbol reaches.
//
// Output: one JSON line per source file on stdout.
// Usage: node ts_facts.mjs <project-root> <tsconfig> [file-filter-substring]
import path from 'node:path';
import { createRequire } from 'node:module';

const root = path.resolve(process.argv[2]);
const require = createRequire(path.join(root, 'package.json'));
// TypeScript 7 (the Go port) has no JavaScript API: then the compiler API of a TypeScript 6 install is used
// (NUCLEO_TS = a directory holding node_modules/typescript)
let ts = {};
try {
  ts = require('typescript');
} catch {
  // a project without its own TypeScript install: use NUCLEO_TS below
}
if (typeof ts.getParsedCommandLineOfConfigFile !== 'function' && process.env.NUCLEO_TS) {
  ts = createRequire(path.join(path.resolve(process.env.NUCLEO_TS), 'package.json'))('typescript');
}
if (typeof ts.getParsedCommandLineOfConfigFile !== 'function') throw new Error(`typescript ${ts.version} sem API de compilador; defina NUCLEO_TS`);
const configPath = path.resolve(root, process.argv[3] ?? 'tsconfig.json');
const filter = process.argv[4] ?? '';

const parsed = ts.getParsedCommandLineOfConfigFile(configPath, {}, { ...ts.sys, onUnRecoverableConfigFileDiagnostic: () => {} });
const program = ts.createProgram({ rootNames: parsed.fileNames, options: parsed.options });
const checker = program.getTypeChecker();
const rel = (f) => path.relative(root, f).replace(/\\/g, '/');
const own = (sf) => !sf.isDeclarationFile && !sf.fileName.includes('node_modules') && rel(sf.fileName).startsWith('src/');

const K = ts.SyntaxKind;
const isFunctionLike = (n) => ts.isFunctionDeclaration(n) || ts.isFunctionExpression(n) || ts.isArrowFunction(n) || ts.isMethodDeclaration(n) || ts.isConstructorDeclaration(n) || ts.isGetAccessor(n) || ts.isSetAccessor(n);

function inTypePosition(id) {
  // an identifier used as a type: under a type node, except `typeof x` (a value) and an `extends` expression of a class
  for (let n = id.parent, prev = id; n; prev = n, n = n.parent) {
    if (ts.isTypeQueryNode(n) || ts.isComputedPropertyName(n)) return false; // `typeof x`, `[key]`: values
    if (ts.isTypeNode(n) && !ts.isExpressionWithTypeArguments(n)) return true;
    if (ts.isExpressionWithTypeArguments(n)) {
      const clause = n.parent;
      if (ts.isHeritageClause(clause) && clause.token === K.ExtendsKeyword && ts.isClassLike(clause.parent)) return false;
      return true;
    }
    if (ts.isStatement(n) || ts.isExpression(n) && !ts.isIdentifier(n) && !ts.isQualifiedName(n) && !ts.isPropertyAccessExpression(n)) return false;
  }
  return false;
}

function declSpace(d) {
  if (ts.isInterfaceDeclaration(d) || ts.isTypeAliasDeclaration(d) || ts.isTypeParameterDeclaration(d)) return 'tipo';
  if (ts.isClassLike(d) || ts.isEnumDeclaration(d) || ts.isImportSpecifier(d) || ts.isImportClause(d) || ts.isNamespaceImport(d) || ts.isImportEqualsDeclaration(d) || ts.isModuleDeclaration(d)) return 'ambos';
  return 'valor';
}

function namePos(decl) {
  const n = ts.getNameOfDeclaration(decl);
  return n ? n.getStart() : decl.getStart();
}

// The checker's answer for a use: the positions of every declaration of the symbol it resolves to (a merged symbol,
// such as a function and a type of the same name, has several, and any of them is that symbol), or "externo".
function oracleOf(id, sf) {
  const p = id.parent;
  let sym;
  if (ts.isShorthandPropertyAssignment(p) && p.name === id) sym = checker.getShorthandAssignmentValueSymbol(p);
  else if (ts.isExportSpecifier(p)) sym = checker.getExportSpecifierLocalTargetSymbol(p);
  else sym = checker.getSymbolAtLocation(id);
  if (!sym || !sym.declarations || sym.declarations.length === 0) return 'externo';
  const here = sym.declarations.filter((d) => d.getSourceFile() === sf).map(namePos);
  if (here.length > 0) return here;
  const d = sym.declarations[0];
  return own(d.getSourceFile()) ? `${rel(d.getSourceFile().fileName)}:${namePos(d)}` : 'externo';
}

function factsOf(sf) {
  const scopes = []; // [id, parent, kind]
  const decls = []; // [scope, name, pos, space, kind]
  const uses = []; // [pos, name, scope, space]
  const oracle = {}; // pos -> declaration pos | "externo" | "file:pos"
  const imports = []; // [localPos, localName, moduleSpecifier, importedName|"default"|"*"]
  const exportsOut = []; // [exportedName, localName|null, moduleSpecifier|null]  (null local with module = re-export)
  const aliasOracle = {}; // import local pos -> "file:pos" | "externo"
  const declared = new Set();
  let nextScope = 0;
  const newScope = (parent, kind) => {
    const id = nextScope++;
    scopes.push([id, parent, kind]);
    return id;
  };
  const declare = (scope, nameNode, space, kind) => {
    if (!nameNode || !ts.isIdentifier(nameNode)) return;
    decls.push([scope, nameNode.text, nameNode.getStart(), space, kind]);
    declared.add(nameNode);
  };
  const declareBinding = (scope, name, space, kind) => {
    if (!name) return;
    if (ts.isIdentifier(name)) declare(scope, name, space, kind);
    else for (const el of name.elements) if (!ts.isOmittedExpression(el)) declareBinding(scope, el.name, space, kind);
  };

  const module = newScope(-1, 'modulo');
  // the top-level declaration a use belongs to (its name position), or -1 for top-level code
  let owner = -1;
  const ownerOf = (st) => {
    if ((ts.isFunctionDeclaration(st) || ts.isClassDeclaration(st) || ts.isInterfaceDeclaration(st) || ts.isTypeAliasDeclaration(st) || ts.isEnumDeclaration(st) || ts.isModuleDeclaration(st)) && st.name) return st.name.getStart();
    if (ts.isVariableStatement(st)) {
      const first = st.declarationList.declarations[0]?.name;
      if (first && ts.isIdentifier(first)) return first.getStart();
    }
    return -1;
  };

  // hoisting: var declarations go to the nearest function scope
  function hoistVars(node, fnScope) {
    const visit = (n) => {
      if (n !== node && isFunctionLike(n)) return;
      if (ts.isVariableDeclarationList(n) && !(n.flags & (ts.NodeFlags.Let | ts.NodeFlags.Const | ts.NodeFlags.Using))) {
        for (const d of n.declarations) declareBinding(fnScope, d.name, 'valor', 'var');
      }
      ts.forEachChild(n, visit);
    };
    ts.forEachChild(node, visit);
  }

  // block-level declarations of a statement list (let/const/class/function/interface/type/enum/import)
  function declareStatements(statements, scope) {
    for (const st of statements) {
      if (ts.isVariableStatement(st) && st.declarationList.flags & (ts.NodeFlags.Let | ts.NodeFlags.Const | ts.NodeFlags.Using)) {
        for (const d of st.declarationList.declarations) declareBinding(scope, d.name, 'valor', 'let');
      } else if (ts.isFunctionDeclaration(st) && st.name) declare(scope, st.name, 'valor', 'funcao');
      else if (ts.isClassDeclaration(st) && st.name) declare(scope, st.name, 'ambos', 'classe');
      else if (ts.isInterfaceDeclaration(st)) declare(scope, st.name, 'tipo', 'interface');
      else if (ts.isTypeAliasDeclaration(st)) declare(scope, st.name, 'tipo', 'tipo');
      else if (ts.isEnumDeclaration(st)) declare(scope, st.name, 'ambos', 'enum');
      else if (ts.isModuleDeclaration(st) && ts.isIdentifier(st.name)) declare(scope, st.name, 'ambos', 'namespace');
      else if (ts.isImportDeclaration(st) && st.importClause) {
        const spec = st.moduleSpecifier.text;
        const ic = st.importClause;
        // `import type { A }` / `import { type A }` bind A in the type space only
        const space = (typeOnly) => (ic.isTypeOnly || typeOnly ? 'tipo' : 'ambos');
        if (ic.name) {
          declare(scope, ic.name, space(false), 'import');
          imports.push([ic.name.getStart(), ic.name.text, spec, 'default']);
        }
        const nb = ic.namedBindings;
        if (nb && ts.isNamespaceImport(nb)) {
          declare(scope, nb.name, space(false), 'import');
          imports.push([nb.name.getStart(), nb.name.text, spec, '*']);
        } else if (nb) {
          for (const el of nb.elements) {
            declare(scope, el.name, space(el.isTypeOnly), 'import');
            imports.push([el.name.getStart(), el.name.text, spec, (el.propertyName ?? el.name).text]);
          }
        }
      }
    }
  }

  function exportsOf(st) {
    const isExported = (n) => (ts.getCombinedModifierFlags(n) & ts.ModifierFlags.Export) !== 0;
    const isDefault = (n) => (ts.getCombinedModifierFlags(n) & ts.ModifierFlags.Default) !== 0;
    if (ts.isExportDeclaration(st)) {
      const spec = st.moduleSpecifier ? st.moduleSpecifier.text : null;
      if (!st.exportClause) exportsOut.push(['*', null, spec]);
      else if (ts.isNamedExports(st.exportClause)) for (const el of st.exportClause.elements) exportsOut.push([el.name.text, (el.propertyName ?? el.name).text, spec]);
      else exportsOut.push([st.exportClause.name.text, '*', spec]);
    } else if (ts.isExportAssignment(st) && ts.isIdentifier(st.expression)) exportsOut.push(['default', st.expression.text, null]);
    else if (ts.isVariableStatement(st) && isExported(st)) {
      const names = [];
      const collect = (n) => (ts.isIdentifier(n) ? names.push(n.text) : n.elements.forEach((e) => !ts.isOmittedExpression(e) && collect(e.name)));
      st.declarationList.declarations.forEach((d) => collect(d.name));
      for (const n of names) exportsOut.push([n, n, null]);
    } else if ((ts.isFunctionDeclaration(st) || ts.isClassDeclaration(st) || ts.isInterfaceDeclaration(st) || ts.isTypeAliasDeclaration(st) || ts.isEnumDeclaration(st)) && st.name && isExported(st)) {
      exportsOut.push([isDefault(st) ? 'default' : st.name.text, st.name.text, null]);
    }
  }

  function visit(node, scope) {
    if (ts.isSourceFile(node)) {
      hoistVars(node, scope);
      declareStatements(node.statements, scope);
      node.statements.forEach(exportsOf);
      for (const st of node.statements) {
        owner = ownerOf(st);
        visit(st, scope);
      }
      owner = -1;
      ts.forEachChild(node, (c) => !ts.isStatement(c) && visit(c, scope));
      return;
    }
    if (isFunctionLike(node)) {
      const fs = newScope(scope, 'funcao');
      if (ts.isFunctionExpression(node) && node.name) declare(fs, node.name, 'valor', 'funcao');
      node.typeParameters?.forEach((tp) => declare(fs, tp.name, 'tipo', 'parametro-tipo'));
      node.parameters.forEach((p) => declareBinding(fs, p.name, 'valor', 'parametro'));
      if (node.body) {
        hoistVars(node, fs);
        if (ts.isBlock(node.body)) declareStatements(node.body.statements, fs);
      }
      node.typeParameters?.forEach((c) => visit(c, fs));
      node.parameters.forEach((c) => visit(c, fs));
      if (node.type) visit(node.type, fs);
      if (node.body) {
        if (ts.isBlock(node.body)) node.body.statements.forEach((c) => visit(c, fs));
        else visit(node.body, fs);
      }
      return;
    }
    if (ts.isClassLike(node) || ts.isInterfaceDeclaration(node) || ts.isTypeAliasDeclaration(node)) {
      const cs = newScope(scope, 'classe');
      if (ts.isClassExpression(node) && node.name) declare(cs, node.name, 'ambos', 'classe');
      node.typeParameters?.forEach((tp) => declare(cs, tp.name, 'tipo', 'parametro-tipo'));
      ts.forEachChild(node, (c) => visit(c, cs));
      return;
    }
    if (ts.isMappedTypeNode(node) || ts.isInferTypeNode(node) || ts.isFunctionTypeNode(node) || ts.isConstructorTypeNode(node) || ts.isCallSignatureDeclaration(node) || ts.isMethodSignature(node) || ts.isConstructSignatureDeclaration(node)) {
      const ts2 = newScope(scope, 'tipo');
      if (ts.isMappedTypeNode(node)) declare(ts2, node.typeParameter.name, 'tipo', 'parametro-tipo');
      if (ts.isInferTypeNode(node)) {
        // `infer U` is visible in the true branch of the enclosing conditional type: declare it there (approximation)
        declare(scope, node.typeParameter.name, 'tipo', 'infer');
        return;
      }
      node.typeParameters?.forEach((tp) => declare(ts2, tp.name, 'tipo', 'parametro-tipo'));
      node.parameters?.forEach((p) => declareBinding(ts2, p.name, 'valor', 'parametro'));
      ts.forEachChild(node, (c) => visit(c, ts2));
      return;
    }
    if (ts.isBlock(node) || ts.isModuleBlock(node) || ts.isCaseBlock(node)) {
      const bs = newScope(scope, 'bloco');
      const statements = ts.isCaseBlock(node) ? node.clauses.flatMap((c) => c.statements) : node.statements;
      declareStatements(statements, bs);
      ts.forEachChild(node, (c) => visit(c, bs));
      return;
    }
    if (ts.isForStatement(node) || ts.isForInStatement(node) || ts.isForOfStatement(node)) {
      const fs = newScope(scope, 'for');
      const init = ts.isForStatement(node) ? node.initializer : node.initializer;
      if (init && ts.isVariableDeclarationList(init) && init.flags & (ts.NodeFlags.Let | ts.NodeFlags.Const | ts.NodeFlags.Using)) {
        for (const d of init.declarations) declareBinding(fs, d.name, 'valor', 'let');
      }
      ts.forEachChild(node, (c) => visit(c, fs));
      return;
    }
    if (ts.isCatchClause(node)) {
      const cs = newScope(scope, 'catch');
      if (node.variableDeclaration) declareBinding(cs, node.variableDeclaration.name, 'valor', 'catch');
      ts.forEachChild(node, (c) => visit(c, cs));
      return;
    }
    if (ts.isConditionalTypeNode(node)) {
      ts.forEachChild(node, (c) => visit(c, scope));
      return;
    }
    if (ts.isIdentifier(node)) {
      if (declared.has(node) || !isUse(node)) return;
      // an export names every meaning of a name (its value and its type): it looks in any space
      const exporting = ts.isExportSpecifier(node.parent) || ts.isExportAssignment(node.parent);
      const space = exporting ? 'qualquer' : inTypePosition(node) ? 'tipo' : 'valor';
      uses.push([node.getStart(), node.text, scope, space, owner]);
      oracle[node.getStart()] = oracleOf(node, sf);
      return;
    }
    ts.forEachChild(node, (c) => visit(c, scope));
  }

  function isUse(id) {
    const p = id.parent;
    if (!p) return false;
    if ((ts.isPropertyAccessExpression(p) || ts.isQualifiedName(p)) && (p.name === id || p.right === id)) return false;
    if (ts.isPropertyAssignment(p) && p.name === id) return false;
    if ((ts.isPropertyDeclaration(p) || ts.isPropertySignature(p) || ts.isMethodDeclaration(p) || ts.isMethodSignature(p) || ts.isGetAccessor(p) || ts.isSetAccessor(p) || ts.isEnumMember(p)) && p.name === id) return false;
    if (ts.isBindingElement(p) && p.propertyName === id) return false;
    if ((ts.isImportSpecifier(p) || ts.isExportSpecifier(p)) && (p.propertyName === id || p.name === id)) {
      // `export { a as b }` without a module: a is a use of the local a
      return ts.isExportSpecifier(p) && !p.parent.parent.moduleSpecifier && (p.propertyName ?? p.name) === id;
    }
    if (ts.isNamespaceExport(p) || ts.isLabeledStatement(p) || ts.isBreakOrContinueStatement(p)) return false;
    if (ts.isJsxAttribute(p) || (ts.isJsxOpeningLikeElement(p) || ts.isJsxClosingElement(p)) && p.tagName === id && /^[a-z]/.test(id.text)) return false;
    if (ts.isTypePredicateNode(p) && p.parameterName === id) return false;
    if (ts.isNamedTupleMember(p) && p.name === id) return false;
    if (ts.isTypeParameterDeclaration(p) || ts.isParameter(p) && p.name === id) return false;
    if (ts.isImportTypeNode(p) || ts.isModuleDeclaration(p) && p.name === id) return false;
    if (ts.isMetaProperty(p)) return false;
    return true;
  }

  visit(sf, module);
  // cross-file oracle: every declaration the checker's aliased symbol has, for each import binding
  for (const [pos] of imports) {
    const node = findIdentifierAt(sf, pos);
    let sym = node && checker.getSymbolAtLocation(node);
    if (sym && sym.flags & ts.SymbolFlags.Alias) sym = checker.getAliasedSymbol(sym);
    const ds = (sym?.declarations ?? []).filter((d) => own(d.getSourceFile()));
    aliasOracle[pos] = ds.length ? ds.map((d) => (ts.isSourceFile(d) ? `${rel(d.fileName)}:modulo` : `${rel(d.getSourceFile().fileName)}:${namePos(d)}`)) : 'externo';
  }
  // module resolution is a compiler fact (provenance: the TypeScript resolver with the project's options)
  const modules = {};
  for (const spec of new Set([...imports.map((i) => i[2]), ...exportsOut.map((e) => e[2]).filter((x) => x)])) {
    const r = ts.resolveModuleName(spec, sf.fileName, parsed.options, ts.sys).resolvedModule;
    // the same project boundary as the oracle's: files under src/, outside node_modules
    modules[spec] = r && !r.resolvedFileName.includes('node_modules') && rel(r.resolvedFileName).startsWith('src/') ? rel(r.resolvedFileName) : null;
  }
  return { file: rel(sf.fileName), scopes, decls, uses, oracle, imports, exports: exportsOut, aliasOracle, modules };
}

function findIdentifierAt(sf, pos) {
  let found = null;
  const walk = (n) => {
    if (found || pos < n.getStart() || pos >= n.getEnd()) return;
    if (ts.isIdentifier(n) && n.getStart() === pos) found = n;
    else ts.forEachChild(n, walk);
  };
  walk(sf);
  return found;
}

for (const sf of program.getSourceFiles()) {
  if (!own(sf) || !rel(sf.fileName).includes(filter)) continue;
  process.stdout.write(JSON.stringify(factsOf(sf)) + '\n');
}
