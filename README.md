# Orchard View

`visual_search_mockup.html` is the current build: a ledger-driven visual search UI over a
document corpus, organized by a domain tree and a function tree (two lattice partitions of
the same underlying items). Open the file directly in a browser — no build step, no server.

This is the applied-tooling side of the [Orchard](../../../Claude/Projects/Orchard) worldview
project (cultivated data partitions for reducing decision space). Full planning history —
proposals, decision sheets, phased implementation plans, handoff docs — lives in that Orchard
folder, not here. This repo stays down to the artifact itself plus whatever's needed to run it.

## Layout

- `visual_search_mockup.html` — the mockup. Single self-contained file (HTML/CSS/JS).
- `archive/` — snapshots of the planning docs that shaped the current build, kept for
  provenance rather than day-to-day reference. See the Orchard folder for anything current.
- `pyproject.toml` / `main.py` — uv-managed Python scaffold, not yet wired to anything.

## Status

Current build has two resolved pieces of core logic: a term/node interaction gate (a search
term narrows an included tree branch instead of losing to it on specificity) and a `group_id`
rejoin fix (re-parsing a query after removing one of its chips rejoins the surviving AND-group
instead of splitting into an OR). Right-click on a tree node changes its color immediately;
treemap tile sizes stay fixed until Go/Reset commits the change, so clicking around doesn't
bounce the layout.
