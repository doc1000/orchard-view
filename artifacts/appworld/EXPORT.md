# AppWorld orchard export

Hydrated in-memory orchard from existing AppWorld linkage and imported
phase5a intrinsic labels, then cut with orchard's Calinski–Harabasz
dynamic optimal cutter. Labels were not regenerated.

## Sources

- Documents: `tool-tree-demo/artifacts/appworld/run-a/tools.jsonl`
  (457 records; `tool_id` → `item_id`/`title`,
  `description` → `text`, remaining fields → `metadata`, `source="appworld"`)
- `function` labeled tree: `tool-tree-demo/artifacts/appworld/phase5a/trees/functional_dominant_raw_convex/intrinsic_labeled_tree.json`
- `function` feature matrix: `tool-tree-demo/artifacts/appworld/phase3b/profiles/functional_dominant_raw_convex.npz` (phase3b `.npz` `matrix` + `tool_ids`, row-aligned to linkage `item_ids`; square matrices also column-permuted so the diagonal stays self-similarity / self-distance)
- `domain` labeled tree: `tool-tree-demo/artifacts/appworld/phase5a/trees/domain_dominant_variance_calibrated/intrinsic_labeled_tree.json`
- `domain` feature matrix: `tool-tree-demo/artifacts/appworld/phase3b/profiles/domain_dominant_variance_calibrated.npz` (phase3b `.npz` `matrix` + `tool_ids`, row-aligned to linkage `item_ids`; square matrices also column-permuted so the diagonal stays self-similarity / self-distance)

## Imported labels

- Label set name: `phase5a_intrinsic` (`import_labels` only; no `label_intrinsic()`)
- Root overrides (same named set, roots only): domain → `domain`, function → `function`
- `function` internals missing an intrinsic label: 0 (no replacements invented)
- `function` active root label: `function`
- `domain` internals missing an intrinsic label: 0 (no replacements invented)
- `domain` active root label: `domain`

## Cut parameters (both trees)

- `top_criterion`: `optimal`
- `cut_optimizer`: `calinski_harabasz_score`
- `cut_polarity`: `1`
- `min_width`: `3`
- `max_width`: `10`
- `target_width`: `null`
- `max_depth`: `5`
- `threshold_steps`: `32`
- No fixed `cluster_count` cut is shipped as the optimized artifact.

The dynamic cutter searches k only inside `min_width..max_width` (`3..10`).
A flatter unconstrained Calinski sweep may report a different k (live
notebook: 11 vs rebuilt `top_partition_count` 9 on domain). That gap is expected.

## Results

### `function`

- `top_partition_count`: **3**
- aligned feature matrix shape: `[457, 457]`; diag min/max `1` / `1`
- cutter `warnings`:
  - (none)

### `domain`

- `top_partition_count`: **9**
- aligned feature matrix shape: `[457, 457]`; diag min/max `0` / `0`
- cutter `warnings`:
  - (none)

## Output layout

```
orchard-view/artifacts/appworld/
  orchard/          # Orchard.save()
  cuts/             # raw build_dynamic_cut JSON + provenance manifest
  labels/           # imported phase5a_intrinsic mappings (post root override)
  node_descriptions.json
  EXPORT.md
```
