# Visual Search Frontend — Design Synopsis

**Project:** Orchard Visual Search Interface  
**Date:** 2026-07-28  
**Status:** Pre-implementation — design record and mockup phase  

---

## Overview

This document captures the intended design and behavior of the visual search frontend for the Orchard hierarchical clustering system. The backend pipeline — which converts a corpus into one or more hierarchical tree-z arrays with labelled/enriched leaf and internal nodes — is already built. This frontend is the runtime retrieval and exploration layer.

The core promise: all heavy LLM and compute work is frontloaded at index time. At runtime, constructing a fully labelled cluster tree of arbitrary width and depth is a fast, low-latency operation. The interface exploits this to make exploration feel instantaneous.

---

## System Architecture Context

**What feeds the frontend:**
- One or more hierarchical tree-z arrays (the "orchard artifact")
- Each node has: label, semantic embedding centroid, child pointers, document membership list, enrichment metadata
- Tree cuts can be made at any depth/width target with no additional LLM calls

**What the frontend does:**
- Renders the cluster tree visually
- Accepts natural language or structured search input
- Decomposes queries into explicit, editable search conditions
- Uses conditions to highlight the tree before executing retrieval
- Executes a tree subselection (Steiner tree over remaining space) on demand
- Returns a narrowed cluster tree + flat document list

---

## Interface Layout

```
┌──────────────────────────────────────────────────────┐
│  [Search Bar]                          [Reset] [Go]  │
├──────────────────────────────────────────────────────┤
│  Search Condition Chips                              │
│  [vacation spots ✓] [NOT maui ✗] ["beach" ✓] ...    │
├──────────────────────────────────────────────────────┤
│  Cluster Tree (hierarchical block navigation)        │
│                                                      │
│  Level 1 (leftmost column):                         │
│  [Travel] [Work] [Health] [Finance] ...             │
│                                                      │
│  Level 2 (expands right when L1 selected):          │
│  [Destinations] [Logistics] [Accommodation] ...     │
│                                                      │
│  Level 3...                                         │
│                                                      │
├──────────────────────────────────────────────────────┤
│  Results (flat list, post-Execute)                  │
│  Doc 1 | Doc 2 | Doc 3 ...                          │
└──────────────────────────────────────────────────────┘
```

---

## Component Specifications

### 1. Search Bar

**Location:** Top of interface  
**Input modes:**
- Natural language: `"beach vacation spots not Hawaii in August"`
- Google-style syntax: `"beach" vacation -maui after:2024-08-01 before:2024-08-14`
- Additive: successive queries append to the condition set (not replace)

**On submit behavior:**
1. Query is sent to a decomposition step (lightweight LLM or rule-based parser)
2. Decomposed into structured conditions (see Condition Chips below)
3. Chips appear; tree lights up — **results do NOT immediately appear**
4. User reviews highlights and conditions before executing

**Controls:**
- `[Reset]` — clears all conditions, returns tree to neutral state
- `[Go / Execute]` — triggers retrieval and renders narrowed tree + results

---

### 2. Search Condition Chips

**Location:** Below search bar  
**Purpose:** Make the implicit search surface explicit and editable

Each chip represents one parsed search condition, e.g.:
- `vacation spots` (inclusive, broad match)
- `NOT maui` (exclusive)
- `"beach"` (exact match)
- `after:2024-08-01` (date filter)
- `between $200–$500` (range)

**Chip behavior:**
- Click chip to toggle active/inactive (inactive = grayed out, excluded from search)
- Each chip shows its type via color/icon: positive (green/+), negative (red/–), date (blue), exact (outlined)
- Chips are additive across multiple search submissions
- A `[–]` button removes a chip entirely
- `[Reverse]` button inverts the polarity of a selected chip (inclusive ↔ exclusive)

**Design note:** This is the explicit contract between user intent and search execution. The user should never have to wonder why results appeared or didn't.

---

### 3. Cluster Tree — Hierarchical Block Navigation

**Location:** Main body of interface  
**Visualization style:** Vertical columns expanding left-to-right (like a breadcrumb that fans out)

**Structure:**
- Level 1 labels appear as a vertical stack of labeled blocks on the left
- Selecting a block highlights it, dims others, and expands Level 2 in the next column to the right
- Each subsequent selection adds a column; previously selected columns remain visible (collapsed to label + highlight)
- Deselecting a level collapses all levels to its right

**Selection modes per node:**
- **Positive select** (click): include this cluster in search space — highlights green
- **Negative select** (right-click or shift-click): exclude this cluster — highlights red, visually collapsed/faded
- **Neutral** (default): no selection, included by default

**Tree highlighting from search conditions:**
- When chips are active (before Execute), the tree lights up to show which nodes are in-scope
- Positive conditions light up relevant nodes green
- Negative conditions dim/red relevant nodes
- Strength of highlight could reflect relevance confidence (lighter = weaker match)
- This provides spatial context: *where in the taxonomy are my answers coming from?*

**Navigation:**
- Click any previously selected block to backtrack to that level
- Backtracking collapses all levels to the right
- Horizontal scroll if many levels are open

**Default visualization:** Vertical column blocks with labels (not D3 circles/treemap). Rationale: labels are always readable, navigation is linear and reversible, and the column metaphor maps naturally to tree depth.

**Alternative visualizations to support later:**
- D3 packed circles (beautiful, weak labels)
- Treemap (compact, irregular shapes)
- Icicle (top-down, good for density)

**Design note:** All three alternatives are compatible with the same JSON artifact. The column block view is the default because it handles label readability and progressive disclosure most cleanly.

---

### 4. Execute / Go Button

**Location:** Top right (also accessible after tree interaction)  
**Trigger:** User clicks after reviewing highlighted tree and active chips  
**Behavior:**
1. Computes Steiner tree over the remaining selected/non-excluded nodes
2. Retrieves documents within that subspace
3. Renders a narrowed cluster tree (same block column format, now showing only the selected subspace)
4. Populates flat document list below

**Design note:** The two-step flow (highlight → execute) is intentional. It forces a moment of review and prevents reflexive, opaque search behavior. The user sees *where* results will come from before committing.

---

### 5. Flat Results List

**Location:** Below cluster tree, post-Execute  
**Contents:** Documents/items that fall within the selected cluster subspace, ranked by relevance to active positive conditions  
**Each result shows:** Title, source cluster path (breadcrumb), snippet or descriptor  
**Behavior:** Clicking a result highlights its home node in the cluster tree  

---

## Key Design Principles

1. **Show the space before the results.** The tree is not decoration — it is the primary navigation artifact. Search highlights the space; Execute retrieves from it.

2. **Explicit over implicit.** Every active search condition is a visible, togglable chip. The user always knows what constraints are active.

3. **Additive and reversible.** Queries accumulate; the Reverse button flips polarity; clicking a chip deactivates it. Nothing is permanent until Execute.

4. **Positive and negative selection.** Both inclusive and exclusive selections are first-class. Negative selection removes nodes from the visible/searchable space, not just deprioritizes them.

5. **Low latency.** Because the tree artifact is pre-built, all tree operations (narrowing, subselection, re-rendering) are runtime-fast. No LLM calls needed for navigation.

6. **Generative answers are deferred.** The interface is about finding and exploring. A "generate summary" action can be layered on top later with one button.

---

## Comparison to Alternative Data Systems

| | Orchard Visual Search | Relational DB | Graph DB |
|---|---|---|---|
| Schema rigidity | None at index time | Strict columns | Schema-light |
| Retrieval flexibility | Moderate (tree-structured) | High (SQL) | Very high |
| Runtime speed | Fast (pre-built tree) | Very fast (indexed) | Moderate |
| Label maintenance | Auto-extracted | Manual columns | Mixed |
| Visual navigation | Native | Requires tooling | Requires tooling |
| Best for | Soft taxonomies, exploration, visual search over modest corpora | Structured records, reporting | Relationship-heavy queries |

**Target use case:** Individual users or small teams doing discovery and exploration over a corpus of 100–100k documents or product descriptions, where the categories are soft (fashion, travel, jobs, research papers) and the user doesn't know exactly what they're looking for.

---

## Open Questions / Deferred Decisions

- [ ] How to handle multiple trees (e.g., domain tree + function tree) in parallel? Show side by side? Layer as overlays?
- [ ] Should negative selections completely remove nodes from the tree display, or just fade them?
- [ ] Chip decomposition: rule-based parser first, or immediate LLM call?
- [ ] For the column block view: horizontal scroll vs. pagination for deep trees?
- [ ] Date/range conditions: displayed as chips or as a separate filter panel?
- [ ] Result ranking: pure semantic similarity, or blend with cluster-level match score?
- [ ] Mobile/responsive layout: column view collapses to accordion?

---

## Files

| File | Purpose |
|---|---|
| `visual_search_synopsis.md` | This document — design record |
| `visual_search_mockup.html` | Interactive frontend mockup (dummy data, no real backend) |

---

## Next Steps

1. ✅ Design synopsis written
2. ✅ Interactive mockup built (dummy cluster tree, lexical highlight, chip toggling)
3. ⬜ Finalize column block UI with real cluster tree JSON
4. ⬜ Wire search decomposition (rule-based or LLM)
5. ⬜ Connect to real tree-z artifact
6. ⬜ Implement Steiner tree subselection on Execute
7. ⬜ Add generative answer layer (optional, later)
