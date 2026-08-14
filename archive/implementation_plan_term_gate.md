# Implementation plan — Option A term gate + `group_id` rejoin

**Status:** awaiting your go-ahead. No code written yet.
**Decisions locked (2026-08-06):** Option A · Q1a `branch ∩ term` · Q2 doc pins always survive · Q3 symmetric · Q4 unchanged · Q5 A now, B later · Q6 fix · Q7 default (terms only).
**File:** `visual_search_mockup.html` · **Plan doc:** supersedes the decision sheet in `proposal_term_node_interaction.md`.

Two independent changes. **Change 1** touches `resolveDoc()` (the load-bearing function); **Change 2** touches only `parseQuery()`. They can be applied and reverted separately, and I'd like to land and validate them in that order.

Call graph confirmed before planning: `recompute()` → `evaluate()` → `resolveDoc()` → `docPassesTermFilter()`. One caller each, no other entry points.

---

## Change 1 — the term gate in `resolveDoc()`

### 1a. Remove the virtual specificity-0 vote (lines ~1036–1052)

Delete this block entirely:

```js
  // Term filter: fold the OR-group result in as a single specificity-0 entry.
  // Node inclusions (specificity >= 1) and document decisions (999) still win over this.
  if (orGroups && orGroups.size > 0) {
    const passesTerms = docPassesTermFilter(doc, orGroups);
    if (!passesTerms) {
      const allTermEntries = [...orGroups.values()].flat();
      const ts = allTermEntries.length ? Math.max(...allTermEntries.map(e => e.ts)) : Date.now();
      const specificity = 0;
      const beats = ...;
      if (beats) winner = { specificity, ts, polarity: "exclude" };
    }
  }
```

This is the whole bug: it puts a content predicate on the same axis as structural position, at a constant that any node include beats.

### 1b. Tag the winner with its kind

In the contest loop, the two places that set `specificity` also record what kind of entry it was, and the assignment carries it:

```js
    if (entry.target_type === "document") {
      if (String(doc.id) === String(entry.target_id)) specificity = 999;
    } else if (entry.target_type === "node") {
      ...
    }
    ...
    if (beats) {
      winner = { specificity, ts: entry.ts, polarity: entry.polarity, kind: entry.target_type };
    }
```

*Why not just test `specificity === 999`?* It works today, but it re-reads the sentinel as if it meant something on the scale — the exact confusion this change exists to undo. `kind` says what we actually mean, costs two lines, and is the first small step toward B. **Alternative if you'd rather keep the diff minimal: skip 1b and test `winner.specificity === 999` in 1c.** Functionally identical.

### 1c. Add the gate after the contest

Immediately before the final `return`, after the existing `nodeIncludeActive` default-exclude block (which stays exactly as it is):

```js
  // Term gate — applied OUTSIDE the specificity contest, not as a competitor in it.
  // The tree layer chooses the candidate set; the query text filters within it.
  // A term is a content predicate, not a position in the hierarchy, so it has no
  // meaningful specificity to compare against a node's depth — comparing them is
  // what made deeper (more specific) includes override terms harder, which is
  // backwards. The one exception is an explicit per-document decision: that's a
  // deliberate manual act and stays final.
  if (orGroups && orGroups.size > 0 && winner?.kind !== "document") {
    if (!docPassesTermFilter(doc, orGroups)) return "exclude";
  }

  return winner ? winner.polarity : "neutral";
```

**Ordering note:** the gate reads `winner` but never writes it, and the default-exclude block only fires on `winner === null` (which can never be `kind: "document"`). So the two are order-independent — I'm putting the gate last purely so the diff stays local and the reading order matches the mental model: contest → default → filter.

### What this yields

| situation | winner | gate | result |
|---|---|---|---|
| no node include, doc matches | `null` | passes | `neutral` → in scope ✔ unchanged (Q4) |
| no node include, doc fails | `null` | **excluded** | out ✔ unchanged (Q4) |
| in included branch, matches | node include | passes | in ✔ |
| in included branch, **fails** | node include | **excluded** | out ✔ **this is the fix** |
| outside branch, matches | `null` → default-exclude | n/a | out ✔ (Q1a — reductive) |
| doc-pinned, fails filter | `{999, include, document}` | **skipped** | in ✔ (Q2) |
| doc-excluded, matches filter | `{999, exclude, document}` | skipped | out ✔ |
| `-term` matches inside branch | node include | **excluded** | out ✔ (Q3 symmetric) |

Against the measured table: `Travel` + `work` → 7 (not 55, not today's 16). `Travel` + `food` → 0. `beach` alone → 3.

### Risk and rollback

Low. The contest loop, `docPassesTermFilter()`, `ledgerHasActiveNodeInclude()`, and `evaluate()` are all unmodified in substance — 1b adds one field, 1a/1c swap a ~15-line block for a ~4-line one. Rollback is restoring the deleted block and deleting the gate. Nothing outside `resolveDoc()` changes, and it has exactly one caller.

---

## Change 2 — rejoin existing AND-groups in `parseQuery()` (Q6)

### 2a. `hasActiveTermEntry` → `findActiveTermEntry`

Return the entry instead of a boolean; the truthiness check at the call site is unchanged in meaning.

```js
function findActiveTermEntry(termId, polarity, quoted) {
  return LEDGER.find(e =>
    e.target_type === "term" &&
    e.target_id === termId &&
    e.polarity === polarity &&
    Boolean(e.quoted) === Boolean(quoted)
  ) || null;
}
```

### 2b. Adopt the surviving group's ids

```js
  groups.forEach((group, gIdx) => {
    // If any token in this group is already live, adopt that entry's ids so the
    // re-added tokens rejoin the existing AND-group rather than forming a new
    // OR-alternative beside it. Without this, "beach travel" → ×beach → re-parse
    // leaves travel@old + beach@new, which docPassesTermFilter reads as
    // "beach OR travel" (16 docs) instead of AND (3).
    const anchor = group
      .map(t => findActiveTermEntry(t.term, t.neg ? "exclude" : "include", t.quoted))
      .find(Boolean);
    const groupId = anchor ? anchor.group_id : baseId + gIdx;
    const queryId = anchor ? anchor.query_id : baseId;

    for (const tok of group) {
      const polarity = tok.neg ? "exclude" : "include";
      if (findActiveTermEntry(tok.term, polarity, tok.quoted)) { skipped++; continue; }
      UNDO_STACK.push({ type: "ledger_pop" });
      writeLedger({ ..., group_id: groupId, query_id: queryId });
      written++;
    }
  });
```

`query_id` is adopted alongside `group_id` so the chip tray's "or"-connector logic (which keys on matching `query_id` + differing `group_id`) sees a coherent group. Adopting only one of the two would make a rejoined token look like an unrelated condition.

**Known edge case, deliberately not handled:** if one group's tokens are already live under *two different* prior queries, the first match wins the anchor. Rare, and any resolution would be arbitrary — flagging rather than guessing.

### Risk and rollback

Very low. `parseQuery()` only; `resolveDoc()` untouched. Rollback is reverting one function.

---

## Validation

Automated first, through the jsdom harness that drove the earlier measurements (it loads the real file with a `ResizeObserver` stub and drives the page via `window.eval`, since top-level `let`/`const` like `LEDGER` are lexical, not window properties). Then a manual pass in the browser, since the harness can't see rendering.

**Change 1**

1. `Travel & Destinations` include: 84 → 16 (default-exclude intact)
2. → `beach`: **3** (was 16) — the original bug
3. → `work`: **7**, not 55 and not 16 — Q1a specifically
4. → `food`: **0** — a term with zero in-branch matches empties the scope rather than being ignored
5. Remove the term chip → back to 16; remove the node chip → back to 84
6. Deeper node `Beach & Coastal` (3 docs) + `beach` → 3 — depth no longer inverts the outcome
7. Pin a non-matching doc, then `beach` → pinned doc still present, scope 4 (Q2)
8. Doc-exclude a matching doc, then `beach` → suppressed, scope 2
9. `-local` inside Travel → the 8 matching docs drop (Q3)
10. `beach` with no node include → 3 (Q4 unchanged)
11. `machine learning` still shares one `group_id` and ANDs

**Change 2**

12. `beach travel` (3) → ×beach → re-parse → **3**, not 16
13. Re-parse `beach travel` 3× → 2 chips, scope 3 (yesterday's idempotency intact)
14. `beach or vacation` → 2 chips + 1 "or" connector; re-parse → unchanged

**Manual in-browser:** chip tray renders correctly through the above, sidebar/treemap counts track `WORKING_SCOPE`, Undo walks back through each step, Go archives and resets cleanly, contrast still meets the project rule.

I'll report the numbers rather than asserting it works, and if any of 1–14 disagrees with this table I'll stop and bring it back rather than adjusting the code until the test passes.

---

## Afterward

Update `project_visual_search_mockup.md`: move the term/node redesign from backlog to resolved with the final semantics, record Q6 as fixed, note Option B is still open as a pure refactor with no behavior change attached, and note Q1c (operator-controlled expansive/additive terms) as a possible future phase — you flagged you may want `or`-style unions later, and this design leaves room for that without disturbing the reductive default.
