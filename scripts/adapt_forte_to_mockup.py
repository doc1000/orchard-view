"""Adapt Forte orchard cuts into the visual-search mockup JS shape.

semantic → domain slot, CODE → function slot.
Read-only over artifacts/forte_blogs/{cuts,orchard}. Writes view/mockup_data.js
and packs standalone HTML.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

VIEW_ROOT = Path(__file__).resolve().parents[1]
PACKET = VIEW_ROOT / "artifacts" / "forte_blogs"
OUT_PATH = PACKET / "view" / "mockup_data.js"

EXPECTED_DOCS = 279
LABEL_SET_NAME = "gpt41mini"
HASH_SEGMENT_LEN = 8


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _short_hash(canonical_node_id: str) -> str:
    digest = canonical_node_id.removeprefix("member_")
    if len(digest) < HASH_SEGMENT_LEN:
        raise SystemExit(f"canonical id too short for a view slug: {canonical_node_id}")
    return digest[:HASH_SEGMENT_LEN]


def _view_id(tree_letter: str, segments: list[str]) -> str:
    return tree_letter + "/" + "/".join(segments)


def _leaf_item_ids(canonical: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for node_id, node in canonical["nodes"].items():
        if node.get("kind") != "leaf":
            continue
        item_id = node.get("item_id")
        if not item_id:
            raise SystemExit(f"leaf {node_id} has no item_id")
        mapping[node_id] = str(item_id)
    return mapping


def _adapt_tree(
    cut_root: dict[str, Any],
    *,
    tree_letter: str,
    labels: dict[str, str],
    leaf_item_ids: dict[str, str],
    docs_by_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, str], dict[str, str]]:
    """Return (mockup tree, item_id → leaf view id, item_id → domain path)."""

    item_to_view: dict[str, str] = {}
    item_to_path: dict[str, str] = {}
    used_ids: set[str] = set()

    def register(view_id: str, canonical_id: str) -> None:
        if view_id in used_ids:
            raise SystemExit(
                f"duplicate view id {view_id!r} (canonical {canonical_id})"
            )
        used_ids.add(view_id)

    def make_leaf(
        canonical_id: str,
        parent_segments: list[str],
        ancestor_labels: list[str],
    ) -> dict[str, Any]:
        item_id = leaf_item_ids.get(canonical_id)
        if item_id is None:
            raise SystemExit(f"cut leaf {canonical_id} is not in canonical_tree")
        doc = docs_by_id.get(item_id)
        if doc is None:
            raise SystemExit(f"cut leaf {canonical_id} item {item_id} missing from documents")
        segments = parent_segments + [_short_hash(canonical_id)]
        view_id = _view_id(tree_letter, segments)
        register(view_id, canonical_id)
        label = str(doc.get("title") or item_id)
        if item_id in item_to_view:
            raise SystemExit(f"item {item_id} mapped to two leaves")
        item_to_view[item_id] = view_id
        trail = ancestor_labels + [label]
        item_to_path[item_id] = " → ".join(trail)
        return {"id": view_id, "label": label, "count": 1, "children": []}

    def walk(
        node: dict[str, Any],
        parent_segments: list[str],
        ancestor_labels: list[str],
        *,
        is_root: bool,
    ) -> dict[str, Any]:
        canonical_id = node["canonical_node_id"]
        if is_root:
            view_id = "root"
            label = "All Documents"
            child_segments: list[str] = []
            child_labels: list[str] = []
        else:
            child_segments = parent_segments + [_short_hash(canonical_id)]
            view_id = _view_id(tree_letter, child_segments)
            label = labels.get(canonical_id)
            if not label:
                raise SystemExit(f"missing {LABEL_SET_NAME} label for {canonical_id}")
            child_labels = ancestor_labels + [label]
        register(view_id, canonical_id)

        children: list[dict[str, Any]] = []
        for leaf_id in node.get("direct_leaf_node_ids") or []:
            children.append(make_leaf(leaf_id, child_segments, child_labels))
        for child in node.get("children") or []:
            children.append(walk(child, child_segments, child_labels, is_root=False))

        if not children:
            raise SystemExit(
                f"cut node {canonical_id} has no children or direct_leaf_node_ids"
            )

        return {
            "id": view_id,
            "label": label,
            "count": int(node["descendant_count"]),
            "children": children,
        }

    tree = walk(cut_root, [], [], is_root=True)
    return tree, item_to_view, item_to_path


def _collect_leaves(node: dict[str, Any], acc: list[str] | None = None) -> list[str]:
    found = acc if acc is not None else []
    children = node.get("children") or []
    if not children:
        found.append(node["id"])
        return found
    for child in children:
        _collect_leaves(child, found)
    return found


def _doc_body(doc: dict[str, Any]) -> str:
    return str(doc.get("text") or "")


def _update_forte_html(semantic_top: int) -> None:
    path = VIEW_ROOT / "visual_search_forte.html"
    text = path.read_text(encoding="utf-8")
    updated, count_n = re.subn(
        r"279 docs · \d+ top-level clusters",
        f"279 docs · {semantic_top} top-level clusters",
        text,
        count=1,
    )
    if count_n != 1:
        raise SystemExit("could not update live top-level cluster count in HTML")
    updated = updated.replace(
        "Semantic tree = TF-IDF clusters. CODE tree = Capture / Organize / Distill / Express.",
        "Semantic tree = MiniLM 0.66 / TF-IDF 0.34. CODE tree = Capture / Organize / Distill / Express.",
    )
    path.write_text(updated, encoding="utf-8", newline="\n")


def _standalone_d3_src() -> Path:
    matches = sorted(
        (VIEW_ROOT / "artifacts" / "appworld" / "standalone").glob("*/d3.min.js")
    )
    if not matches:
        raise SystemExit("AppWorld standalone d3.min.js not found")
    return matches[-1]


def pack_standalone() -> Path:
    stamp = datetime.now().strftime("%Y%d%m%H%M")
    standalone_root = PACKET / "standalone"
    if standalone_root.is_dir():
        shutil.rmtree(standalone_root)
    dest = standalone_root / f"orchard_view_forte_{stamp}"
    dest.mkdir(parents=True)
    html = (VIEW_ROOT / "visual_search_forte.html").read_text(encoding="utf-8")
    html = html.replace(
        'src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"',
        'src="d3.min.js"',
    )
    html = html.replace(
        'src="artifacts/forte_blogs/view/mockup_data.js"',
        'src="mockup_data.js"',
    )
    if 'src="d3.min.js"' not in html or 'src="mockup_data.js"' not in html:
        raise SystemExit("standalone HTML still has remote or nested script src")
    (dest / "visual_search_forte.html").write_text(html, encoding="utf-8", newline="\n")
    shutil.copy2(OUT_PATH, dest / "mockup_data.js")
    shutil.copy2(_standalone_d3_src(), dest / "d3.min.js")
    return dest


def main() -> int:
    documents = _read_json(PACKET / "orchard" / "documents.json")
    if not isinstance(documents, list):
        raise SystemExit("documents.json is not a list")
    docs_by_id: dict[str, dict[str, Any]] = {}
    for doc in documents:
        item_id = str(doc["item_id"])
        if item_id in docs_by_id:
            raise SystemExit(f"duplicate document item_id {item_id}")
        docs_by_id[item_id] = doc

    semantic_labels = _read_json(
        PACKET / "orchard" / "trees" / "semantic" / "labels" / f"{LABEL_SET_NAME}.json"
    )["labels"]
    code_labels = _read_json(
        PACKET / "orchard" / "trees" / "CODE" / "labels" / f"{LABEL_SET_NAME}.json"
    )["labels"]
    leaf_item_ids = _leaf_item_ids(
        _read_json(PACKET / "orchard" / "trees" / "semantic" / "canonical_tree.json")
    )
    semantic_cut = _read_json(PACKET / "cuts" / "semantic.calinski_optimal.json")
    code_cut = _read_json(PACKET / "cuts" / "CODE.calinski_optimal.json")

    domain_tree, domain_item_view, domain_item_path = _adapt_tree(
        semantic_cut["root"],
        tree_letter="d",
        labels=semantic_labels,
        leaf_item_ids=leaf_item_ids,
        docs_by_id=docs_by_id,
    )
    function_tree, function_item_view, _ = _adapt_tree(
        code_cut["root"],
        tree_letter="f",
        labels=code_labels,
        leaf_item_ids=leaf_item_ids,
        docs_by_id=docs_by_id,
    )

    mockup_docs: list[dict[str, Any]] = []
    for item_id, doc in docs_by_id.items():
        dom = domain_item_view.get(item_id)
        fn = function_item_view.get(item_id)
        if not dom or not fn:
            raise SystemExit(f"document {item_id} missing domCluster or fnCluster")
        mockup_docs.append(
            {
                "id": item_id,
                "title": str(doc.get("title") or item_id),
                "domCluster": dom,
                "fnCluster": fn,
                "path": domain_item_path[item_id],
                "body": _doc_body(doc),
            }
        )

    domain_leaves = _collect_leaves(domain_tree)
    function_leaves = _collect_leaves(function_tree)
    referenced_dom = {d["domCluster"] for d in mockup_docs}
    referenced_fn = {d["fnCluster"] for d in mockup_docs}
    semantic_top = int(semantic_cut["top_partition_count"])
    code_top = int(code_cut["top_partition_count"])

    failures: list[str] = []
    if len(mockup_docs) != EXPECTED_DOCS:
        failures.append(f"doc count {len(mockup_docs)} != {EXPECTED_DOCS}")
    if any(not d["domCluster"] or not d["fnCluster"] for d in mockup_docs):
        failures.append("some docs missing domCluster/fnCluster")
    unused_dom = set(domain_leaves) - referenced_dom
    unused_fn = set(function_leaves) - referenced_fn
    if unused_dom:
        failures.append(f"{len(unused_dom)} semantic leaves unreferenced")
    if unused_fn:
        failures.append(f"{len(unused_fn)} CODE leaves unreferenced")
    if len(domain_tree["children"]) != semantic_top:
        failures.append(
            f"semantic root children {len(domain_tree['children'])} != {semantic_top}"
        )
    if len(function_tree["children"]) != code_top:
        failures.append(
            f"CODE root children {len(function_tree['children'])} != {code_top}"
        )
    if failures:
        raise SystemExit("sanity failed:\n  " + "\n  ".join(failures))

    js = (
        "// Generated by scripts/adapt_forte_to_mockup.py — do not edit.\n"
        "const DOMAIN_TREE = "
        + json.dumps(domain_tree, ensure_ascii=False)
        + ";\n"
        "const FUNCTION_TREE = "
        + json.dumps(function_tree, ensure_ascii=False)
        + ";\n"
        "const TREES = { domain: DOMAIN_TREE, function: FUNCTION_TREE };\n"
        "const DOCS = "
        + json.dumps(mockup_docs, ensure_ascii=False)
        + ";\n"
    )
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(js, encoding="utf-8", newline="\n")
    _update_forte_html(semantic_top)
    packed = pack_standalone()
    print(
        f"wrote {OUT_PATH.relative_to(VIEW_ROOT)} "
        f"({EXPECTED_DOCS} docs, semantic top={semantic_top}, "
        f"CODE top={code_top})"
    )
    print(f"packed {packed.relative_to(VIEW_ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
