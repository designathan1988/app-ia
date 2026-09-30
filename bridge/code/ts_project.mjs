// Compile a generated TypeScript project with the real compiler (strict), emit it, and optionally run its
// validators on JSON values (the differential test).
//   node ts_project.mjs check <dir>                 -> {"diagnostics": [...]} (and emits to <dir>/out when clean)
//   node ts_project.mjs validate <dir> <values.jsonl> -> one JSON line per value: {entity, errors}
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const ts = createRequire(path.join(path.resolve(process.env.NUCLEO_TS ?? '.'), 'package.json'))('typescript');
const [mode, dirArg, extra] = process.argv.slice(2);
const dir = path.resolve(dirArg);

if (mode === 'check') {
  const parsed = ts.getParsedCommandLineOfConfigFile(path.join(dir, 'tsconfig.json'), {}, { ...ts.sys, onUnRecoverableConfigFileDiagnostic: () => {} });
  const program = ts.createProgram({ rootNames: parsed.fileNames, options: parsed.options });
  const diags = ts.getPreEmitDiagnostics(program).map((d) => {
    const where = d.file ? `${path.relative(dir, d.file.fileName)}:${d.file.getLineAndCharacterOfPosition(d.start ?? 0).line + 1}` : '';
    return `${where} TS${d.code}: ${ts.flattenDiagnosticMessageText(d.messageText, ' ')}`;
  });
  if (diags.length === 0) program.emit();
  process.stdout.write(JSON.stringify({ diagnostics: diags }) + '\n');
} else if (mode === 'validate') {
  const require = createRequire(import.meta.url);
  const { VALIDATORS } = require(path.join(dir, 'out', 'src', 'validate.js'));
  for (const line of fs.readFileSync(extra, 'utf8').split('\n')) {
    if (!line.trim()) continue;
    const { entity, value } = JSON.parse(line);
    process.stdout.write(JSON.stringify({ entity, errors: [...VALIDATORS[entity](value)].sort() }) + '\n');
  }
}
