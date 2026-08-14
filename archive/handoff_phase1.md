# Handoff Prompt — Phase 1: Data Model Foundation

## Your Task

Implement Phase 1 of the implementation plan for `visual_search_mockup.html`. Phase 1 is
purely a data model layer — no visual changes, no CSS changes, no UI behavior changes. The
file should look and behave identically to the user; Phase 1 only adds the new stores and
computation functions that later phases will wire up.

---

## Read These Files First

1. `C:\Users\doste\Claude\Projects\Orchard\implementation_plan.md` — the full plan. Phase 1
   is the authoritative spec for your work. Read it before writing any code.

2. `C:\Users\doste\Claude\Projects\Orchard\visual_search_mockup.html` — the file you will
   edit. Read the entire JavaScript section to understand what currently exists.

Do not read any other files. Do not create any new files.

---

## Scope of Phase 1

Implement exactly the following, in order:

### 1. Fix Document Schema (Section 1.1)

- Add the `FN_MAP` constant (full table is in the plan) above the `ORIGINAL_DOCS` array
- Rename `cluster` → `domCluster` in every entry in `ORIGINAL_DOCS` and add `fnCluster`
  using `FN_MAP[doc.domCluster]`
- Update `generateDocs()` to assign `domCluster` (was `cluster`) and `fnCluster` via
  `FN_MAP[node.id] ?? "fn-d-dest"`
- Remove the `generateDocs(FUNCTION_TREE, new Set())` call from the DOCS assembly — docs
  exist once in CORPUS and map to both trees via `domCluster` / `fnCluster`
- Update `ORIGINAL_CLUSTERS` to use `d.domCluster` instead of `d.cluster`
- Add startup validation: `validateFnMap()` (logs a console warning for any missing entries)

### 2. Pre-compute Ancestor Paths (Section 1.2)

- Add `pathToNode(tree, targetId, path)` — returns array of node IDs from root to target
- Add `DOC_PATHS` as a module-level `Map`
- Add `buildDocPaths(docs)` — populates `DOC_PATHS` with `{ domPath, fnPath }` per doc
- Add `NODE_LABELS` as a module-level `Map`
- Add `buildNodeLabels(tree)` — populates `NODE_LABELS` with `nodeId → label.toLowerCase()`
- Call both builders after DOCS is assembled

### 3. Define the Five Stores (Section 1.3)

Add these module-level variables after the existing `S = {...}` block (do not remove `S` yet):

```js
const CORPUS = [...DOCS]; // snapshot after DOCS is built
let BASE = [...CORPUS];
let LEDGER = [];
let WORKING_SCOPE = [...BASE];
const HOPPER = new Set();
let UNDO_STACK = [];
let SESSION_HISTORY = [];
```

### 4. Write `evaluate()` and `resolveDoc()` (Section 1.4)

- Add `evaluate(base, ledger)` — filters base by calling `resolveDoc` per doc
- Add `resolveDoc(doc, ledger)` — returns `"include"`, `"exclude"`, or `"neutral"`
  using the precedence logic in the plan (document > node depth > query > timestamp)
- Stub `termMatchesDoc()` to always return `false` for now (Phase 5 provides the real impl)

### 5. Write `writeLedger()` and `recompute()` (Section 1.5)

- Add `writeLedger(entry)` — pushes `{ ts: Date.now(), ...entry }` onto `LEDGER`, calls
  `recompute()`
- Add `recompute()` — sets `WORKING_SCOPE = evaluate(BASE, LEDGER)`, calls `renderAll()`

Do not yet wire any UI actions to `writeLedger`. That is Phase 2.

---

## What NOT to Change

- Do not touch any CSS
- Do not change any HTML structure
- Do not modify any existing render functions (`renderSidebar`, `renderTreemap`, `renderList`, etc.)
- Do not remove or alter `S`, `snap()`, `undo()`, `executeSearch()`, or `decompose()` —
  those are replaced in Phase 2 and 3, not Phase 1
- Do not change the existing `DOMAIN_TREE` or `FUNCTION_TREE` data structures
- The file must still load and function identically to the user after your changes

---

## Exit Criteria

After your changes, open the file in a browser and run these in the console to verify:

```js
// Verify stores exist
console.log(CORPUS.length);        // should be ~110-130 (original + domain placeholders only, no function duplicates)
console.log(WORKING_SCOPE.length); // same as CORPUS.length

// Verify doc paths were built
const p = DOC_PATHS.get(DOCS[0].id);
console.log(p.domPath);  // e.g. ["root", "travel", "travel-beach", "t-b-carib"]
console.log(p.fnPath);   // e.g. ["root", "fn-discover", "fn-d-places", "fn-d-dest"]

// Verify evaluate() works
writeLedger({ source:"domain_tree", target_type:"node", target_id:"health", polarity:"exclude" });
console.log(WORKING_SCOPE.length); // should drop by ~health docs count

writeLedger({ source:"domain_tree", target_type:"node", target_id:"h-nutrition", polarity:"include" });
console.log(WORKING_SCOPE.length); // should recover the nutrition docs

// Verify LEDGER has entries
console.log(LEDGER.length); // 2

// Verify existing UI still works
// (reload page — tree, treemap, and chips should function as before)
```

If any console assertion fails, debug before finishing. The existing UI must continue to
work; Phase 1 is additive only.

---

## Workspace

- Edit in place: `C:\Users\doste\Claude\Projects\Orchard\visual_search_mockup.html`
- All changes go into that single file
- When done, present the file to the user
