// Headless builder-6 process. Protocol: one JSON request per line on stdin, one JSON reply per line on stdout.
//   {"op":"reset","document":<DocumentJson|null>,"selection":[...]}
//   {"op":"dispatch","command":"element.insert","args":{...}}  -> {"status":"done"|"refused"|..., "message":...}
//   {"op":"canRun"|"refusal","command":...,"args":...}
//   {"op":"state"}      -> {"document":..., "selection":[...]}
//   {"op":"validate","document":...}  {"op":"export","document":...}  {"op":"manifest"}
//   {"op":"setup","document":...,"selection":["/Page/Hero"],"locale":"en","breakpoint":"desktop","state":"base"} -> {"state":0}
//   {"op":"goal","document":<fixture>,"diff":[...]}  -> {"ok":true} (the goal is the fixture with the diff applied)
//   {"op":"try","state":k,"candidates":[{"command","args"}],"keep":bool}
//        -> per candidate {"status","message","mismatches","problems","state"?}: the command run on a fresh copy of
//           saved state k, compared with the goal by the builder's own matchDocument
//   {"op":"stateOf","state":k} {"op":"forget","keep":[k...]}
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
// saved states for planning: id -> {parent, action}. A state is the path of actions from the setup, and is restored
// by replaying that path on a fresh store: the clock is manual and ids are sequential, so the replay is exact and
// keeps what a snapshot would lose (the undo history).
let saved = new Map();
let nextState = 0;
let goal = null;
let setupReq = null;
const pathOf = (id) => {
  const out = [];
  for (let k = id; k !== null; k = saved.get(k).parent) {
    if (!saved.has(k)) throw new Error(`estado inexistente ${k}`);
    if (saved.get(k).action) out.push(saved.get(k).action);
  }
  return out.reverse();
};
const base = () => {
  const req = setupReq;
  const doc = req.document ?? undefined;
  const sel = doc ? (req.selection ?? []).map((p) => idOfPath(doc, p)) : [];
  const st = h.createHeadless(doc, sel, req.locale ?? 'pt-BR');
  if (req.breakpoint && req.breakpoint !== 'desktop') st.dispatch('view.setBreakpoint', { breakpoint: req.breakpoint });
  if (req.state && req.state !== 'base') st.dispatch('view.setStyleState', { state: req.state });
  return st;
};
// an action is one dispatch, or {"sequence":[...]}: several, stopping at the first that does not run
const run = (st, action) => {
  if (Array.isArray(action.sequence)) {
    let r = { status: 'done' };
    for (const a of action.sequence) {
      r = run(st, a);
      if (r.status !== 'done') return r;
    }
    return r;
  }
  const args = resolveArgs(st.getState().document, action.args ?? {});
  let r = st.dispatch(action.command, args);
  if (r.status === 'confirm') r = { ...st.answer(true), confirmed: true };
  return r;
};
const restore = (id) => {
  const st = base();
  for (const a of pathOf(id)) run(st, a);
  return st;
};
const save = (parent, action) => {
  const id = nextState++;
  saved.set(id, { parent, action });
  return id;
};
// {"$node": "/Page/Hero"} anywhere in the arguments stands for that node's id in the current document
const resolveArgs = (doc, value) => {
  if (Array.isArray(value)) return value.map((v) => resolveArgs(doc, v));
  if (value && typeof value === 'object') {
    if (typeof value.$node === 'string' && Object.keys(value).length === 1) return idOfPath(doc, value.$node);
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, resolveArgs(doc, v)]));
  }
  return value;
};
const idOfPath = (doc, path) => {
  const r = h.resolveNode(doc, h.parsePath(path).nodes);
  if (typeof r === 'string') throw new Error(`seleção ${path}: ${r}`);
  return r.node.id;
};
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
      case 'setup': {
        setupReq = req;
        saved = new Map();
        nextState = 0;
        const st = base();
        out({ state: save(null, null), selection: st.getState().selection });
        break;
      }
      case 'goal': {
        const r = h.applyDiff(req.document, req.diff);
        if (r.error) throw new Error(`diff: ${JSON.stringify(r.error)}`);
        goal = r.document;
        out({ ok: true });
        break;
      }
      case 'try': {
        const results = [];
        const before = restore(req.state).getState();
        for (const c of req.candidates) {
          const st = restore(req.state);
          let r;
          try {
            r = run(st, c);
          } catch (e) {
            results.push({ status: 'error', message: String(e).slice(0, 300) });
            continue;
          }
          const now = st.getState();
          const res = { status: r.status, message: r.message ?? null };
          if (goal) {
            res.mismatches = h.matchDocument(now.document, goal).length;
            res.distance = h.distance(h.diffItems(now.document, goal));
          }
          res.problems = h.validate(now.document, now.selection).length;
          res.changed = now.document !== before.document;
          if (r.confirmed) res.confirmed = true;
          if (req.fields && res.changed !== undefined) res.fields = h.itemFields(h.diffItems(before.document, now.document));
          if (req.keep && r.status === 'done') res.state = save(req.state, c);
          results.push(res);
        }
        out({ results });
        break;
      }
      case 'goalDiff': {
        // what the goal still needs from saved state k, as structured items (the planner's reasoning material)
        const st = restore(req.state).getState();
        const items = h.diffItems(st.document, goal);
        out({ items, fields: h.itemFields(items), selection: st.selection, mismatches: h.matchDocument(st.document, goal).length, distance: h.distance(items) });
        break;
      }
      case 'stateOf': {
        const st = restore(req.state).getState();
        out({ document: st.document, selection: st.selection, undoSteps: st.history.past?.length ?? null,
              mismatches: goal ? h.matchDocument(st.document, goal) : null, plan: pathOf(req.state) });
        break;
      }
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
