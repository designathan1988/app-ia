// Headless harness for builder-6: the editor's real store, command table, predicates, manifest and model
// rules, with the browser ports replaced by the headless ports the builder's own unit tests use (noLayout,
// anyCss, manualClock, sequentialIds). Nothing of the builder is reimplemented here: the AI plans against
// the editor itself, and every committed state is validated by the editor's own validateDocument.
//
// Loaded through Vite's module runner (run.mjs) so that import.meta.glob in the manifest runtime works.
// Imports are root-relative to the builder checkout.
import { COMMANDS, PREDICATES } from '/src/app/commands.ts';
import { createEmptyDocument, type DocumentJson, type Selection } from '/src/core/document/model.ts';
import { rulesFromManifest, validateDocument } from '/src/core/document/validate.ts';
import { manualClock } from '/src/core/ports/clock.ts';
import { sequentialIds } from '/src/core/ports/ids.ts';
import { noLayout } from '/src/core/ports/layout.ts';
import { lexer as cssLexer } from '/node_modules/css-tree/lib/index.js';
import { createStore } from '/src/core/store/store.ts';
import { siteFiles } from '/src/core/export/export.ts';
import { translate } from '/src/i18n/index.ts';
import { manifest } from '/src/manifest/runtime.ts';
import { initialEditorUi } from '/src/editor/state.ts';
import { INITIAL_PREFERENCES } from '/src/editor/preferences/preferences.ts';
import { activeLayer } from '/src/editor/view/style-state.ts';

export const RULES = rulesFromManifest(manifest.elements, manifest.properties, manifest.html);

// Whether a value is valid for a property, by the CSS grammars of the W3C specifications (css-tree over webref):
// the headless stand-in for the browser's CSS.supports, so a value the browser would refuse is refused here too.
// A property the grammars do not know (custom properties, very new ones) is not blocked.
export const cssGrammar = {
  supports(property: string, value: string): boolean {
    if (property.startsWith('--')) return true;
    try {
      if (!cssLexer.getProperty(property)) return true;
      return cssLexer.matchProperty(property, value).error === null;
    } catch {
      return false;
    }
  },
};

export function createHeadless(document?: DocumentJson, selection: Selection = [], locale: 'en' | 'pt-BR' = 'pt-BR', ui?: unknown) {
  const ids = sequentialIds('ai');
  const initialDoc =
    document ??
    createEmptyDocument(ids, { page: translate(locale, 'pages.defaultHome'), root: translate(locale, 'element.page.label') }, RULES.root);
  const preferences = { ...INITIAL_PREFERENCES, locale };
  return createStore({
    table: COMMANDS,
    predicates: PREDICATES,
    commands: new Map(manifest.commands.map((c: any) => [c.id, c])),
    constants: new Map(manifest.interactions.constants.map((c: any) => [c.id, c.value])),
    rules: RULES,
    clock: manualClock(),
    ids,
    words: (_ui: unknown, key: any, params?: any) => translate(locale, key, params),
    layout: noLayout,
    css: cssGrammar,
    layer: activeLayer,
    initial: { document: initialDoc, selection, ui: ui ?? initialEditorUi(preferences as any) },
    freeze: true, // every committed state deep-frozen and validated, as in development and tests
  } as any);
}

export function manifestSummary() {
  return {
    elements: manifest.elements.elements.map((e: any) => ({ id: e.id, tag: e.tag, content: e.content })),
    commands: manifest.commands.map((c: any) => ({ id: c.id, availability: c.availability?.predicate ?? null })),
    built: Object.entries(COMMANDS).filter(([, h]: any) => h && h.run).map(([id]) => id),
    palette: manifest.elements.palette.flatMap((g: any) => g.entries.map((e: any) => ({ id: e.id, group: g.id, element: e.element ?? null, kind: e.kind }))),
    properties: (manifest.properties.properties ?? []).map((p: any) => p.id),
  };
}

export function validate(document: DocumentJson, selection: Selection = []) {
  return validateDocument(document, selection, RULES);
}

export function exportSite(document: DocumentJson) {
  return siteFiles(document, RULES);
}

export { manifest, translate };
export { applyDiff, matchDocument, parsePath, resolveNode } from '/src/manifest/scenario.ts';

// ---------------------------------------------------------------------------------------------------------------
// Structured difference between two documents (ours, not the builder's): what the planner reasons about.
// Nodes are paired by id; a node of `after` without an id (a node a goal adds) is "added" under its parent.
// The same function describes what a command changed (effect learning) and what a goal still needs (planning), so
// both speak the same vocabulary.
// ---------------------------------------------------------------------------------------------------------------
type Item = Record<string, unknown>;
const NODE_SKIP = new Set(['id', 'children']);
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

function indexNodes(doc: any) {
  const byId = new Map<string, { node: any; parent: string | null; index: number; page: number }>();
  const walk = (node: any, parent: string | null, index: number, page: number) => {
    if (node && typeof node.id === 'string') byId.set(node.id, { node, parent, index, page });
    (node?.children ?? []).forEach((c: any, i: number) => walk(c, node?.id ?? null, i, page));
  };
  (doc?.pages ?? []).forEach((p: any, i: number) => walk(p.tree, null, 0, i));
  return byId;
}

function styleItems(id: string, before: any, after: any, out: Item[]) {
  const b = before ?? {};
  const a = after ?? {};
  for (const bp of new Set([...Object.keys(b), ...Object.keys(a)])) {
    const bs = b[bp] ?? {};
    const as = a[bp] ?? {};
    for (const st of new Set([...Object.keys(bs), ...Object.keys(as)])) {
      const bv = bs[st] ?? {};
      const av = as[st] ?? {};
      for (const prop of new Set([...Object.keys(bv), ...Object.keys(av)])) {
        if (!same(bv[prop], av[prop])) out.push({ kind: 'style', id, breakpoint: bp, state: st, property: prop, value: av[prop] ?? null, current: bv[prop] ?? null });
      }
    }
  }
}

// A goal names nodes by name, not id: a node value without id may be a node that already exists. Pair it with the
// existing node of the same name and type (preferring the same parent) so it reads as moved or changed, not as
// removed and added again. Only a node with no counterpart stays "added".
function pairByName(before: any, after: any): any {
  const bIdx = indexNodes(before);
  const byName = new Map<string, string[]>();
  for (const [id, b] of bIdx) byName.set(b.node.name, [...(byName.get(b.node.name) ?? []), id]);
  const copy = structuredClone(after);
  const used = new Set<string>(indexNodes(copy).keys());
  const walk = (node: any, parentId: string | null) => {
    if (node && typeof node.id !== 'string') {
      const cands = (byName.get(node.name) ?? []).filter((id) => !used.has(id) && bIdx.get(id)!.node.type === node.type);
      const pick = cands.find((id) => bIdx.get(id)!.parent === parentId) ?? (cands.length === 1 ? cands[0] : undefined);
      if (pick !== undefined) {
        node.id = pick;
        used.add(pick);
      }
    }
    const pid = typeof node?.id === 'string' ? node.id : parentId;
    (node?.children ?? []).forEach((c: any) => walk(c, pid));
  };
  (copy?.pages ?? []).forEach((p: any) => walk(p.tree, null));
  return copy;
}

export function diffItems(before: any, goalOrAfter: any): Item[] {
  const after = pairByName(before, goalOrAfter);
  const out: Item[] = [];
  for (const key of new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})])) {
    if (key === 'pages') continue;
    if (!same(before?.[key], after?.[key])) out.push({ kind: 'doc', field: key, value: after?.[key] ?? null, current: before?.[key] ?? null });
  }
  const bp = before?.pages ?? [];
  const ap = after?.pages ?? [];
  const pageMeta = (p: any) => ({ ...p, tree: undefined });
  if (bp.length !== ap.length || bp.some((p: any, i: number) => !same(pageMeta(p), pageMeta(ap[i] ?? {})))) out.push({ kind: 'doc', field: 'pages', value: ap.map(pageMeta), current: bp.map(pageMeta) });
  const bIdx = indexNodes(before);
  const aIdx = indexNodes(after);
  for (const [id, b] of bIdx) if (!aIdx.has(id)) out.push({ kind: 'removed', id, parent: b.parent, type: b.node.type });
  for (const [id, a] of aIdx) {
    const b = bIdx.get(id);
    if (!b) {
      out.push({ kind: 'added', id, parent: a.parent, index: a.index, type: a.node.type, name: a.node.name, tag: a.node.tag, text: a.node.text ?? null });
      continue;
    }
    if (b.parent !== a.parent || b.index !== a.index) {
      const siblingsSame = b.parent === a.parent;
      out.push({ kind: siblingsSame ? 'reordered' : 'moved', id, parent: a.parent, index: a.index, from: b.parent });
    }
    for (const key of new Set([...Object.keys(b.node), ...Object.keys(a.node)])) {
      if (NODE_SKIP.has(key) || same(b.node[key], a.node[key])) continue;
      if (key === 'styles') styleItems(id, b.node.styles, a.node.styles, out);
      else out.push({ kind: 'field', id, field: key, value: a.node[key] ?? null, current: b.node[key] ?? null });
    }
  }
  // nodes of `after` with no id: added by a goal, under the nearest parent that has one
  const walkNew = (node: any, parentId: string | null, index: number) => {
    if (node && typeof node.id !== 'string') {
      const { children: _c, ...fields } = node;
      out.push({ kind: 'added', id: null, parent: parentId, index, type: node.type, name: node.name, tag: node.tag, text: node.text ?? null, styles: node.styles ?? {}, attributes: node.attributes ?? {}, classes: node.classes ?? [], node: fields });
    }
    const pid = typeof node?.id === 'string' ? node.id : parentId;
    (node?.children ?? []).forEach((c: any, i: number) => walkNew(c, pid, i));
  };
  (after?.pages ?? []).forEach((p: any) => walkNew(p.tree, null, 0));
  return out;
}

// the vocabulary of effects: which kinds of change an item is
export function itemFields(items: Item[]): string[] {
  const f = new Set<string>();
  for (const it of items) {
    if (it.kind === 'doc') f.add(`doc:${String(it.field)}`);
    else if (it.kind === 'style') {
      f.add('node:styles');
      f.add(`style:${String(it.property)}`);
    } else if (it.kind === 'field') f.add(`node:${String(it.field)}`);
    else f.add(`node:${String(it.kind)}`);
  }
  return [...f].sort();
}

// Graded distance to a goal: one per leaf still to change (each style property, attribute, class, text), so a step
// that achieves part of what an item needs counts as progress. The builder's matchDocument still decides success.
const leaves = (v: unknown): number => {
  if (v === null || v === undefined) return 0;
  if (Array.isArray(v)) return v.reduce((n: number, x) => n + Math.max(1, leaves(x)), 0);
  if (typeof v === 'object') return Object.values(v as object).reduce((n: number, x) => n + Math.max(1, leaves(x)), 0);
  return 1;
};
const keyDiff = (a: any, b: any): number => {
  if (!a || !b || typeof a !== 'object' || typeof b !== 'object' || Array.isArray(a) || Array.isArray(b)) return 1;
  let n = 0;
  for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) if (!same(a[k], b[k])) n += 1;
  return Math.max(n, 1);
};
export function distance(items: Item[]): number {
  let n = 0;
  for (const it of items) {
    if (it.kind === 'added') n += 1 + leaves(it.styles) + leaves(it.attributes) + leaves(it.classes) + (it.text != null ? 1 : 0);
    else if (it.kind === 'field') n += keyDiff(it.value, it.current);
    else n += 1;
  }
  return n;
}

// ---------------------------------------------------------------------------------------------------------------
// Goals as constraints (what language understanding produces): the same item vocabulary as diffItems, checked
// against a document. "added" is judged relative to the start document (a node that did not exist then).
// ---------------------------------------------------------------------------------------------------------------
export function satisfied(item: any, doc: any, start: any): boolean {
  const now = indexNodes(doc);
  const before = indexNodes(start);
  const node = typeof item.id === 'string' ? now.get(item.id) : undefined;
  switch (item.kind) {
    case 'style':
      return !!node && (node.node.styles?.[item.breakpoint]?.[item.state]?.[item.property] ?? null) === item.value;
    case 'field': {
      if (!node) return false;
      const v = node.node[item.field];
      if (item.value && typeof item.value === 'object' && !Array.isArray(item.value)) {
        return !!v && Object.entries(item.value).every(([k, x]) => same(v[k], x));
      }
      return same(v, item.value);
    }
    case 'removed':
      return !now.has(item.id);
    case 'moved':
    case 'reordered':
      return !!node && node.parent === item.parent && (item.index === undefined || item.index === null || node.index === item.index);
    case 'added':
      return addedMatch(item, doc, start)?.missing.length === 0;
    default:
      return false;
  }
}

// The new node that best realises an "added" constraint: right type and place, with the extra fields it still lacks
// (text, name). null when no new node of that type is in that place.
const ADDED_EXTRAS = ['text', 'name'];
export function addedMatch(item: any, doc: any, start: any): { id: string; missing: string[] } | null {
  const now = indexNodes(doc);
  const before = indexNodes(start);
  let best: { id: string; missing: string[] } | null = null;
  for (const [id, n] of now) {
    if (before.has(id)) continue;
    if (item.type && n.node.type !== item.type) continue;
    if (item.parent && n.parent !== item.parent) continue;
    if (item.index !== undefined && item.index !== null && n.index !== item.index) continue;
    const missing = ADDED_EXTRAS.filter((f) => item[f] !== undefined && item[f] !== null && n.node[f] !== item[f]);
    if (!best || missing.length < best.missing.length) best = { id, missing };
  }
  return best;
}

// Graded distance of a constraint: 0 when it holds; for "added", the extras still missing on the new node, or
// 1 + all extras when the node is not there yet.
export function constraintDistance(item: any, doc: any, start: any): number {
  if (item.kind !== 'added') return satisfied(item, doc, start) ? 0 : 1;
  const m = addedMatch(item, doc, start);
  const extras = ADDED_EXTRAS.filter((f) => item[f] !== undefined && item[f] !== null).length;
  return m ? m.missing.length : 1 + extras;
}

// What is still needed, as items the planner can act on: an "added" node that exists but lacks its text or name
// becomes field items on that very node.
export function pendingItems(items: any[], doc: any, start: any): any[] {
  const out: any[] = [];
  for (const it of items) {
    if (it.kind === 'added') {
      const m = addedMatch(it, doc, start);
      if (m && m.missing.length === 0) continue;
      if (m) for (const f of m.missing) out.push({ kind: 'field', id: m.id, field: f, value: it[f] });
      else out.push(it);
    } else if (!satisfied(it, doc, start)) out.push(it);
  }
  return out;
}

// ---------------------------------------------------------------------------------------------------------------
// Inertia (the frame axiom): what a request does not mention must stay as it was. Every change between the start
// document and the current one that no constraint accounts for is collateral, and counts against the plan.
// ---------------------------------------------------------------------------------------------------------------
function ancestors(idx: Map<string, { parent: string | null }>, id: string): string[] {
  const out: string[] = [];
  for (let p = idx.get(id)?.parent ?? null; p; p = idx.get(p)?.parent ?? null) out.push(p);
  return out;
}

export function collateral(constraints: any[], start: any, doc: any): any[] {
  const before = indexNodes(start);
  const now = indexNodes(doc);
  const removedTargets = new Set(constraints.filter((c) => c.kind === 'removed').map((c) => c.id));
  const movedTargets = new Set(constraints.filter((c) => c.kind === 'moved' || c.kind === 'reordered').map((c) => c.id));
  const styleKeys = new Set(constraints.filter((c) => c.kind === 'style').map((c) => `${c.id}|${c.breakpoint}|${c.state}|${c.property}`));
  const fieldKeys = new Set(constraints.filter((c) => c.kind === 'field').map((c) => `${c.id}|${c.field}`));
  const addedMatches = constraints.filter((c) => c.kind === 'added').map((c) => addedMatch(c, doc, start)?.id).filter((x) => x);
  const newIds = new Set<string>();
  for (const id of addedMatches as string[]) {
    newIds.add(id);
    for (const [nid] of now) if (!before.has(nid) && ancestors(now, nid).includes(id)) newIds.add(nid);
  }
  // parents whose children may legitimately shift: where something was added, removed or moved
  const touchedParents = new Set<string>();
  for (const id of newIds) touchedParents.add(now.get(id)?.parent ?? '');
  for (const id of removedTargets) touchedParents.add(before.get(id)?.parent ?? '');
  for (const id of movedTargets) {
    touchedParents.add(before.get(id)?.parent ?? '');
    touchedParents.add(now.get(id)?.parent ?? '');
  }
  const out: any[] = [];
  for (const it of diffItems(start, doc)) {
    const id = it.id as string | null;
    switch (it.kind) {
      case 'removed':
        if (removedTargets.has(id) || ancestors(before, id as string).some((a) => removedTargets.has(a))) continue;
        break;
      case 'added':
        if (id && newIds.has(id)) continue;
        break;
      case 'moved':
        if (movedTargets.has(id)) continue;
        break;
      case 'reordered':
        if (movedTargets.has(id) || touchedParents.has(it.parent as string)) continue;
        break;
      case 'style':
        if (styleKeys.has(`${id}|${it.breakpoint}|${it.state}|${it.property}`)) continue;
        if (id && newIds.has(id)) continue;
        break;
      case 'field':
        if (fieldKeys.has(`${id}|${it.field}`) || (id && newIds.has(id))) continue;
        break;
      default:
        break;
    }
    out.push(it);
  }
  return out;
}
