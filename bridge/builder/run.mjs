// Headless builder-6 process. Protocol: one JSON request per line on stdin, one JSON reply per line on stdout.
//   {"op":"reset","document":<DocumentJson|null>,"selection":[...]}
//   {"op":"dispatch","command":"element.insert","args":{...}}  -> {"status":"done"|"refused"|..., "message":...}
//   {"op":"canRun"|"refusal","command":...,"args":...}
//   {"op":"state"}      -> {"document":..., "selection":[...]}
//   {"op":"validate","document":...}  {"op":"export","document":...}  {"op":"manifest"}
// Usage: node run.mjs <builder-root>
import path from 'node:path';
import readline from 'node:readline';
import { pathToFileURL } from 'node:url';

const builderRoot = path.resolve(process.argv[2] ?? process.env.BUILDER_ROOT ?? '');
const harnessPath = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), 'harness.ts');
const vite = await import(pathToFileURL(path.join(builderRoot, 'node_modules', 'vite', 'dist', 'node', 'index.js')).href);

const server = await vite.createServer({
  root: builderRoot,
  configFile: false,
  logLevel: 'error',
  appType: 'custom',
  server: { middlewareMode: true, hmr: false, watch: null, fs: { strict: false } },
  optimizeDeps: { noDiscovery: true, include: [] },
  define: { 'import.meta.env.DEV': 'true' },
});
const runner = vite.createServerModuleRunner(server.environments.ssr, { hmr: false });
const h = await runner.import('/@fs/' + harnessPath.replace(/\\/g, '/'));

let store = h.createHeadless();
const out = (obj) => process.stdout.write(JSON.stringify(obj) + '\n');
out({ ready: true });

const rl = readline.createInterface({ input: process.stdin });
for await (const line of rl) {
  if (!line.trim()) continue;
  let req;
  try {
    req = JSON.parse(line);
    switch (req.op) {
      case 'reset':
        store = h.createHeadless(req.document ?? undefined, req.selection ?? []);
        out({ ok: true });
        break;
      case 'dispatch': {
        const r = store.dispatch(req.command, req.args ?? {});
        out(r);
        break;
      }
      case 'canRun':
        out({ ok: store.canRun(req.command, req.args ?? {}) });
        break;
      case 'refusal':
        out({ message: store.refusal(req.command, req.args ?? {}) });
        break;
      case 'state': {
        const s = store.getState();
        out({ document: s.document, selection: s.selection });
        break;
      }
      case 'validate':
        out({ problems: h.validate(req.document ?? store.getState().document, req.selection ?? []) });
        break;
      case 'export': {
        const site = h.exportSite(req.document ?? store.getState().document);
        const files = site.pages.map((p) => ({ path: p.file, text: p.html }));
        files.push({ path: 'css/styles.css', text: site.css });
        if (site.interactions !== null) files.push({ path: 'js/interactions.js', text: site.interactions });
        out({ files });
        break;
      }
      case 'manifest':
        out(h.manifestSummary());
        break;
      case 'close':
        out({ ok: true });
        await server.close();
        process.exit(0);
      default:
        out({ error: `unknown op ${req.op}` });
    }
  } catch (e) {
    out({ error: String(e && e.stack ? e.stack.split('\n').slice(0, 4).join(' | ') : e) });
  }
}
await server.close();
