// Oracle for "every reference to a declaration": TypeScript's own language service (findReferences), which follows
// imports, re-exports and aliases across the whole project. For a deterministic sample of the project's top-level
// declarations, prints one JSON line: {file, pos, refs: [[file, pos, isDefinition], ...]}.
// Usage: node ts_refs.mjs <project-root> <tsconfig> <every-kth>
import path from 'node:path';
import { createRequire } from 'node:module';

const root = path.resolve(process.argv[2]);
const require = createRequire(path.join(root, 'package.json'));
let ts = require('typescript');
if (typeof ts.createLanguageService !== 'function' && process.env.NUCLEO_TS) {
  ts = createRequire(path.join(path.resolve(process.env.NUCLEO_TS), 'package.json'))('typescript');
}
const parsed = ts.getParsedCommandLineOfConfigFile(path.resolve(root, process.argv[3]), {}, { ...ts.sys, onUnRecoverableConfigFileDiagnostic: () => {} });
const every = Number(process.argv[4] ?? 10);
const rel = (f) => path.relative(root, f).split(path.sep).join('/');
const host = {
  getScriptFileNames: () => parsed.fileNames,
  getScriptVersion: () => '1',
  getScriptSnapshot: (f) => (ts.sys.fileExists(f) ? ts.ScriptSnapshot.fromString(ts.sys.readFile(f)) : undefined),
  getCurrentDirectory: () => root,
  getCompilationSettings: () => parsed.options,
  getDefaultLibFileName: (o) => ts.getDefaultLibFilePath(o),
  fileExists: ts.sys.fileExists,
  readFile: ts.sys.readFile,
  readDirectory: ts.sys.readDirectory,
  directoryExists: ts.sys.directoryExists,
  getDirectories: ts.sys.getDirectories,
};
const ls = ts.createLanguageService(host, ts.createDocumentRegistry());
const program = ls.getProgram();
let k = 0;
for (const sf of program.getSourceFiles()) {
  if (sf.isDeclarationFile || sf.fileName.includes('node_modules') || !rel(sf.fileName).startsWith('src/')) continue;
  for (const st of sf.statements) {
    const names = [];
    if ((ts.isFunctionDeclaration(st) || ts.isClassDeclaration(st) || ts.isInterfaceDeclaration(st) || ts.isTypeAliasDeclaration(st) || ts.isEnumDeclaration(st)) && st.name) names.push(st.name);
    if (ts.isVariableStatement(st)) for (const d of st.declarationList.declarations) if (ts.isIdentifier(d.name)) names.push(d.name);
    for (const n of names) {
      if (k++ % every !== 0) continue;
      const refs = [];
      for (const group of ls.findReferences(sf.fileName, n.getStart()) ?? []) {
        for (const r of group.references) refs.push([rel(r.fileName), r.textSpan.start, r.isDefinition === true]);
      }
      process.stdout.write(JSON.stringify({ file: rel(sf.fileName), pos: n.getStart(), name: n.text, refs }) + '\n');
    }
  }
}
