// Normalised shapes of TypeScript statements and expressions, for finding repeated code (clichés).
// Identifiers become positional placeholders (the first distinct name is $0, the next $1, ...), literals become
// their kind, so two fragments that differ only in names and constants get the same shape.
//   node ts_shapes.mjs <project-root> <tsconfig> <min-nodes>
//   -> one JSON line per fragment: {shape, size, file, line, text}
import path from 'node:path';
import { createRequire } from 'node:module';

const root = path.resolve(process.argv[2]);
const require = createRequire(path.join(root, 'package.json'));
let ts = {};
try { ts = require('typescript'); } catch { /* use NUCLEO_TS */ }
if (typeof ts.getParsedCommandLineOfConfigFile !== 'function' && process.env.NUCLEO_TS) {
  ts = createRequire(path.join(path.resolve(process.env.NUCLEO_TS), 'package.json'))('typescript');
}
const parsed = ts.getParsedCommandLineOfConfigFile(path.resolve(root, process.argv[3]), {}, { ...ts.sys, onUnRecoverableConfigFileDiagnostic: () => {} });
const minNodes = Number(process.argv[4] ?? 25);
const rel = (f) => path.relative(root, f).split(path.sep).join('/');

function shapeOf(node) {
  const names = new Map();
  let size = 0;
  const walk = (n) => {
    size++;
    if (ts.isIdentifier(n) || ts.isPrivateIdentifier(n)) {
      if (!names.has(n.text)) names.set(n.text, `$${names.size}`);
      return names.get(n.text);
    }
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) return 'STR';
    if (ts.isNumericLiteral(n)) return 'NUM';
    const kids = [];
    ts.forEachChild(n, (c) => { kids.push(walk(c)); });
    const op = ts.isBinaryExpression(n) ? ts.tokenToString(n.operatorToken.kind) : '';
    return `${ts.SyntaxKind[n.kind]}${op}(${kids.join(',')})`;
  };
  const shape = walk(node);
  return { shape, size };
}

const program = ts.createProgram({ rootNames: parsed.fileNames, options: parsed.options });
for (const sf of program.getSourceFiles()) {
  if (sf.isDeclarationFile || sf.fileName.includes('node_modules') || !rel(sf.fileName).startsWith('src/')) continue;
  const visit = (n) => {
    if (ts.isStatement(n) && !ts.isBlock(n) && !ts.isSourceFile(n) || ts.isArrowFunction(n) || ts.isFunctionExpression(n)) {
      const { shape, size } = shapeOf(n);
      if (size >= minNodes) {
        const line = sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1;
        process.stdout.write(JSON.stringify({ shape, size, file: rel(sf.fileName), line, text: n.getText(sf).slice(0, 160) }) + '\n');
      }
    }
    ts.forEachChild(n, visit);
  };
  visit(sf);
}
