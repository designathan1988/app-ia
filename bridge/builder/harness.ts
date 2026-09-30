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
import { anyCss } from '/src/core/ports/css.ts';
import { createStore } from '/src/core/store/store.ts';
import { siteFiles } from '/src/core/export/export.ts';
import { translate } from '/src/i18n/index.ts';
import { manifest } from '/src/manifest/runtime.ts';
import { initialEditorUi } from '/src/editor/state.ts';
import { INITIAL_PREFERENCES } from '/src/editor/preferences/preferences.ts';
import { activeLayer } from '/src/editor/view/style-state.ts';

export const RULES = rulesFromManifest(manifest.elements, manifest.properties, manifest.html);

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
    css: anyCss,
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
      out.push({ kind: 'added', id: null, parent: parentId, index, type: node.type, name: node.name, tag: node.tag, text: node.text ?? null, styles: node.styles ?? {}, attributes: node.attributes ?? {}, classes: node.classes ?? [] });
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
