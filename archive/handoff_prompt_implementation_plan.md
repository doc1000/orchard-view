# Handoff Prompt: Orchard Visual Search — Implementation Plan

## What You Are Being Asked To Do

Produce a detailed, phased implementation plan for rebuilding the state and interaction logic of an existing HTML/JS visual search mockup. The design decisions are fully settled. You are not being asked to revisit them — you are being asked to plan the code work clearly enough that a developer (or coding agent) can execute phase by phase with confidence.

The artifact under discussion is a single self-contained HTML file: `visual_search_mockup.html`. It currently has working UI scaffolding but the views manage their own filtering state independently. The goal is to refactor around a shared state layer so that all views read from and write to one source of truth.

---

## What the Tool Is

A **structured culling interface** for large document corpora organized into hierarchical trees. It is not a keyword search engine. It is an exploration and discernment tool — the user navigates a taxonomy to narrow, filter, and commit to a working set of documents across multiple search cycles.

Three synchronized views — Domain Tree, Function Tree, and Treemap — are lenses on the same underlying document scope. A query bar and per-node / per-document polarity controls all write into a single Decision Ledger. Every view reads its state from that ledger. Views never own independent filtering state.

Design philosophy: **trading interface** — fast, decisive, high contrast, deep taxonomies. Not surgical precision over every edge case. Rapid discernment at scale.

---

## The Five Stores (State Model)

| Store | Description |
|---|---|
| **CORPUS** | Immutable universe. All available documents. Changes only on data load/refresh. |
| **BASE** | Committed selection. Starts as CORPUS. Advances on Go. |
| **DECISION LEDGER** | Ordered, timestamped list of all polarity actions from any view. |
| **WORKING SCOPE** | Derived: `evaluate(BASE, LEDGER)`. Recomputed on every ledger write. |
| **HOPPER** | Independent persistent collection. Survives Go, Undo, and Reset. |

**Core principle:** Views emit decisions into the ledger and render from the derived working scope. Views never own or manage filtering state independently.

---

## Decision Ledger Entry Shape

```json
{
  "ts": 1234567890,
  "source": "query | domain_tree | function_tree | treemap | results_list",
  "target_type": "term | node | document",
  "target_id": "node_id or doc_id or query term string",
  "polarity": "include | exclude | neutral"
}
```

The ledger is evaluated in full on every scope recompute. After Go, the active ledger is cleared and archived as session history (accessible via a dropdown on the Conditions row).

---

## Scope Evaluation Rules

### Precedence hierarchy (most specific wins):
1. **Document decision** — explicit right-click on a result; always wins
2. **Child node decision** — overrides parent broadcast for that subtree
3. **Parent node decision** — broadcasts downward to all descendants
4. **Query inference** — lowest specificity; any explicit node/doc action overrides

### At equal specificity: last timestamp wins.
If Domain includes Health and Function later excludes a doc under Health, that doc is excluded. Recency is the tiebreaker. No hidden priority between trees.

### Broadcast rule:
A polarity decision on a node applies to all descendant nodes and documents. A more-specific child decision overrides the parent broadcast for that child's subtree only.

### Cross-tree:
Domain Tree and Function Tree nodes do not map 1:1. A document can appear under an included Domain node and an excluded Function node. Last timestamp wins. The node count (W/B) in each tree reflects the actual surviving documents accurately.

---

## Query Matching Rules

- **Unquoted term** — fuzzy/token match against document content AND node labels. If a node label matches, the entire branch below that node stays in scope. This is intentional — we are searching structures, not just documents.
- **Quoted phrase** `"exact phrase"` — exact string match on document content only. No branch inheritance from a matching node label.
- **Negative** `-term` or `-"phrase"` — excludes matching docs or branches.
- **OR groups** — terms separated by `or` form separate groups evaluated with OR. Within a group, terms combine as AND.
- After Go: query bar clears. A history dropdown on the query bar preserves prior queries.

---

## Settled Design Decisions

1. **Reset = BASE ← CORPUS.** Not "clear decisions." Undo steps back through the ledger one entry at a time, including past a Go commit (shows "Undo GO?" confirmation beneath the Undo button).

2. **Equal specificity → last timestamp wins.** No hidden tree hierarchy. User is responsible for checking both trees in multi-tree workflows.

3. **Node color = node's own polarity decision, transmitted downward.** No mixed-color nodes, no badges. A green parent with a red child is clear: the child has a more specific decision. Speed and clarity over precision.

4. **No hard/soft inclusion distinction.** A document is in scope or it is not. Node-match branch retention behaves identically to direct document match from a scope membership perspective.

5. **Query bar clears on Go.** History dropdown on query bar preserves prior queries in session order. Conditions row has a dropdown for prior ledger states.

6. **Go is blocked when WORKING SCOPE is empty (0 documents).**

7. **Before Go: empty nodes display red** (shows impact, user can reverse). After Go: empty nodes are hidden.

8. **Hopper is fully independent.** Receives docs from any search cycle. Has its own export/clear controls. Clearing Hopper has zero effect on BASE, WORKING SCOPE, or LEDGER.

9. **Treemap and tree nodes share the same node_id namespace.** A treemap click writes the same ledger entry as the equivalent tree node click.

10. **Full decision provenance is in session ledger history, not in persistent hover UI.** Interface prioritizes fast scanning.

---

## Visual States (Nodes in Trees and Treemap)

| State | Trigger | Color |
|---|---|---|
| Neutral | No active decision, documents in BASE | Default (white/dim) |
| Included | Explicit positive polarity on this node | Green |
| Excluded | Explicit exclusion OR zero documents remain | Red |
| Partial | Some children in scope, some out — shown via W/B count discrepancy | Parent color + count diff |

Node counts display as **W / B** (working count / base count) during the diff stage.

Results list: in-scope docs first, out-of-scope docs below dimmed/red, with a "Show excluded" toggle. Right-click cycles polarity: neutral → include → exclude → neutral.

---

## State Transitions

```
CORPUS
  ↓ session start
BASE  +  DECISION LEDGER  →  evaluate()  →  WORKING SCOPE

WORKING SCOPE  →  GO (commit)  →  BASE = WORKING SCOPE
                                   LEDGER → history
                                   query bar cleared
                                   all views clean slate

UNDO  →  pop last LEDGER entry  →  recompute WORKING SCOPE
         (can undo past Go with "Undo GO?" confirmation)

RESET  →  BASE = CORPUS  ·  LEDGER cleared  ·  HOPPER untouched

WORKING SCOPE docs  →  ADD  →  HOPPER (independent, persistent)
```

---

## Current State of the Mockup

The existing `visual_search_mockup.html` has:
- A working Domain Tree and Function Tree toggle in the left panel
- A Treemap view and Results List view (tab-switched in the right panel)
- A query bar with Parse, Undo, Prune, Reset, scope counter, and Go buttons
- A Conditions row beneath the query bar
- A Hopper strip at the bottom
- Mock document data (~847 simulated documents across a taxonomy)
- **Problem:** Each view currently manages its own filtering. The domain tree, treemap, and results list do not share a single derived scope. Node counts do not match results. Polarity decisions in one view do not propagate to others. Go only accounts for parsed query conditions, not tree polarity decisions.

---

## Acceptance Tests (use these to verify the plan covers each scenario)

**T1 — Parent exclusion with child restoration:** Exclude Health & Wellness → all children red. Include Nutrition & Diet → Nutrition returns, parent shows partial. Press Go → clean slate with correct base.

**T2 — Parent inclusion with child exclusion:** Include Work & Careers → narrows scope. Exclude Finance & Fintech (child) → those docs out even though parent included. All three views match.

**T3 — Cross-tree conflict, last action wins:** Include Domain node containing Doc A. Exclude Function node containing Doc A (newer action) → Doc A excluded. Right-click Doc A in Results to include → Doc A returns (document decision wins). Go → Doc A in committed base.

**T4 — Query + polarity combined commit:** Search fintech, parse. Exclude one matching branch via tree. Include one doc via right-click. Go → committed set reflects all three actions.

**T5 — Exact phrase vs. fuzzy:** `"machine learning"` → only docs containing that literal phrase; node label match does not inherit branch. `machine learning` unquoted → node label match keeps branch.

**T6 — Undo past Go:** Narrow 847→138, Go. Further narrow to 30. Undo repeatedly through ledger. Undo past the Go commit (confirm prompt). Prior 138-doc decisions restored. Hopper intact throughout.

**T7 — Reset:** Narrow to 138, Go. Narrow to 30. Reset → returns to 847 (CORPUS), not 138. Hopper survives.

**T8 — Multi-cycle Hopper:** Add docs from two separate search cycles. Hopper accumulates both sets. Reset. Hopper unchanged. Clear Hopper → no effect on search scope.

**T9 — Zero-result guard:** Create contradictory conditions → 0 docs. Go button disabled. All nodes red. User can still see and remove decisions. Go re-enables when scope > 0.

---

## What the Plan Should Include

1. **Phase breakdown** — logical phases that can be executed and tested independently, with clear entry/exit criteria for each.

2. **Data structures** — concrete JS object/array shapes for CORPUS, BASE, DECISION LEDGER, WORKING SCOPE, and HOPPER. The evaluate() function signature and logic.

3. **Event → ledger wiring** — for each interaction point (tree node click, treemap click, result right-click, query parse, Go, Undo, Reset, Add to Hopper), describe exactly what gets written to the ledger and what triggers a recompute.

4. **View rendering contracts** — what data each view receives from the shared state and what it is responsible for rendering (counts, colors, document lists). Views must not compute scope — they only render it.

5. **Undo stack design** — how to handle pre- and post-Go undo, and how to store ledger snapshots tied to Go commits for the history dropdown.

6. **Query parser** — how to tokenize the query string into ledger entries (OR groups, quoted phrases, negative terms, fuzzy unquoted terms).

7. **Risk flags** — implementation-level risks: performance on recompute with large corpora, event ordering guarantees, any DOM patterns in the existing mockup that will resist refactoring.

8. **Test checkpoints** — map each acceptance test to the phase in which it becomes executable.

The plan should be specific enough that a developer can begin Phase 1 without further design discussion. Design decisions are closed. The only open questions are implementation choices.
