# Handoff — implement the Option A term gate + `group_id` rejoin

## The one rule that matters

**If a validation check disagrees with its expected number, stop and report it. Do not adjust the code until the number matches.**

The expected numbers in the plan were measured against the current file *before* any of this was designed — they describe what the corpus actually contains, not what the new code should produce. So a mismatch means either the plan's reasoning is wrong or the implementation is, and both need a human. On 2026-07-30 a session in this same function "fixed" the reported symptom by restructuring load-bearing logic, broke behavior the user had built over multiple sessions, and had to be fully rolled back. The failure was not coding ability. It was continuing past the point where stopping was correct.

Corollary: **do not redesign anything.** The design decisions are locked and were made deliberately by the user across a long review. If something in the plan looks wrong, say so and stop — don't improve it.

## Your task

Implement the two changes specified in `C:\Users\doste\Claude\Projects\Orchard\implementation_plan_term_gate.md`, in `C:\Users\doste\Claude\Projects\Orchard\visual_search_mockup.html`.

That plan contains the literal before/after code. Follow it as written. Nothing in it is a sketch.

- **Change 1 — term gate in `resolveDoc()`.** Delete the virtual specificity-0 term vote (~lines 1036–1052); tag the contest winner with `kind: entry.target_type`; add a 4-line term gate after the contest, with explicit per-document decisions exempt.
- **Change 2 — `group_id` rejoin in `parseQuery()`.** `hasActiveTermEntry` → `findActiveTermEntry` (returns the entry); adopt the anchor entry's `group_id` *and* `query_id` so re-parsed tokens rejoin an existing AND-group instead of forming an OR alternative beside it.

Land and validate them **in that order, separately.** They are independently revertible and should stay that way.

## Read first

1. `Orchard/implementation_plan_term_gate.md` — the plan. Authoritative.
2. Memory: `project_visual_search_mockup.md` and `feedback_no_adhoc_architecture_changes.md` — pre-populated in your system prompt on this space. History of what's resolved, what was rolled back, and why.
3. `Orchard/proposal_term_node_interaction.md` — background and the measured tables, if you want the reasoning behind the decisions. Not needed to execute.
4. The full `<script>` block of `visual_search_mockup.html` before editing anything.

`Orchard/implementation_plan.md` (the original phased spec) is still broadly authoritative for everything *except* what memory says was changed or reverted. It predates all of this.

## Decisions already locked — do not revisit

Option A (terms gate outside the specificity contest) · Q1a (`branch ∩ term` — a node include always bounds the result; terms only narrow) · Q2 (explicit document pins always survive a failing term filter) · Q3 (exclude-terms gate symmetrically with include-terms) · Q4 (with no node include active, term behavior is unchanged) · Q5 (Option A now; Option B typed-lanes refactor deferred) · Q6 (fix the `group_id` split) · Q7 (idempotency stays terms-only; node/document cycling is deliberately stateful).

Deferred on purpose, not oversights: Option B, and Q1c (operator-controlled expansive/additive terms — the user may want `or`-style unions later; this design leaves room without disturbing the reductive default).

## Do not touch

- `ledgerHasActiveNodeInclude()` — validated, load-bearing.
- `docPassesTermFilter()` — the gate calls it unchanged.
- `evaluate()` — no changes needed.
- The OR-connector chip logic (`query_id`, `.chip-or`, connector insertion in `renderChips()`).
- Search-box clearing behavior — deliberately left as-is (never cleared). Do not reintroduce clearing.
- The contest loop in `resolveDoc()` — only the winner-assignment line gains a `kind` field.

## Validation

Run all 14 checks in the plan's Validation section and **report the actual numbers**, not a pass/fail summary. Then a manual in-browser pass: chip tray, sidebar/treemap counts tracking `WORKING_SCOPE`, Undo stepping back through each action, Go archiving and resetting cleanly, and contrast still meeting the project rule in `CLAUDE.md`.

Harness gotchas — these cost a previous session several turns:

- jsdom with `runScripts: 'dangerously'`, and stub `ResizeObserver` in `beforeParse` or the page throws on load.
- Drive the page through `window.eval`, **not** `window.LEDGER` — top-level `let`/`const` (`LEDGER`, `BASE`, `WORKING_SCOPE`, `CORPUS`, `DOMAIN_TREE`) are lexical bindings and are not window properties.
- Give the page ~500ms before driving it.
- `npm install jsdom` works in the sandbox.

Key expected values: `Travel & Destinations` include = 16 docs; then `beach` → 3, `work` → 7 (not 55, not 16), `food` → 0; deeper node `Beach & Coastal` + `beach` → 3; pinned non-matching doc + `beach` → scope 4 with the pin present; doc-excluded matching doc + `beach` → scope 2; `beach` with no node include → 3.

## When done

Update memory (`project_visual_search_mockup.md`): move the term/node redesign from backlog to resolved with the final semantics, record Q6 as fixed, and note that Option B remains open as a pure no-op refactor with no behavior change attached.

## Exit criteria

- Both changes implemented exactly as the plan specifies, applied and validated in order.
- All 14 checks reported with actual numbers; any mismatch escalated rather than coded around.
- Existing validated behavior intact: specificity competition for node-vs-node and node-vs-document, `ledgerHasActiveNodeInclude` default-exclude, OR-connector chips, shared-`group_id` AND semantics, term-write idempotency.
- Memory updated.
