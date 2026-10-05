# Orchard demo + agent control surface

A recorded Playwright demo of the Orchard AppWorld visual tool search, plus the
`window.orchard` API. The API lets an agent run the same search by calling functions and reading structured state, with no clicks or screenshots.

▶ **Watch the demo:** https://youtu.be/cxSrKvUfdAY

## Generate the video

```bash
npm install
npm run setup        # one-time: downloads Playwright's Chromium
npm run demo         # → demo/orchard_demo.webm (+ demo/orchard_demo.mp4 if ffmpeg is on PATH)
```

`npm run demo` does the following:
- starts a small Node static server for `artifacts/appworld/standalone/orchard_view_appworld_202615081315/`, with d3 served locally so no network is needed
- records Chromium at 1440×900
- checks the scope counts after every step and fails loudly if they drift
- writes the video to this folder. The run takes about 45s.

```bash
npm run demo:agent            # same decision path, API calls only, prints state per step
npm run demo:agent -- --full  # full JSON state after each step
```

## Demo sequence

Every number in the captions is read from live state, not hardcoded.

| Scene | Action | Scope |
|---|---|---|
| 0 | Full corpus. Caption states the task: log a user into their Amazon account | 457 |
| 1–2 | Type the intent `user account` (not a tool name) and Parse. Irrelevant regions turn red | 457 → 69 |
| 3 | Drill into *User identity…*, then **Shift+right-click** *Profile, Credential, Address, and Friend Management* to reject it | 69 → 59 |
| 4 | Switch **Domain → Function**: the same 59 tools in a different partition | 59 |
| 5 | Drill into *Authentication and code dispatch*, then right-click to include *Account Access Validation* | 59 → 9 |
| 6 | **Go**: commit. The 9 login tools become the new base and the treemap re-lays out | base 457 → 9 |
| 7 | Switch back to **Domain**: the same 9 tools, one per app | 9 |
| 8 | Right-click to include the `amazon.login` tile, then **Go** | base 9 → 1 |
| 9 | Open `amazon.login` and show its preview. Final caption: `457 tools → 1` | 1 |

The domain tree doesn't split login tools by app (all 9 sit under *Account Access Validation*). So the last step picks the Amazon tile directly instead of navigating an "Amazon" branch.

The recorder adds a few overlays: a visible cursor with click ripples, keycap hints, captions, and hidden hover tooltips. They exist only in the recording. The product page doesn't include them.

## Interaction model

| Level | Meaning | API |
|---|---|---|
| Corpus | All 457 tools, never changes | `corpus_count` |
| Base | The committed search universe | `base_count` |
| Working scope | Base filtered by the current terms and include/exclude decisions | `working_count`, `candidate_tools` |
| Go | Commit: the working scope becomes the new base and the decisions clear | `commitScope()` |

Mouse controls:
- **Right-click** a node to cycle neutral → include → exclude.
- **Shift+right-click** a node to exclude it directly.
- **Left-click** to drill in.

Includes made in the two trees combine as a **union**. To narrow across both trees, commit with Go before switching trees, as the demo does.

## Agent-facing API (`window.orchard`)

The API lives in `artifacts/appworld/standalone/orchard_view_appworld_202615081315/orchard_api.js`, and both HTML copies load it. It is a thin wrapper over the page's existing functions (`parseQuery`, `setNodePolarity`, `switchTree`, `go`, `resetAll`, `openPreview`). Every mutator returns `getState()` as plain JSON.

| Function | Purpose |
|---|---|
| `getState()` | `{tree, corpus_count, base_count, working_count, focus_path, included_nodes, excluded_nodes, terms, children, candidate_tools (≤50), commits, preview}` |
| `getScope()` / `getCandidateCount()` / `getCandidateTools()` / `getActiveDecisions()` | Narrower reads |
| `findNodes(labelSubstring, tree?)` | Label → `[{id, label, tree, depth}]` (node ids are hashes) |
| `getChildren(nodeId?)` | Children of the focus node or a given node, with base/working counts and polarity |
| `search(query)` | Parse query terms into conditions |
| `switchTree("domain" \| "function")` | Change partition; keeps base and decisions |
| `includeNode(id)` / `excludeNode(id)` / `clearNode(id)` | Explicit decisions |
| `commitScope()` | Go |
| `drillInto(id)` / `drillUp()` / `drillToRoot()` | Treemap focus (changes the view only) |
| `inspectTool(toolId)` | Open the preview; returns `{id, title, path, body, in_working_scope}` |
| `reset()` | Back to the full corpus and the Domain tree |

Example agent trace (`npm run demo:agent`):

```
search("user account")                       base=457 working= 69
excludeNode(<Profile, Credential, Address…>) base=457 working= 59
switchTree("function")                       base=457 working= 59
includeNode(<Account Access Validation>)     base=457 working=  9  [amazon.login, gmail.login, …]
commitScope()                                base=  9 working=  9
switchTree("domain")                         base=  9 working=  9
includeNode(<amazon.login>)                  base=  9 working=  1  ["amazon.login"]
commitScope()                                base=  1 working=  1
```

### Exposing it to an agent later

The search state lives in the page, so the cheapest route is to keep a headless page session (see `agent_walkthrough.js`) and map each `orchard.*` function to one tool. That works over MCP, HTTP or a Python Playwright bridge. Each tool call becomes `page.evaluate(() => orchard.<fn>(args))`, and the JSON comes back unchanged. If a browser-free runtime is needed, port `evaluate()`/`resolveDoc()` and the ledger to Python against the same `mockup_data.js` trees. The API surface can stay the same.

## Files

- `record_demo.js`: the recorded demo (scenes, mouse pacing, captions, assertions, video/mp4 output)
- `agent_walkthrough.js`: the same path through the API only
- `lib.js`: static server, page loading, node lookup, scope assertions
- `orchard_demo.webm` / `orchard_demo.mp4`: the latest local recording (gitignored; published at https://youtu.be/cxSrKvUfdAY)
