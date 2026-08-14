# Decision sheet — how query terms should compose with node/document scope

**Status:** awaiting your decisions. **No `resolveDoc()`/`evaluate()` code has been written.**
**File:** `visual_search_mockup.html` · **Date:** 2026-08-06

Read §1–2 for background, then answer the seven questions in §4. Q1 is the only one that really matters; Q2–Q7 are mostly confirmations, each with a recommended default you can accept wholesale. Everything here is measured against the current file via a jsdom harness, not assumed.

---

## 1. What's wrong, precisely

Include "Travel & Destinations" → 84 docs becomes 16. Type `beach`, Parse → a chip appears, scope stays 16. Confirmed reproducible.

In `resolveDoc()`:

- A **node** entry's specificity is its index in the doc's ancestor path. `DOC_PATHS` includes the root, so a top-level node scores **1**; deeper nodes score higher.
- A **document** entry scores **999** and always wins.
- A **failing term filter** folds in as a single virtual vote at specificity **0** (~line 1043).

1 > 0, so any node include silently discards the term.

The off-by-one isn't the real problem — the **direction** is. The deeper and more specific the branch you include, the more strongly it overrides your search term. Refining the branch is what defeats the refinement. Raising the term's constant just relocates an arbitrary threshold; the inversion survives.

**Root cause:** `specificity` is one linear scale ranking three things that don't share an axis — a document pin (an explicit manual override), a node decision (a structural position), and a term filter (a content predicate). `999` and `0` are sentinels standing in for "this is a different *kind* of thing," not real positions on a scale. Any fix that keeps all three on one axis will keep producing this class of bug.

## 2. Measured behavior (current file, 84-doc corpus)

"Travel & Destinations" included = 16 docs. Then, for each term:

| term | corpus matches | inside branch | outside | today | A: `branch ∩ term` | B: term wins |
|---|---|---|---|---|---|---|
| `beach` | 3 | 3 | 0 | **16** | 3 | 3 |
| `local` | 8 | 8 | 0 | **16** | 8 | 8 |
| `work` | 55 | 7 | 48 | **16** | 7 | 55 |
| `food` | 5 | 0 | 5 | **16** | 0 | 5 |
| `health` | 15 | 0 | 15 | **16** | 0 | 15 |
| `design` | 4 | 0 | 4 | **16** | 0 | 4 |

Today's column is the bug: the term changes nothing. **A and B agree whenever a term has no matches outside the branch** — which is why your `beach` example doesn't discriminate between them. They diverge sharply on `work`.

Two more measurements that matter for Q2/Q3:

- A **document pin already survives a failing term filter today** (999 > 0). Pin "Remote ML Engineering at Fintech Scale", then search `beach` → scope 4 = 3 beach docs + the pin.
- A **document exclude already suppresses a term-matching doc today** → scope 2. Both behaviors are current, tested, and worth preserving.

---

## 3. The three structural options

### Option A — terms are a gate, applied outside the contest ⭐ recommended

Leave the specificity contest untouched for node-vs-node and node-vs-document. After a winner is chosen, apply the term filter as a final AND: if terms are active and the doc fails `docPassesTermFilter()`, exclude it — **unless** the winner is a document-level entry, which stays final.

Model: *the tree layer chooses the candidate set; the query text filters within it; explicit per-doc pins sit above both.*

- **Diff:** one added branch after the contest. `evaluate()`, `docPassesTermFilter()`, and the node/document contest all unmodified.
- **Fixes the inversion at its root** — term-vs-node stops being a magnitude comparison at all.
- `ledgerHasActiveNodeInclude()`'s default-exclude is untouched (it fires on `winner === null`; A only adds exclusions).
- **Risk:** low. Revertible by deleting one block. The behavior change is confined to "terms now bite."
- **Cost:** with a node include active, a term can only subtract. See Q1.

### Option B — typed precedence lanes

Stop pretending the kinds share a scale. Resolve in explicit order: **document override → term gate → node contest (by depth + ts, as today) → implicit default-exclude.** Each kind competes only within its own lane.

- For today's entity set this is **behaviorally identical to A**. It's the honest structural version of the same rule.
- Pays off when a fourth kind arrives — the semantic/synonym layer you've mentioned, hopper state, saved views — each gets a lane instead of a fight over a magic number.
- **Risk: moderate-to-high.** A substantially larger diff inside `resolveDoc()`, which is the exact shape of change that got rolled back on 2026-07-30.
- **Mitigation:** if you want B, do **A first** (behavior change, tiny diff, easy to validate), then B as a *pure no-op refactor* once A is confirmed. Separating "change the behavior" from "restructure the code" is what was missing last time; each step stays independently revertible.

### Option C — terms at specificity 1000 (listed to rule out)

Keep one linear scale, move terms above documents. One-line change, but it **breaks document pins** — pin a doc, type an unrelated word, the pin silently vanishes (contradicting the measured behavior above) — and preserves the linear-scale conflation that caused this. Not recommended.

---

## 4. The decisions

### Q1 — With a node included *and* a term active, does the node still constrain? ⚠️ the real question

This is where your two earlier answers pulled apart: you picked A (a gate, which only narrows) but also said terms should be able to *add*. Those are incompatible, and `work` above shows the gap: 7 docs vs 55.

| | behavior | `Travel` + `work` |
|---|---|---|
| **Q1a** ⭐ | `branch ∩ term`. The include always bounds the result; terms refine within it. With **no** node include active, terms behave exactly as today — they select from the whole corpus. | 7 |
| **Q1b** | Term supersedes the branch. Scope becomes all term matches; the node include only shapes things when no term is active. This is "terms also add," taken literally. | 55 |
| **Q1c** | Operator-dependent — a bare term narrows within scope, a prefixed/toggled one searches corpus-wide and adds. Removes the ambiguity permanently at the cost of a new UI affordance and a `parseQuery()` token. | either, your call per query |

**Recommendation: Q1a.** It's consistent with `ledgerHasActiveNodeInclude`'s existing "included branch = the whole scope" stance, and it's what makes tree-narrowing worth doing at all — under Q1b, narrowing to Travel and then typing `work` throws your narrowing away silently, which is the same class of surprise as the current bug. **But Q1c is the honest answer if you genuinely want both**, and it's the one I'd pick if "terms should also add" was a firm requirement rather than an instinct. Q1c is also strictly larger scope than the rest of this document — I'd want it as its own phase, not bundled here.

**Risk if we choose wrong:** Q1a→Q1b is a one-line flip later. Q1c retrofitted later means touching `parseQuery()`, the chip renderer, and the term gate together.

### Q2 — Do explicit document pins survive a failing term filter?

Pin a doc, then search a term it doesn't match. **Today: it survives** (999 beats the term's 0).

- ⭐ **Keep** — a manual pin is the most explicit signal in the system and should outrank everything. Preserves measured current behavior; A's carve-out exists for this.
- **Change** — terms gate everything including pins. Simpler rule, but a pin can vanish without you touching it.

**Recommendation: keep.** Zero risk — it's the status quo.

### Q3 — Do exclude-terms (`-beach`) apply inside an explicitly included branch?

`docPassesTermFilter()` folds include- and exclude-terms into one boolean, so under A they're gated identically: `-local` inside Travel would drop all 8 matching docs.

- ⭐ **Yes, symmetric** — `-term` subtracts everywhere, matching `+term`'s gating.
- **No** — exclude-terms yield to an explicit node include.

**Recommendation: symmetric.** Falls out of A for free; splitting them means two code paths and a rule that's hard to hold in your head. Low risk.

### Q4 — Terms with no node include active: unchanged?

Today `beach` alone filters BASE 84 → 3. Under A this is **unchanged** (the gate applies uniformly; there's just no competing node winner). Flagging only so it isn't a surprise. ⭐ **Confirm unchanged.**

### Q5 — Structural direction and sequencing

- ⭐ **A now, revisit B when a fourth entity kind lands.** Small diff, fixes the bug, doesn't pre-commit.
- **A now, B as a scheduled follow-up refactor.** Same first step, with B queued as an explicit no-op change.
- **B directly.** One pass, bigger diff, higher rollback risk.

**Recommendation: first.** The 2026-07-30 rollback happened because a behavior fix and a restructure shipped together and couldn't be separated when one of them was wrong.

### Q6 — `group_id` split after partial chip removal (independent of everything above)

Remove one chip of a multi-word AND query, then re-parse the same text: the surviving token keeps its old `group_id`, the re-added token mints a new one, and `docPassesTermFilter()` reads them as two OR groups. `beach travel` (AND = 3 docs) becomes OR (16). **A/B'd against a build with the new dedupe removed — identical either way, so this predates yesterday's change**; the dedupe only improved the chip count (3 → 2).

- ⭐ **Fix it** — when a group contains any skipped-because-already-active token, reuse that existing entry's `group_id` for the whole group. `parseQuery()` only, ~3 lines, does not touch `resolveDoc()`.
- **Leave it** — it's an edge case and predates all of this.

**Recommendation: fix.** Cheap, isolated, and it's a quiet re-run of the AND/OR bug you already fixed once.

### Q7 — Should node/document writes be idempotent too?

Yesterday's change made *term* writes idempotent. Node/document cycling is deliberately stateful (neutral → include → exclude), so applying the same rule would break cycling.

- ⭐ **No** — terms only. Flagged so it isn't assumed either way.

---

## 5. If you accept every ⭐ default

Implement **A** with the document-pin carve-out (Q1a, Q2-keep, Q3-symmetric), plus the **Q6** `group_id` fix. Two isolated changes, both revertible independently. B stays on the backlog; Q1c stays a separate future phase.

**Validation before I'd call it done:** include "Travel & Destinations" (84 → 16) → `beach` narrows to 3 → `work` gives 7, not 55 → remove the term chip → back to 16 → remove the node chip → back to 84 → a right-click-pinned doc survives an unrelated term → a doc-excluded doc stays excluded despite matching a term → OR-connector chips, shared-`group_id` AND semantics, and the default-exclude all unchanged.
