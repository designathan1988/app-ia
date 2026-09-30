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

export function createHeadless(document?: DocumentJson, selection: Selection = []) {
  const ids = sequentialIds('ai');
  const initialDoc =
    document ??
    createEmptyDocument(ids, { page: translate('pt-BR', 'pages.defaultHome'), root: translate('pt-BR', 'element.page.label') }, RULES.root);
  const preferences = { ...INITIAL_PREFERENCES, locale: 'pt-BR' as const };
  return createStore({
    table: COMMANDS,
    predicates: PREDICATES,
    commands: new Map(manifest.commands.map((c: any) => [c.id, c])),
    constants: new Map(manifest.interactions.constants.map((c: any) => [c.id, c.value])),
    rules: RULES,
    clock: manualClock(),
    ids,
    words: (_ui: unknown, key: any, params?: any) => translate('pt-BR', key, params),
    layout: noLayout,
    css: anyCss,
    layer: activeLayer,
    initial: { document: initialDoc, selection, ui: initialEditorUi(preferences as any) },
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
