# Orchard Visual Search — Implementation Plan

## Overview

This plan refactors `visual_search_mockup.html` from per-view filtering state to a shared
Decision Ledger architecture. Six phases, each independently testable. Design decisions are
closed — this document covers only implementation choices.

---

## Existing Code: What to Keep, What to Replace

**Keep:**
- All CSS (no changes)
- `DOMAIN_TREE` and `FUNCTION_TREE` data structures
- D3 treemap layout and SVG rendering machinery
- Drag handle, tooltip, preview panel, hopper UI
- `renderTreemap()`, `renderSidebar()`, `renderList()` DOM scaffolding
- `collapseAll()`, `setView()`, `openPreview()`, `closePreview()`

**Replace entirely:**
- `S` state object → split into named stores (`BASE`, `LEDGER`, `WORKING_SCOPE`, `HOPPER`)
- `snap()` / `undo()` → `UNDO_STACK` with typed entries
- `updateDocCount()` → derived from `WORKING_SCOPE.length`
- `executeSearch()` → `go()`
- `decompose()` → `parseQuery()` with a real tokenizer
- `updateHighlights()` → computed inside `evaluate()` via ledger
- `S.nodeStates` → replaced by ledger entries of `target_type: "node"`
- `S.chips` → replaced by ledger entries of `target_type: "term"`
- `S.fillData` → recomputed from `WORKING_SCOPE` after every `evaluate()`
- `CHIP_REL` and `QUERY_PARSE` hardcoded maps → real parser + term-to-node index

**Modify:**
- `DOCS` — add `fnCluster` field to every doc; remove the separate `generateDocs(FUNCTION_TREE, ...)` call
- `generateDocs()` — takes `DOMAIN_TREE` only; assigns `fnCluster` via a mapping table
- `renderSidebar()` — reads node polarity from ledger, counts from `WORKING_SCOPE`
- `renderTreemap()` — reads node polarity from ledger, counts from `WORKING_SCOPE`
- `renderList()` — shows in-scope docs first; out-of-scope docs below (dimmed) with toggle

---

## Phase 1 — Data Model Foundation

**Goal:** Establish the five stores and the `evaluate()` function. No UI changes yet.

**Entry:** Working mockup (current state).  
**Exit:** `evaluate(BASE, LEDGER)` returns a correct doc array you can verify via console.

---

### 1.1 — Fix Document Schema

Every doc needs a `domCluster` (domain tree leaf ID, was `cluster`) and `fnCluster`
(function tree leaf ID). Since the corpus is one set of documents viewed through two trees,
remove the separate `generateDocs(FUNCTION_TREE, ...)` call entirely.

Add a `FN_MAP` table mapping each domain leaf ID to a function tree leaf ID:

```js
const FN_MAP = {
  // Travel → Place Discovery / Trip Planning
  "t-b-carib":  "fn-d-dest",
  "t-b-pac":    "fn-a-t-log",
  "t-b-med":    "fn-d-dest",
  "t-m-rock":   "fn-a-t-log",
  "t-m-alps":   "fn-a-t-log",
  "t-m-asia":   "fn-a-t-acc",
  "t-u-eu":     "fn-d-local",
  "t-u-asia":   "fn-d-local",
  "t-u-us":     "fn-d-local",
  // Work → Career Decisions / Decision Support
  "w-t-ml":     "fn-de-c-role",
  "w-t-eng":    "fn-de-c-role",
  "w-t-data":   "fn-de-c-co",
  "w-f-bank":   "fn-a-w-fin",
  "w-f-fin":    "fn-de-c-co",
  "w-f-crypto": "fn-d-market",
  "w-d-ux":     "fn-de-c-role",
  "w-d-brand":  "fn-de-b-prod",
  // Health → Life & Wellness / Learning
  "h-f-str":    "fn-l-l-body",
  "h-f-card":   "fn-l-l-body",
  "h-n-plant":  "fn-l-l-body",
  "h-n-perf":   "fn-l-l-body",
  "h-m-stress": "fn-l-l-mind",
  "h-m-sleep":  "fn-l-l-mind",
  // Research → Technical Learning
  "r-ml-repr":  "fn-l-t-ml",
  "r-ml-gen":   "fn-l-t-ml",
  "r-ml-agent": "fn-l-t-ml",
  "r-b-gen":    "fn-l-t-bio",
  "r-b-drug":   "fn-l-t-bio",
  "r-s-econ":   "fn-d-market",
  "r-s-cog":    "fn-l-l-mind",
  // Products → Purchase Decisions
  "p-f-men":    "fn-de-b-prod",
  "p-f-women":  "fn-de-b-prod",
  "p-t-wear":   "fn-de-b-prod",
  "p-t-audio":  "fn-de-b-prod",
  "p-fd-art":   "fn-de-b-serv",
  "p-fd-hlth":  "fn-de-b-serv",
  // Culture → Inspiration
  "c-a-film":   "fn-i-a-vis",
  "c-a-music":  "fn-i-a-mus",
  "c-p-env":    "fn-i-s-env",
  "c-p-tech":   "fn-i-s-pol",
};
```

Update `generateDocs()` to assign both fields:
```js
docs.push({
  id: nextId++,
  title: ...,
  domCluster: node.id,          // was: cluster
  fnCluster: FN_MAP[node.id] ?? "fn-d-dest",  // fallback
  path: pathStr,
  body: bodies[i](node, parentLabel),
});
```

Update `ORIGINAL_DOCS` to rename `cluster` → `domCluster` and add `fnCluster` using `FN_MAP`.

---

### 1.2 — Pre-compute Ancestor Paths

At startup, after building CORPUS, compute ancestor arrays for every doc. This avoids
re-traversing the trees inside `evaluate()` on every call.

```js
// Returns array of node IDs from root to `targetId` (inclusive), or null if not found
function pathToNode(tree, targetId, path = []) {
  const current = [...path, tree.id];
  if (tree.id === targetId) return current;
  for (const child of (tree.children || [])) {
    const found = pathToNode(child, targetId, current);
    if (found) return found;
  }
  return null;
}

// Precomputed per doc: { domPath: string[], fnPath: string[] }
// Index position = depth (0 = root, last = leaf)
const DOC_PATHS = new Map();  // doc.id → { domPath, fnPath }

function buildDocPaths(docs) {
  for (const doc of docs) {
    DOC_PATHS.set(doc.id, {
      domPath: pathToNode(DOMAIN_TREE, doc.domCluster) ?? [],
      fnPath:  pathToNode(FUNCTION_TREE, doc.fnCluster) ?? [],
    });
  }
}
```

Call `buildDocPaths(CORPUS)` once after CORPUS is assembled.

---

### 1.3 — Define the Five Stores

```js
// CORPUS: immutable after load
const CORPUS = [...ORIGINAL_DOCS, ...generateDocs(DOMAIN_TREE, ORIGINAL_CLUSTERS)];

// BASE: committed selection; starts as CORPUS
let BASE = [...CORPUS];

// LEDGER: ordered array of decision entries
// Shape: { ts, source, target_type, target_id, polarity }
let LEDGER = [];

// WORKING_SCOPE: derived; recomputed on every ledger write
let WORKING_SCOPE = [...BASE];

// HOPPER: persistent independent collection
// Stored as a Set of doc IDs to survive Go/Undo/Reset
const HOPPER = new Set();

// UNDO_STACK: typed entries for undo
let UNDO_STACK = [];

// SESSION_HISTORY: archived ledger states (one per Go)
let SESSION_HISTORY = [];
// Entry shape: { label: string, ledger: LedgerEntry[], base: Doc[] }
```

---

### 1.4 — Write `evaluate(base, ledger)`

This is the core computation. It runs on every ledger write.

```js
function evaluate(base, ledger) {
  return base.filter(doc => resolveDoc(doc, ledger) !== "exclude");
}

// Returns "include", "exclude", or "neutral" (neutral = in scope)
function resolveDoc(doc, ledger) {
  const paths = DOC_PATHS.get(doc.id);
  if (!paths) return "neutral";

  // Track the winning decision: { specificity, ts, polarity }
  let winner = null;

  for (const entry of ledger) {
    let specificity = -1;

    if (entry.target_type === "document") {
      if (String(doc.id) === String(entry.target_id)) {
        specificity = 999; // always wins
      }

    } else if (entry.target_type === "node") {
      // Check both trees; specificity = depth index in path
      const domIdx = paths.domPath.indexOf(entry.target_id);
      const fnIdx  = paths.fnPath.indexOf(entry.target_id);
      const idx = Math.max(domIdx, fnIdx); // one or both may be -1
      if (idx >= 0) specificity = idx;

    } else if (entry.target_type === "term") {
      if (termMatchesDoc(entry.target_id, doc)) {
        specificity = 0; // lowest
      }
    }

    if (specificity < 0) continue;

    const beats =
      !winner ||
      specificity > winner.specificity ||
      (specificity === winner.specificity && entry.ts > winner.ts);

    if (beats) {
      winner = { specificity, ts: entry.ts, polarity: entry.polarity };
    }
  }

  return winner ? winner.polarity : "neutral";
}
```

**`termMatchesDoc(termId, doc)` — Phase 5 provides the full implementation.** For now, stub
it as always returning false (query term decisions have no effect until Phase 5).

---

### 1.5 — `recompute()` and `writeLedger()`

These are the two functions everything else calls.

```js
function writeLedger(entry) {
  LEDGER.push({ ts: Date.now(), ...entry });
  recompute();
}

function recompute() {
  WORKING_SCOPE = evaluate(BASE, LEDGER);
  renderAll();
}
```

`renderAll()` calls the same render functions as the existing code — they will be updated
in Phase 3 to read from `WORKING_SCOPE` instead of per-view state.

---

### Phase 1 Test Checkpoint

Open browser console. After loading:
```js
writeLedger({ source:"domain_tree", target_type:"node", target_id:"health", polarity:"exclude" });
console.log(WORKING_SCOPE.length); // should be 847 - 134 = 713

writeLedger({ source:"domain_tree", target_type:"node", target_id:"h-nutrition", polarity:"include" });
console.log(WORKING_SCOPE.length); // should restore the 44 nutrition docs → ~757
```

No UI update needed yet; verify via console only.

---

## Phase 2 — Ledger Write Layer (Wiring Actions)

**Goal:** Every user interaction that currently mutates `S.nodeStates`, `S.chips`, etc.
instead calls `writeLedger()`. `recompute()` runs after each write.

**Entry:** Phase 1 complete (stores and evaluate() working).  
**Exit:** All interaction points write to ledger. UI may be partially broken — that's fine
until Phase 3 fixes the render contracts.

---

### 2.1 — Node Click / Right-click (Sidebar and Treemap)

Replace every `S.nodeStates[node.id] = ...` pattern.

Current cycle in `renderTreeNodes` (left-click toggles pos; right-click cycles):
```js
// LEFT CLICK: was toggle pos; new behavior = cycle neutral → include → exclude → neutral
// RIGHT CLICK: same cycle (matches design spec "right-click cycles polarity")
```

New cycle: `neutral → include → exclude → neutral`.

```js
function cycleNodePolarity(nodeId, source) {
  // Find the current effective polarity for this node from the ledger
  const current = getNodeLedgerPolarity(nodeId);
  const next = current === "neutral"  ? "include"
              : current === "include" ? "exclude"
              : "neutral";

  // Push to undo stack before writing
  UNDO_STACK.push({ type: "ledger_pop" });

  writeLedger({
    source,
    target_type: "node",
    target_id: nodeId,
    polarity: next,
  });
}

// Returns the polarity of the most recent ledger entry for this exact node
// (not considering propagation — just what was explicitly set on this node)
function getNodeLedgerPolarity(nodeId) {
  for (let i = LEDGER.length - 1; i >= 0; i--) {
    if (LEDGER[i].target_type === "node" && LEDGER[i].target_id === nodeId) {
      return LEDGER[i].polarity;
    }
  }
  return "neutral";
}
```

Replace the existing `row.addEventListener("click", ...)` and `row.addEventListener("contextmenu", ...)`
bodies with calls to `cycleNodePolarity(node.id, "domain_tree")` (or `"function_tree"`).

Do the same for treemap's `g.on("contextmenu", ...)`. Treemap uses the same `cycleNodePolarity`
with source `"treemap"`.

**Remove `snap()` calls from these handlers.** Undo is now at ledger-entry granularity.

---

### 2.2 — Document Right-click (Results List)

Right-click on a result item cycles polarity at the document level:

```js
function cycleDocPolarity(docId) {
  const current = getDocLedgerPolarity(docId);
  const next = current === "neutral"  ? "include"
              : current === "include" ? "exclude"
              : "neutral";

  UNDO_STACK.push({ type: "ledger_pop" });

  writeLedger({
    source: "results_list",
    target_type: "document",
    target_id: String(docId),
    polarity: next,
  });
}

function getDocLedgerPolarity(docId) {
  for (let i = LEDGER.length - 1; i >= 0; i--) {
    const e = LEDGER[i];
    if (e.target_type === "document" && String(e.target_id) === String(docId)) {
      return e.polarity;
    }
  }
  return "neutral";
}
```

Wire: in `renderList()`, add `item.addEventListener("contextmenu", e => { e.preventDefault(); cycleDocPolarity(doc.id); })`.

---

### 2.3 — Go

```js
function go() {
  if (WORKING_SCOPE.length === 0) return; // blocked when scope = 0

  // Archive current state for session history
  SESSION_HISTORY.push({
    label: `Cycle ${SESSION_HISTORY.length + 1} — ${BASE.length} → ${WORKING_SCOPE.length} docs`,
    ledger: [...LEDGER],
    base:   [...BASE],
  });

  // Push to undo stack so we can undo past Go
  UNDO_STACK.push({
    type:     "go_commit",
    prevBase: [...BASE],
    prevLedger: [...LEDGER],
  });

  BASE          = [...WORKING_SCOPE];
  LEDGER        = [];
  WORKING_SCOPE = [...BASE];

  document.getElementById("searchInput").value = "";
  updateGoButton();
  recompute();
  setStatus(`Committed — ${BASE.length} docs now base`);
}
```

---

### 2.4 — Undo

```js
function undo() {
  if (!UNDO_STACK.length) { setStatus("Nothing to undo"); return; }

  const action = UNDO_STACK[UNDO_STACK.length - 1]; // peek first

  if (action.type === "go_commit") {
    // Show confirmation before undoing a Go commit
    if (!action.confirmed) {
      action.confirmed = true;
      setStatus("Undo GO? Press Undo again to confirm.");
      return;
    }
    // Confirmed: restore
    UNDO_STACK.pop();
    BASE   = action.prevBase;
    LEDGER = action.prevLedger;
    SESSION_HISTORY.pop();

  } else if (action.type === "ledger_pop") {
    UNDO_STACK.pop();
    LEDGER.pop(); // remove the most recent ledger entry
  }

  recompute();
  setStatus("Undone");
}
```

Note: `action.confirmed` is a runtime flag on the stack entry object; it is not persisted.

---

### 2.5 — Reset

```js
function resetAll() {
  UNDO_STACK.push({
    type: "go_commit",
    prevBase: [...BASE],
    prevLedger: [...LEDGER],
  });
  BASE          = [...CORPUS];
  LEDGER        = [];
  WORKING_SCOPE = [...BASE];
  // HOPPER intentionally untouched
  document.getElementById("searchInput").value = "";
  recompute();
  setStatus("Reset to full corpus");
}
```

---

### 2.6 — Add to Hopper

```js
function addToHopper(docId) {
  HOPPER.add(docId);
  renderHopper();
}

function removeFromHopper(docId) {
  HOPPER.delete(docId);
  renderHopper();
}

function toggleHopperDoc(docId) {
  if (HOPPER.has(docId)) removeFromHopper(docId);
  else addToHopper(docId);
  renderList(); // refresh hopper-btn state in list
}
```

Hopper operations do NOT touch LEDGER, BASE, or WORKING_SCOPE.

---

### Phase 2 Test Checkpoint

- Click a domain tree node → `LEDGER.length` increments by 1; `WORKING_SCOPE.length` changes
- Click same node again → `LEDGER.length = 2`; scope reverses
- Press Undo → `LEDGER.length = 1`; scope reverts
- Press Go → `LEDGER = []`; `BASE.length` = prior `WORKING_SCOPE.length`; `SESSION_HISTORY.length = 1`
- Press Undo after Go → confirmation message; Undo again → `BASE` restores
- Press Reset → `BASE.length = 847`; `LEDGER = []`

---

## Phase 3 — View Rendering Contracts

**Goal:** All views read exclusively from `WORKING_SCOPE`, `LEDGER`, and `BASE`. No view
computes scope independently.

**Entry:** Phase 2 complete (ledger writes working).  
**Exit:** All three views (sidebar, treemap, results list) are consistent; counts match.

---

### 3.1 — Shared Node Color Resolution

Both the sidebar and treemap need to determine each node's display color. This is a pure
function of the ledger — it reads the node's own polarity decision (if any), independent
of what it broadcasts to descendants.

```js
// Returns "include" | "exclude" | "neutral" for display on the node itself
function getNodeDisplayPolarity(nodeId) {
  return getNodeLedgerPolarity(nodeId); // defined in Phase 2
}
```

Node color mapping:
- `"include"` → green (`pos-selected` class / `var(--green)`)
- `"exclude"` → red (`neg-selected` class / `var(--red)`)
- `"neutral"` but has query term highlighting → use `S.highlighted` (legacy) or compute from ledger term entries
- `"neutral"` with no highlight → default

For the pre-Go "empty nodes display red" rule: after resolving color, check if the node's
subtree has zero docs in WORKING_SCOPE. If yes and before Go, override display to red.

```js
function nodeWorkingCount(nodeId) {
  // Count WORKING_SCOPE docs whose domPath or fnPath includes this node
  return WORKING_SCOPE.filter(doc => {
    const p = DOC_PATHS.get(doc.id);
    return p && (p.domPath.includes(nodeId) || p.fnPath.includes(nodeId));
  }).length;
}

function nodeBaseCount(nodeId) {
  return BASE.filter(doc => {
    const p = DOC_PATHS.get(doc.id);
    return p && (p.domPath.includes(nodeId) || p.fnPath.includes(nodeId));
  }).length;
}
```

**Performance note:** These iterate WORKING_SCOPE per node. For 847 docs and ~60 nodes,
this is ~50K iterations per renderAll. Acceptable in-browser. If it lags, precompute a
`Map<nodeId, count>` inside `recompute()` and read from that. See Risk Flags.

---

### 3.2 — Sidebar Rendering Contract

`renderSidebar()` receives no arguments. It reads from:
- `LEDGER` → node polarity (via `getNodeDisplayPolarity`)
- `WORKING_SCOPE` + `BASE` → W/B counts per node (via `nodeWorkingCount`, `nodeBaseCount`)

Count display format:
- Before Go: show `W / B` when they differ (partial); show `W` when they match
- After Go (`LEDGER.length === 0` and initial state): show `W` only

Row CSS class rules (replace existing `pos-selected` / `neg-selected` / `highlight-*`):
```
getNodeDisplayPolarity(nodeId) === "include" → "pos-selected"
getNodeDisplayPolarity(nodeId) === "exclude" → "neg-selected"
nodeWorkingCount(nodeId) === 0 && goNotYetPressed → "neg-selected" (red for empty)
// query highlighting still applies when polarity === "neutral"
```

The existing `S.highlighted` and `S.nodeStates` references in `renderTreeNodes` are
replaced by the above.

---

### 3.3 — Treemap Rendering Contract

`renderTreemap()` reads from:
- `LEDGER` → node polarity (via `getNodeDisplayPolarity`)
- `WORKING_SCOPE` → tile sizing and W/B counts

Tile area should reflect the number of docs in scope for that node, not the static
`node.count`. Update the `d3.hierarchy` sum:

```js
const root = d3.hierarchy(focusNode)
  .sum(d => {
    if (!d.children || !d.children.length) {
      return Math.max(nodeWorkingCount(d.id), 0.5); // 0.5 keeps tile visible at 0 docs
    }
    return 0;
  })
  .sort((a, b) => b.value - a.value);
```

Node color: use `getNodeDisplayPolarity` as in the sidebar.

Before-Go zero-count tiles display red (same rule as sidebar). After Go (on clean-slate
render), empty tiles are hidden — set their sum to 0 and D3 will omit them.

Count label in tile: show `W / B` when W !== B; show `W` when equal.

---

### 3.4 — Results List Rendering Contract

`renderList()` reads from:
- `WORKING_SCOPE` → in-scope documents (render first, normal style)
- `BASE` minus `WORKING_SCOPE` → out-of-scope documents (render below, dimmed/red, hidden by default)
- `LEDGER` → per-doc polarity for right-click indicator

```js
function renderList() {
  const inScope  = WORKING_SCOPE;
  const outIds   = new Set(WORKING_SCOPE.map(d => d.id));
  const outScope = BASE.filter(d => !outIds.has(d.id));

  // ... render inScope items normally
  // ... render outScope items with class "result-item excluded" (dimmed, red border)
  //     only if showExcluded toggle is on
}
```

Add a "Show excluded (N)" toggle button to the list header. Clicking it toggles a
local boolean `showExcluded`. This is the only local state a view is allowed to hold.

Right-click indicator on result items: show a small colored dot based on `getDocLedgerPolarity(doc.id)`.

---

### 3.5 — Doc Count Badge and Go Button

```js
function updateHeader() {
  document.getElementById("activeCount").textContent = WORKING_SCOPE.length;
  const goBtn = document.getElementById("goBtn");
  goBtn.disabled = WORKING_SCOPE.length === 0;
  goBtn.classList.toggle("btn-go-disabled", WORKING_SCOPE.length === 0);
}
```

Add `.btn-go-disabled { opacity: 0.4; cursor: not-allowed; }` to CSS.

Call `updateHeader()` at the end of `recompute()`.

---

### Phase 3 Test Checkpoint (covers T1, T2, T9)

**T1:** Exclude `health` → sidebar shows all health children red; treemap health region red;
counts show W=0/B=134 on health node. Include `h-nutrition` → parent shows green+count diff;
all three views match. Go → clean slate; health and nutrition nodes hidden from treemap.

**T2:** Include `work` → treemap/sidebar green. Exclude `work-finance` → that node red in
both views; doc count drops by 73. All three views show same count.

**T9:** Create contradictory conditions producing 0 docs → `activeCount` shows 0; Go button
grayed out and disabled; all nodes red.

---

## Phase 4 — Go, Undo, and Session History UI

**Goal:** Wire the Go button disable state, Undo confirmation UI, and the session history
dropdown on the Conditions row.

**Entry:** Phase 3 complete.  
**Exit:** Acceptance tests T6, T7, T8 pass.

---

### 4.1 — Undo Confirmation UI

When the user presses Undo and the top of `UNDO_STACK` is a `go_commit`:
- Display a small confirmation label beneath the Undo button: `"Undo GO? Press again to confirm"`
- A second press with `action.confirmed = true` executes the undo

Implementation: add a `<div id="undoConfirm" style="display:none; ...">Undo GO? Press again to confirm</div>`
beneath the header toolbar. Show/hide it based on `action.confirmed` state.

Clear the confirmation if any other action is taken (any ledger write resets it).

---

### 4.2 — Session History Dropdown

Add a `<select id="historySelect">` to the right side of the chip tray (Conditions row).

Populate on each Go:
```js
function updateHistoryDropdown() {
  const sel = document.getElementById("historySelect");
  sel.innerHTML = `<option value="">History ▾</option>`;
  SESSION_HISTORY.forEach((h, i) => {
    const opt = document.createElement("option");
    opt.value = i;
    opt.textContent = h.label;
    sel.appendChild(opt);
  });
}
```

On `change`, show a read-only overlay displaying the archived ledger entries for that
cycle. Do not restore it — this is provenance display only, not a restore action.

---

### 4.3 — Query Bar History Dropdown

Add a `<datalist id="queryHistory">` linked to the search input, populated with prior
queries on each Go:

```js
let QUERY_HISTORY = [];
// In go(): QUERY_HISTORY.push(document.getElementById("searchInput").value.trim());
// Then update <datalist> with QUERY_HISTORY entries
```

---

### Phase 4 Test Checkpoints (T6, T7, T8)

**T6:** Narrow 847→138, Go. Narrow to 30. Undo → 31 → 32 ... back through ledger entries.
Undo past Go → confirmation prompt. Confirm → back to 138-doc base. `HOPPER` unchanged.

**T7:** Narrow to 138, Go. Narrow to 30. Reset → `BASE = CORPUS`; `WORKING_SCOPE.length = 847`. Hopper unchanged.

**T8:** Add docs from two cycles. Clear Hopper → `HOPPER.clear()`. `WORKING_SCOPE` unchanged.

---

## Phase 5 — Query Parser

**Goal:** Replace the hardcoded `CHIP_REL` / `QUERY_PARSE` maps with a real tokenizer
that writes ledger entries for query terms.

**Entry:** Phase 4 complete.  
**Exit:** Acceptance tests T4 and T5 pass.

---

### 5.1 — Tokenizer

Input: raw query string from `searchInput`.

```
Grammar:
  query      = group (OR group)*
  group      = term+
  term       = [-]? (quoted | unquoted)
  quoted     = '"' .* '"'
  unquoted   = non-whitespace token
  OR         = case-insensitive literal "or"
```

```js
function tokenize(query) {
  const tokens = [];
  const re = /(-?"[^"]*"|-?\S+)/g;
  let m;
  while ((m = re.exec(query)) !== null) {
    const raw = m[1];
    const neg = raw.startsWith("-");
    const inner = neg ? raw.slice(1) : raw;
    const quoted = inner.startsWith('"') && inner.endsWith('"');
    const term = quoted ? inner.slice(1, -1) : inner.toLowerCase();
    tokens.push({ term, neg, quoted });
  }
  return tokens;
}
```

---

### 5.2 — OR Group Splitting

Split token list on the literal token `"or"` (case-insensitive, unquoted):

```js
function splitOrGroups(tokens) {
  const groups = [[]];
  for (const tok of tokens) {
    if (!tok.neg && !tok.quoted && tok.term === "or") {
      groups.push([]);
    } else {
      groups[groups.length - 1].push(tok);
    }
  }
  return groups.filter(g => g.length > 0);
}
```

Within each OR group, terms combine as AND. Groups combine as OR.

---

### 5.3 — Write Parsed Tokens to Ledger

```js
function parseQuery() {
  const raw = document.getElementById("searchInput").value.trim();
  if (!raw) return;

  QUERY_HISTORY.push(raw);
  const tokens = tokenize(raw);
  const groups = splitOrGroups(tokens);

  // Each token becomes a ledger entry
  // OR groups are encoded as a group_id field on each entry
  const groupId = Date.now();
  let idx = 0;
  for (const group of groups) {
    for (const tok of group) {
      UNDO_STACK.push({ type: "ledger_pop" });
      writeLedger({
        source:      "query",
        target_type: "term",
        target_id:   tok.term,
        polarity:    tok.neg ? "exclude" : "include",
        quoted:      tok.quoted,  // extra field — not in base schema but stored
        group_id:    groupId + idx,  // same group_id = AND; diff = OR
      });
      idx++;
    }
  }
}
```

Note: `group_id` is an extension to the base ledger schema. Store it; `evaluate()` uses
it to implement OR logic.

---

### 5.4 — `termMatchesDoc(termId, doc, quoted)`

```js
function termMatchesDoc(termId, doc, quoted = false) {
  const body  = doc.body.toLowerCase();
  const title = doc.title.toLowerCase();
  const term  = termId.toLowerCase();

  if (quoted) {
    // Exact string match on content only — no node label inheritance
    return body.includes(term) || title.includes(term);
  } else {
    // Fuzzy: match body/title OR node label match triggers branch inheritance
    if (body.includes(term) || title.includes(term)) return true;
    // Node label match: check if any ancestor node label contains the term
    const paths = DOC_PATHS.get(doc.id);
    if (!paths) return false;
    return nodeLabelsContainTerm([...paths.domPath, ...paths.fnPath], term);
  }
}

// Build a Map<nodeId, label.toLowerCase()> at startup for fast lookup
const NODE_LABELS = new Map();
function buildNodeLabels(tree) {
  NODE_LABELS.set(tree.id, tree.label.toLowerCase());
  for (const child of (tree.children || [])) buildNodeLabels(child);
}
// Call: buildNodeLabels(DOMAIN_TREE); buildNodeLabels(FUNCTION_TREE);

function nodeLabelsContainTerm(nodeIds, term) {
  return nodeIds.some(id => NODE_LABELS.get(id)?.includes(term));
}
```

---

### 5.5 — OR Group Evaluation in `resolveDoc`

The `evaluate()` / `resolveDoc()` logic from Phase 1 handles each ledger entry individually.
For OR groups, we need to modify the term matching:

A doc matches an OR group if it matches ANY term within that group (AND within group → must
match ALL of that group's include terms).

Simplest implementation: group term entries by `group_id`. Evaluate each group independently.
A doc is excluded if it fails to match any include group (when include groups are present)
or matches any exclude term.

```js
// Inside evaluate(), before the per-doc loop:
const termEntries = ledger.filter(e => e.target_type === "term");
const orGroups = groupBy(termEntries, e => e.group_id);

// For a given doc, compute whether it passes term filters
function docPassesTermFilter(doc, orGroups) {
  const includeGroups = [...orGroups.values()].filter(g => g.some(e => e.polarity === "include"));
  const excludeTerms  = [...orGroups.values()].flat().filter(e => e.polarity === "exclude");

  // Exclusions: any matching exclude term removes the doc
  for (const e of excludeTerms) {
    if (termMatchesDoc(e.target_id, doc, e.quoted)) return false;
  }

  // Inclusions: doc must match at least one OR group
  if (includeGroups.length === 0) return true; // no include filter
  return includeGroups.some(group =>
    group.filter(e => e.polarity === "include")
         .every(e => termMatchesDoc(e.target_id, doc, e.quoted))
  );
}
```

Integrate `docPassesTermFilter` into `resolveDoc()`: if the doc fails the term filter,
treat it as if a `"term"` ledger entry with polarity `"exclude"` and specificity 0 applies.
Node and document decisions can still override this (their specificity ≥ 1 or 999).

---

### Phase 5 Test Checkpoint (T4, T5)

**T4:** Type `fintech`, parse. Exclude `w-f-bank` via tree. Include doc ID 3 via right-click.
Go → WORKING_SCOPE contains fintech docs minus banking branch, plus doc 3 explicitly.
`LEDGER` now empty. `BASE.length` = that working set size.

**T5:** `"machine learning"` → only docs with that literal phrase in body/title; node `r-ml`
label match does NOT add docs without the phrase. `machine learning` (unquoted) → node
`r-ml` label match brings its full branch in scope.

---

## Phase 6 — Polish and Final Wiring

**Goal:** Remaining edge cases, chip tray as ledger display, final cross-tree verification.

---

### 6.1 — Chip Tray as Ledger Summary

The chip tray (Conditions row) should display the current active ledger entries. Replace
the chip rendering with a function that reads from `LEDGER`:

Each `target_type: "term"` entry → renders as a chip with the term and polarity style.
Each `target_type: "node"` entry → renders as a chip with the node label.
Each `target_type: "document"` entry → renders as a chip with doc title (truncated).

Chips remain clickable to remove the corresponding ledger entry (which triggers a recompute).

```js
function renderChips() {
  // ... build chip for each ledger entry
  // clicking the × on a chip removes that entry from LEDGER by ts
  // and pushes a "ledger_remove_by_ts" entry onto UNDO_STACK
}
```

---

### 6.2 — Cross-tree Consistency Check (T3)

This acceptance test requires a doc to appear in results under both trees. Verify:

1. Load a doc that maps to both `work-tech` (domain) and `fn-de-career` (function).
2. Include `work` domain node (timestamp T1).
3. Exclude `fn-de-career` function node (timestamp T2 > T1).
4. Verify doc is excluded (T2 > T1 at equal specificity 2).
5. Right-click doc in results → include (document decision, specificity 999).
6. Verify doc is included regardless of tree decisions.
7. Go → doc in BASE.

If step 4 fails, the DOC_PATHS fnPath is not wired to the function tree correctly.
Check `DOC_PATHS.get(docId).fnPath` includes the function node IDs.

---

### 6.3 — Before-Go vs. After-Go Node Display

Tracked via a simple flag:

```js
let LAST_GO_AT = null; // null = never; Date = last Go timestamp

// In go(): LAST_GO_AT = Date.now();

// In node color resolution:
function isBeforeFirstGo() { return LAST_GO_AT === null; }
```

Actually the spec is per-cycle: "before Go: empty nodes red; after Go: empty nodes hidden."

After a Go, the LEDGER is empty and WORKING_SCOPE = BASE. An empty node at this point means
it was empty in BASE too (which would be very unusual). In practice: after Go, no nodes are
empty because the committed scope is the working scope. Nodes with zero docs in WORKING_SCOPE
appear only when the user is actively filtering.

Implementation: in node count display, check `nodeWorkingCount(nodeId) === 0`.
If true and `LEDGER.length > 0` → display red.
If true and `LEDGER.length === 0` → hide the node (only relevant in treemap tiles; sidebar always shows structure).

---

### 6.4 — Prune Button

Prune hides excluded nodes from the sidebar (existing behavior via `S.pruned`). In the
new model, this reads from `getNodeDisplayPolarity`:

```js
function renderTreeNodes(nodes, depth, container) {
  for (const node of nodes) {
    const polarity = getNodeDisplayPolarity(node.id);
    if (STATE.pruned && polarity === "exclude") continue;
    // ... rest of render
  }
}
```

`STATE.pruned` is a simple boolean in a small UI state object (the only surviving local
state flag, along with `showExcluded` and `hopperOpen`).

---

### 6.5 — Status Bar

Keep as-is. Update `statusMsg` text in each operation as before.

---

## Acceptance Test → Phase Map

| Test | First Executable In |
|------|---------------------|
| T1 — Parent exclusion, child restoration | Phase 3 |
| T2 — Parent inclusion, child exclusion | Phase 3 |
| T3 — Cross-tree conflict, last action wins | Phase 6 (needs fnCluster from Phase 1 + cross-tree eval from Phase 1) |
| T4 — Query + polarity combined commit | Phase 5 |
| T5 — Exact phrase vs. fuzzy | Phase 5 |
| T6 — Undo past Go | Phase 4 |
| T7 — Reset returns to CORPUS | Phase 2 |
| T8 — Multi-cycle Hopper | Phase 2 (Hopper) + Phase 4 (multi-cycle) |
| T9 — Zero-result guard | Phase 3 |

---

## Data Structure Quick Reference

```
CORPUS          Doc[]           Immutable after load. Never changes.
BASE            Doc[]           Committed selection. Starts = CORPUS. Advances on Go.
LEDGER          Entry[]         Ordered by timestamp. Cleared on Go (archived to history).
WORKING_SCOPE   Doc[]           Derived. evaluate(BASE, LEDGER). Recomputed on every ledger write.
HOPPER          Set<docId>      Persistent. Never cleared by Go/Undo/Reset.
UNDO_STACK      UndoEntry[]     Typed: "ledger_pop" | "go_commit".
SESSION_HISTORY HistoryEntry[]  One entry per Go. For the dropdown on Conditions row.
DOC_PATHS       Map<id,Paths>   Precomputed. { domPath: string[], fnPath: string[] }.
NODE_LABELS     Map<id,string>  Precomputed. nodeId → label.toLowerCase(). For term matching.
```

---

## Risk Flags

### RF-1 — `nodeWorkingCount` Performance

`nodeWorkingCount(nodeId)` iterates `WORKING_SCOPE` once per node per render. With 60 nodes
and 847 docs, `renderAll()` does ~50K array element checks. This is fast. However, if corpus
grows to 10K+ docs or node count grows substantially, precompute a `Map<nodeId, number>`
inside `recompute()` before calling `renderAll()`:

```js
function buildCountCache() {
  const cache = new Map();
  for (const doc of WORKING_SCOPE) {
    const p = DOC_PATHS.get(doc.id);
    if (!p) continue;
    for (const id of [...p.domPath, ...p.fnPath]) {
      cache.set(id, (cache.get(id) ?? 0) + 1);
    }
  }
  return cache;
}
```

Pass `countCache` to render functions instead of calling `nodeWorkingCount` per-node.

---

### RF-2 — `evaluate()` Replay Cost

`evaluate()` replays the full LEDGER for every doc on every ledger write. With 847 docs and
a ledger of 10–30 entries, this is ~25K iterations per keypress — negligible. If ledger
grows to hundreds of entries in a long session, consider caching the last evaluate result
and only re-evaluating docs whose affected node IDs appear in the newly added entry.

Not needed for initial implementation.

---

### RF-3 — Same Node ID Across Trees

The spec says treemap and tree nodes share one namespace. Currently, domain and function tree
node IDs are already disjoint (`travel` vs. `fn-discover`). Verify no collisions before
writing the ledger: a `cycleNodePolarity` call must correctly identify which tree a node
belongs to, to set the `source` field.

Add a lookup set at startup:
```js
const DOMAIN_NODE_IDS = new Set();
const FUNCTION_NODE_IDS = new Set();
function collectIds(tree, set) { set.add(tree.id); for (const c of tree.children||[]) collectIds(c, set); }
collectIds(DOMAIN_TREE, DOMAIN_NODE_IDS);
collectIds(FUNCTION_TREE, FUNCTION_NODE_IDS);

// In cycleNodePolarity:
const source = DOMAIN_NODE_IDS.has(nodeId)   ? "domain_tree"
             : FUNCTION_NODE_IDS.has(nodeId) ? "function_tree"
             : "treemap"; // treemap can host either
```

---

### RF-4 — D3 Treemap Tile Area After Scope Change

The treemap currently sizes tiles by `node.count` (static). After Phase 3, tiles are sized
by `nodeWorkingCount`. When scope shrinks, tiles shrink proportionally — this is correct
behavior. Verify that D3's treemap layout handles the case where all leaf values sum to 0
(all docs excluded) without crashing. Guard with `Math.max(value, 0.1)` in the sum function
to keep tiles visible at zero count (shown as tiny slivers, colored red).

---

### RF-5 — FnCluster Coverage

`FN_MAP` must cover every domain leaf node ID. If a leaf is missing from `FN_MAP`, its docs
will have `fnCluster = undefined`, causing `pathToNode(FUNCTION_TREE, undefined)` to return
null and the doc to have an empty `fnPath`. This means function-tree node decisions will
never affect those docs.

At startup, validate:
```js
function validateFnMap() {
  function leaves(node, acc=[]) {
    if (!node.children?.length) { acc.push(node.id); return acc; }
    for (const c of node.children) leaves(c, acc);
    return acc;
  }
  const missing = leaves(DOMAIN_TREE).filter(id => !FN_MAP[id]);
  if (missing.length) console.warn("Missing FN_MAP entries:", missing);
}
```

---

### RF-6 — Quoted Field in Ledger Schema

The base spec ledger schema does not include a `quoted` field. The Phase 5 tokenizer adds
it as an extension. This is fine for a single-file implementation — just document it. If
ledger entries are ever serialized to JSON for external consumption, the schema will need
to be versioned.

---

### RF-7 — Existing `S` Object Dependencies

The current code has many functions that read directly from `S.nodeStates`, `S.chips`, etc.
The safest refactor strategy is:

1. Add the new stores (`BASE`, `LEDGER`, etc.) alongside `S` first (Phase 1).
2. Replace `S.nodeStates` writes with `writeLedger()` (Phase 2) while keeping `S.nodeStates` reads working temporarily.
3. Replace `S.nodeStates` reads in render functions (Phase 3) with ledger-derived calls.
4. Delete `S.nodeStates`, `S.chips`, `S.highlighted`, `S.results`, `S.executed`, `S.fillData` from `S` (Phase 3 exit).

This avoids breaking the whole file in one commit.

---

## Execution Order Summary

| Phase | What Changes | Key Function Added/Changed |
|-------|-------------|---------------------------|
| 1 | Data model: stores, paths, evaluate() | `evaluate()`, `resolveDoc()`, `writeLedger()`, `recompute()` |
| 2 | Ledger writes for all interactions | `cycleNodePolarity()`, `cycleDocPolarity()`, `go()`, `undo()`, `resetAll()` |
| 3 | Views read from WORKING_SCOPE | `renderSidebar()`, `renderTreemap()`, `renderList()`, `updateHeader()` |
| 4 | Go/Undo UI, history dropdown | `updateHistoryDropdown()`, undo confirmation UI |
| 5 | Real query parser | `tokenize()`, `splitOrGroups()`, `termMatchesDoc()`, `parseQuery()` |
| 6 | Polish: chip tray as ledger, cross-tree T3, empty node display | `renderChips()` refactor |

Each phase ends in a testable state. A developer can commit after each phase.
