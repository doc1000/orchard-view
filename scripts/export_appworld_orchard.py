"""Hydrate AppWorld orchard, Calinski-optimal cut, export into orchard-view.

Reads tool-tree-demo artifacts (JSON / npz only). Does not import tool_tree_demo,
call OrchardBuilder.build(), or regenerate labels.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from orchard import Document, Orchard, Tree, build_dynamic_cut, import_labels, validate_dynamic_cut

VIEW_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = VIEW_ROOT.parent
DEMO_ROOT = WORKSPACE_ROOT / "tool-tree-demo"
OUT_ROOT = VIEW_ROOT / "artifacts" / "appworld"

TOOLS_JSONL = DEMO_ROOT / "artifacts" / "appworld" / "run-a" / "tools.jsonl"
PHASE5A_TREES = DEMO_ROOT / "artifacts" / "appworld" / "phase5a" / "trees"
PHASE3B_PROFILES = DEMO_ROOT / "artifacts" / "appworld" / "phase3b" / "profiles"

EXPECTED_ROOT_ID = (
    "member_fa955a31c93e0faf46e743098371cfff7a6519c28c4a43755e04d435614d6b02"
)
EXPECTED_DOCUMENT_COUNT = 457
LABEL_SET_NAME = "phase5a_intrinsic"
SOURCE_NAME = "appworld"

CUT_PARAMS: dict[str, Any] = {
    "top_criterion": "optimal",
    "cut_optimizer": "calinski_harabasz_score",
    "cut_polarity": 1,
    "min_width": 3,
    "max_width": 10,
    "target_width": None,
    "max_depth": 5,
    "threshold_steps": 32,
}

TREE_SPECS: tuple[dict[str, str], ...] = (
    {
        "tree_id": "function",
        "labeled_json": str(
            PHASE5A_TREES / "functional_dominant_raw_convex" / "intrinsic_labeled_tree.json"
        ),
        "npz": str(PHASE3B_PROFILES / "functional_dominant_raw_convex.npz"),
        "root_label": "function",
    },
    {
        "tree_id": "domain",
        "labeled_json": str(
            PHASE5A_TREES
            / "domain_dominant_variance_calibrated"
            / "intrinsic_labeled_tree.json"
        ),
        "npz": str(PHASE3B_PROFILES / "domain_dominant_variance_calibrated.npz"),
        "root_label": "domain",
    },
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any, *, sort_keys: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=sort_keys) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def load_documents(path: Path) -> list[Document]:
    documents: list[Document] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        tool_id = str(row["tool_id"])
        metadata = {key: value for key, value in row.items() if key not in {"tool_id", "description"}}
        documents.append(
            Document(
                text=str(row.get("description") or ""),
                item_id=tool_id,
                title=tool_id,
                metadata=metadata,
                source=SOURCE_NAME,
            )
        )
    if len(documents) != EXPECTED_DOCUMENT_COUNT:
        raise SystemExit(
            f"expected {EXPECTED_DOCUMENT_COUNT} tools.jsonl records, got {len(documents)}"
        )
    return documents


def label_mapping_from_source(payload: dict[str, Any]) -> tuple[dict[str, str], int]:
    mapping: dict[str, str] = {}
    missing_internal = 0
    for node_id, node in payload["nodes"].items():
        summary = node.get("intrinsic_summary") or {}
        intrinsic = summary.get("intrinsic_label")
        if isinstance(intrinsic, str) and intrinsic.strip():
            mapping[node_id] = intrinsic
            continue
        if node.get("kind") == "leaf":
            leaf_id = node.get("tool_id") or node.get("item_id")
            if leaf_id:
                mapping[node_id] = str(leaf_id)
        else:
            missing_internal += 1
    return mapping, missing_internal


def node_descriptions_from_source(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    descriptions: dict[str, dict[str, Any]] = {}
    fields = ("intrinsic_label", "intrinsic_description", "scope_boundary", "key_capabilities")
    for node_id, node in payload["nodes"].items():
        summary = node.get("intrinsic_summary") or {}
        if not isinstance(summary, dict):
            continue
        extracted = {field: summary[field] for field in fields if field in summary}
        if extracted:
            descriptions[node_id] = extracted
    return descriptions


def assert_node_id_sanity(tree: Tree, payload: dict[str, Any], tree_id: str) -> None:
    source_root = payload["root_node_id"]
    if tree.root_node_id != source_root:
        raise SystemExit(
            f"{tree_id}: root_node_id mismatch after from_linkage: "
            f"{tree.root_node_id!r} != {source_root!r}. Stopping; not fuzzy-relabeling."
        )
    if tree.root_node_id != EXPECTED_ROOT_ID:
        raise SystemExit(
            f"{tree_id}: unexpected root hash {tree.root_node_id!r}; "
            f"expected {EXPECTED_ROOT_ID!r}. Stopping."
        )
    nodes = payload["nodes"]
    sample_internal = next(
        node["node_id"]
        for node in nodes.values()
        if node.get("kind") == "internal" and node.get("node_id") != source_root
    )
    sample_leaf = next(
        node["node_id"] for node in nodes.values() if node.get("kind") == "leaf"
    )
    for sample_id, role in (
        (source_root, "root"),
        (sample_internal, "internal"),
        (sample_leaf, "leaf"),
    ):
        if sample_id not in tree.nodes:
            raise SystemExit(
                f"{tree_id}: source {role} node {sample_id!r} missing from orchard tree. "
                "Stopping; not fuzzy-relabeling."
            )


def align_feature_matrix(
    matrix: np.ndarray,
    npz_tool_ids: list[str],
    linkage_item_ids: list[str],
    tree_id: str,
) -> np.ndarray:
    if len(npz_tool_ids) != len(linkage_item_ids):
        raise SystemExit(
            f"{tree_id}: npz tool_ids length {len(npz_tool_ids)} != "
            f"linkage length {len(linkage_item_ids)}"
        )
    index = {tid: i for i, tid in enumerate(npz_tool_ids)}
    missing = [tid for tid in linkage_item_ids if tid not in index]
    if missing:
        raise SystemExit(
            f"{tree_id}: {len(missing)} linkage item_ids missing from npz, e.g. {missing[:3]}"
        )
    extra = set(npz_tool_ids) - set(linkage_item_ids)
    if extra:
        raise SystemExit(
            f"{tree_id}: npz has {len(extra)} tool_ids not in linkage, e.g. {list(extra)[:3]}"
        )
    rows = [index[tid] for tid in linkage_item_ids]
    aligned = np.asarray(matrix, dtype=float)[rows]
    if aligned.ndim == 2 and aligned.shape[0] == aligned.shape[1]:
        aligned = aligned[:, rows]
    if aligned.shape[0] != len(linkage_item_ids):
        raise SystemExit(
            f"{tree_id}: aligned matrix rows {aligned.shape[0]} != {len(linkage_item_ids)}"
        )
    return aligned


def hydrate_tree(
    spec: dict[str, str],
    documents: list[Document],
) -> tuple[Tree, dict[str, Any], dict[str, str], int, dict[str, dict[str, Any]]]:
    payload = _read_json(Path(spec["labeled_json"]))
    Z = np.asarray(payload["linkage"]["z_matrix"], dtype=float)
    item_ids = list(
        payload["linkage"].get("item_ids") or payload["linkage"]["tool_ids"]
    )
    tree = Tree.from_linkage(
        Z,
        item_ids=item_ids,
        tree_id=spec["tree_id"],
        method="average",
        documents=documents,
    )
    assert_node_id_sanity(tree, payload, spec["tree_id"])
    mapping, missing_internal = label_mapping_from_source(payload)
    import_labels(tree, mapping, name=LABEL_SET_NAME, make_active=True)
    mapping[tree.root_node_id] = spec["root_label"]
    import_labels(tree, mapping, name=LABEL_SET_NAME, make_active=True)
    descriptions = node_descriptions_from_source(payload)
    return tree, payload, mapping, missing_internal, descriptions


def cut_tree(tree: Tree, spec: dict[str, str]) -> tuple[dict[str, Any], np.ndarray]:
    archive = np.load(spec["npz"])
    matrix = archive["matrix"]
    npz_tool_ids = [str(tid) for tid in archive["tool_ids"]]
    aligned = align_feature_matrix(
        matrix, npz_tool_ids, list(tree.item_ids), spec["tree_id"]
    )
    cut = build_dynamic_cut(
        tree,
        top_criterion=CUT_PARAMS["top_criterion"],
        cut_optimizer=CUT_PARAMS["cut_optimizer"],
        feature_matrix=aligned,
        cut_polarity=CUT_PARAMS["cut_polarity"],
        min_width=CUT_PARAMS["min_width"],
        max_width=CUT_PARAMS["max_width"],
        target_width=CUT_PARAMS["target_width"],
        max_depth=CUT_PARAMS["max_depth"],
        threshold_steps=CUT_PARAMS["threshold_steps"],
    )
    validate_dynamic_cut(cut, tree)
    return cut, aligned


def write_export_md(
    path: Path,
    *,
    stats: list[dict[str, Any]],
) -> None:
    lines = [
        "# AppWorld orchard export",
        "",
        "Hydrated in-memory orchard from existing AppWorld linkage and imported",
        "phase5a intrinsic labels, then cut with orchard's Calinski–Harabasz",
        "dynamic optimal cutter. Labels were not regenerated.",
        "",
        "## Sources",
        "",
        f"- Documents: `{TOOLS_JSONL.relative_to(WORKSPACE_ROOT).as_posix()}`",
        f"  ({EXPECTED_DOCUMENT_COUNT} records; `tool_id` → `item_id`/`title`,",
        "  `description` → `text`, remaining fields → `metadata`, `source=\"appworld\"`)",
    ]
    for spec in TREE_SPECS:
        lines.append(
            f"- `{spec['tree_id']}` labeled tree: "
            f"`{Path(spec['labeled_json']).relative_to(WORKSPACE_ROOT).as_posix()}`"
        )
        lines.append(
            f"- `{spec['tree_id']}` feature matrix: "
            f"`{Path(spec['npz']).relative_to(WORKSPACE_ROOT).as_posix()}` "
            "(phase3b `.npz` `matrix` + `tool_ids`, row-aligned to linkage "
            "`item_ids`; square matrices also column-permuted so the diagonal "
            "stays self-similarity / self-distance)"
        )
    lines.extend(
        [
            "",
            "## Imported labels",
            "",
            f"- Label set name: `{LABEL_SET_NAME}` (`import_labels` only; no `label_intrinsic()`)",
            "- Root overrides (same named set, roots only): domain → `domain`, "
            "function → `function`",
        ]
    )
    for row in stats:
        lines.append(
            f"- `{row['tree_id']}` internals missing an intrinsic label: "
            f"{row['missing_internal']} (no replacements invented)"
        )
        lines.append(
            f"- `{row['tree_id']}` active root label: `{row['root_label']}`"
        )
    lines.extend(
        [
            "",
            "## Cut parameters (both trees)",
            "",
            f"- `top_criterion`: `{CUT_PARAMS['top_criterion']}`",
            f"- `cut_optimizer`: `{CUT_PARAMS['cut_optimizer']}`",
            f"- `cut_polarity`: `{CUT_PARAMS['cut_polarity']}`",
            f"- `min_width`: `{CUT_PARAMS['min_width']}`",
            f"- `max_width`: `{CUT_PARAMS['max_width']}`",
            "- `target_width`: `null`",
            f"- `max_depth`: `{CUT_PARAMS['max_depth']}`",
            f"- `threshold_steps`: `{CUT_PARAMS['threshold_steps']}`",
            "- No fixed `cluster_count` cut is shipped as the optimized artifact.",
            "",
            "The dynamic cutter searches k only inside `min_width..max_width` (`3..10`).",
            "A flatter unconstrained Calinski sweep may report a different k (live",
            "notebook: 11 vs rebuilt `top_partition_count` 9 on domain). That gap is expected.",
            "",
            "## Results",
            "",
        ]
    )
    for row in stats:
        warnings = row["warnings"] or ["(none)"]
        lines.append(f"### `{row['tree_id']}`")
        lines.append("")
        lines.append(f"- `top_partition_count`: **{row['top_partition_count']}**")
        lines.append(
            f"- aligned feature matrix shape: `{row['aligned_shape']}`; "
            f"diag min/max `{row['diag_min']:.6g}` / `{row['diag_max']:.6g}`"
        )
        lines.append("- cutter `warnings`:")
        for warning in warnings:
            lines.append(f"  - {warning}")
        lines.append("")
    lines.extend(
        [
            "## Output layout",
            "",
            "```",
            "orchard-view/artifacts/appworld/",
            "  orchard/          # Orchard.save()",
            "  cuts/             # raw build_dynamic_cut JSON + provenance manifest",
            "  labels/           # imported phase5a_intrinsic mappings (post root override)",
            "  node_descriptions.json",
            "  EXPORT.md",
            "```",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main() -> int:
    documents = load_documents(TOOLS_JSONL)
    corpus_ids = {doc.item_id for doc in documents}

    trees: dict[str, Tree] = {}
    stats: list[dict[str, Any]] = []
    label_sidecars: dict[str, dict[str, str]] = {}
    node_descriptions: dict[str, dict[str, dict[str, Any]]] = {}
    cuts: dict[str, dict[str, Any]] = {}

    for spec in TREE_SPECS:
        tree_id = spec["tree_id"]
        print(f"hydrating {tree_id}...", flush=True)
        tree, _payload, mapping, missing_internal, descriptions = hydrate_tree(
            spec, documents
        )
        if set(tree.item_ids) != corpus_ids:
            raise SystemExit(
                f"{tree_id}: leaf item_ids do not match document corpus "
                f"({len(tree.item_ids)} vs {len(corpus_ids)})"
            )
        trees[tree_id] = tree
        label_sidecars[tree_id] = mapping
        node_descriptions[tree_id] = descriptions

        print(f"cutting {tree_id} (Calinski optimal)...", flush=True)
        cut, aligned = cut_tree(tree, spec)
        cuts[tree_id] = cut
        diag = np.diag(aligned) if aligned.ndim == 2 and aligned.shape[0] == aligned.shape[1] else np.array([])
        stats.append(
            {
                "tree_id": tree_id,
                "missing_internal": missing_internal,
                "root_label": tree.label_for(tree.root_node_id),
                "top_partition_count": cut["top_partition_count"],
                "warnings": list(cut.get("warnings") or []),
                "aligned_shape": list(aligned.shape),
                "diag_min": float(diag.min()) if diag.size else float("nan"),
                "diag_max": float(diag.max()) if diag.size else float("nan"),
            }
        )
        print(
            f"  {tree_id} top_partition_count={cut['top_partition_count']} "
            f"warnings={len(cut.get('warnings') or [])}",
            flush=True,
        )

    domain_count = next(row["top_partition_count"] for row in stats if row["tree_id"] == "domain")
    if domain_count in {2, 25} or domain_count < 3 or domain_count > 20:
        raise SystemExit(
            f"domain top_partition_count={domain_count} is wildly different from the "
            "live-notebook rebuild (9). Check matrix alignment before shipping."
        )

    orchard = Orchard.from_trees(
        documents=documents,
        trees=trees,
        metadata={
            "source": SOURCE_NAME,
            "label_set": LABEL_SET_NAME,
            "notes": "hydrated from phase5a labeled trees + phase3b matrices; labels imported not regenerated",
        },
    )
    orchard_dir = OUT_ROOT / "orchard"
    print(f"saving orchard to {orchard_dir}...", flush=True)
    orchard.save(orchard_dir)

    cuts_dir = OUT_ROOT / "cuts"
    for tree_id, cut in cuts.items():
        _write_json(cuts_dir / f"{tree_id}.calinski_optimal.json", cut)
    _write_json(
        cuts_dir / "manifest.json",
        {
            "top_criterion": CUT_PARAMS["top_criterion"],
            "cut_optimizer": CUT_PARAMS["cut_optimizer"],
            "cut_polarity": CUT_PARAMS["cut_polarity"],
            "min_width": CUT_PARAMS["min_width"],
            "max_width": CUT_PARAMS["max_width"],
            "target_width": CUT_PARAMS["target_width"],
            "max_depth": CUT_PARAMS["max_depth"],
            "threshold_steps": CUT_PARAMS["threshold_steps"],
            "feature_matrix": (
                "matching phase3b profile, row-aligned to linkage item_ids; "
                "square matrices also column-permuted"
            ),
            "label_set": LABEL_SET_NAME,
            "root_overrides": {"domain": "domain", "function": "function"},
            "trees": {
                row["tree_id"]: {
                    "top_partition_count": row["top_partition_count"],
                    "warnings": row["warnings"],
                    "aligned_shape": row["aligned_shape"],
                    "internals_missing_label": row["missing_internal"],
                }
                for row in stats
            },
            "sources": {
                "tools_jsonl": TOOLS_JSONL.relative_to(WORKSPACE_ROOT).as_posix(),
                "trees": {
                    spec["tree_id"]: {
                        "labeled_json": Path(spec["labeled_json"])
                        .relative_to(WORKSPACE_ROOT)
                        .as_posix(),
                        "npz": Path(spec["npz"]).relative_to(WORKSPACE_ROOT).as_posix(),
                    }
                    for spec in TREE_SPECS
                },
            },
        },
        sort_keys=True,
    )

    labels_dir = OUT_ROOT / "labels"
    for tree_id, mapping in label_sidecars.items():
        _write_json(
            labels_dir / f"{tree_id}.{LABEL_SET_NAME}.json",
            {
                "name": LABEL_SET_NAME,
                "tree_id": tree_id,
                "labels": mapping,
            },
            sort_keys=True,
        )
    _write_json(OUT_ROOT / "node_descriptions.json", node_descriptions)
    write_export_md(OUT_ROOT / "EXPORT.md", stats=stats)
    print(f"wrote packet under {OUT_ROOT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
