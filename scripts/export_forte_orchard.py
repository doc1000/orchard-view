"""Build the Forte blogs orchard: CODE taxonomy + semantic TF-IDF, Calinski cuts, labels.

orchard/ is import-only. Training chunks are not orchard leaves.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from dotenv import load_dotenv

from orchard import (
    Document,
    Orchard,
    OrchardBuilder,
    TaxonomyModel,
    Tree,
    build_dynamic_cut,
    import_labels,
    validate_dynamic_cut,
)
from orchard.backends.tfidf import TfidfEmbeddingBackend

VIEW_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = VIEW_ROOT.parent
POSTS_DIR = (
    WORKSPACE_ROOT
    / "forte_second_brain_scraper"
    / "forte-building-a-second-brain"
    / "posts"
)
SEED_YAML = VIEW_ROOT / "artifacts" / "forte_blogs" / "code_taxonomy_seed.yaml"
OUT_ROOT = VIEW_ROOT / "artifacts" / "forte_blogs"

EXPECTED_DOCUMENT_COUNT = 279
SOURCE_NAME = "forte_blogs"
LABEL_SET_NAME = "gpt41mini"
LABEL_MODEL = "gpt-4.1-mini-2025-04-14"
GOLD_STEM = "0027-building-a-second-brain-the-definitive-introductory-guide"
CODE_STAGES = ("capture", "organize", "distill", "express")

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

HEADING_LINE_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
STAGE_WORD_RE = re.compile(r"\b(capture|organize|distill|express)\b", re.IGNORECASE)
CUE_TOKEN_RE = re.compile(r"[a-z0-9]+")
TYPICAL_ACTIONS_RE = re.compile(r"typical actions include\s+(.+)", re.IGNORECASE | re.DOTALL)


def _write_json(path: Path, value: Any, *, sort_keys: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=sort_keys) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _slug(text: str) -> str:
    tokens = CUE_TOKEN_RE.findall(text.casefold())
    return "-".join(tokens[:8]) or "section"


def load_posts(posts_dir: Path) -> list[Document]:
    paths = sorted(posts_dir.glob("*.md"))
    if len(paths) != EXPECTED_DOCUMENT_COUNT:
        raise SystemExit(
            f"expected {EXPECTED_DOCUMENT_COUNT} markdown posts, got {len(paths)}"
        )
    documents: list[Document] = []
    for path in paths:
        raw = path.read_text(encoding="utf-8")
        meta, body = _split_frontmatter(raw)
        title = str(meta.get("title") or "").strip() or path.stem
        text = body.strip() or title
        documents.append(
            Document(
                text=text,
                item_id=path.stem,
                title=title,
                metadata=_jsonable(meta),
                source=SOURCE_NAME,
            )
        )
    return documents


def _split_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    if not raw.startswith("---"):
        return {}, raw
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw
    loaded = yaml.safe_load(parts[1])
    meta = loaded if isinstance(loaded, dict) else {}
    return meta, parts[2].lstrip("\n")


def cues_from_label(row: dict[str, Any]) -> list[str]:
    features = row.get("distinguishing_features") or []
    for feature in features:
        match = TYPICAL_ACTIONS_RE.search(str(feature))
        if match:
            tokens = CUE_TOKEN_RE.findall(match.group(1).casefold())
            return [token for token in tokens if token not in {"or", "and", "the", "a"}]
    return []


def yaml_to_definition(seed: dict[str, Any]) -> dict[str, Any]:
    taxonomy = seed["taxonomy"]
    labels = []
    for row in taxonomy["labels"]:
        labels.append(
            {
                "label_id": row["id"],
                "name": row["label"],
                "definition": str(row["definition"]).strip(),
                "cues": cues_from_label(row),
            }
        )
    order = [row["label_id"] for row in labels]
    if tuple(order) != CODE_STAGES:
        raise SystemExit(f"label_order {order} != {list(CODE_STAGES)}")
    return {
        "schema_version": "orchard_taxonomy_definition_v1",
        "name": "CODE",
        "taxonomy_version": "orchard_taxonomy_v1",
        "structure": "flat",
        "provenance": (
            "Converted from artifacts/forte_blogs/code_taxonomy_seed.yaml "
            "(Tiago Forte CODE; cues from typical-action phrases)"
        ),
        "label_order": list(CODE_STAGES),
        "labels": labels,
    }


def _heading_sections(body: str) -> list[tuple[int, str, str]]:
    lines = body.splitlines()
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = HEADING_LINE_RE.match(line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2).strip()))
    sections: list[tuple[int, str, str]] = []
    for idx, (line_index, level, title) in enumerate(headings):
        end = headings[idx + 1][0] if idx + 1 < len(headings) else len(lines)
        section_body = "\n".join(lines[line_index + 1 : end]).strip()
        sections.append((level, title, section_body))
    return sections


def _single_stage(heading: str) -> str | None:
    found = [match.group(1).casefold() for match in STAGE_WORD_RE.finditer(heading)]
    unique = list(dict.fromkeys(found))
    if len(unique) != 1:
        return None
    return unique[0]


def collect_training(
    seed: dict[str, Any],
    posts_dir: Path,
) -> tuple[list[Document], dict[str, str], list[dict[str, Any]]]:
    documents: list[Document] = []
    labels_by_item_id: dict[str, str] = {}
    manifest: list[dict[str, Any]] = []

    for row in seed["taxonomy"]["labels"]:
        label_id = str(row["id"])
        for index, chunk in enumerate(row.get("training_chunks") or []):
            item_id = f"seed.{label_id}.{index}"
            text = str(chunk).strip()
            documents.append(
                Document(
                    text=text,
                    item_id=item_id,
                    title=f"{row['label']} seed {index}",
                    metadata={"source": "yaml_chunk", "label": label_id},
                    source=SOURCE_NAME,
                )
            )
            labels_by_item_id[item_id] = label_id
            manifest.append(
                {
                    "item_id": item_id,
                    "label": label_id,
                    "source": "yaml_chunk",
                    "path": None,
                    "heading": None,
                }
            )

    gold_labels: set[str] = set()
    for path in sorted(posts_dir.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        _meta, body = _split_frontmatter(raw)
        rel = path.relative_to(posts_dir.parent).as_posix()
        for level, heading, section_body in _heading_sections(body):
            if level > 3:
                continue
            stage = _single_stage(heading)
            if stage is None or not section_body:
                continue
            item_id = f"{path.stem}.h{level}.{_slug(heading)}"
            if item_id in labels_by_item_id:
                item_id = f"{item_id}.{len(labels_by_item_id)}"
            text = f"{heading}\n\n{section_body}"
            documents.append(
                Document(
                    text=text,
                    item_id=item_id,
                    title=heading,
                    metadata={
                        "source": "heading_section",
                        "label": stage,
                        "path": rel,
                        "heading": heading,
                    },
                    source=SOURCE_NAME,
                )
            )
            labels_by_item_id[item_id] = stage
            manifest.append(
                {
                    "item_id": item_id,
                    "label": stage,
                    "source": "heading_section",
                    "path": rel,
                    "heading": heading,
                }
            )
            if path.stem == GOLD_STEM:
                gold_labels.add(stage)

    if gold_labels != set(CODE_STAGES):
        raise SystemExit(
            f"gold post {GOLD_STEM} heading stages {sorted(gold_labels)} "
            f"!= {list(CODE_STAGES)}"
        )
    return documents, labels_by_item_id, manifest


def documents_in_item_order(
    documents: list[Document], item_ids: list[str]
) -> list[Document]:
    by_id = {doc.item_id: doc for doc in documents}
    missing = [item_id for item_id in item_ids if item_id not in by_id]
    if missing:
        raise SystemExit(f"{len(missing)} item_ids missing from documents, e.g. {missing[:3]}")
    return [by_id[item_id] for item_id in item_ids]


def semantic_feature_matrix(documents: list[Document], item_ids: list[str]) -> np.ndarray:
    ordered = documents_in_item_order(documents, item_ids)
    return np.asarray(
        TfidfEmbeddingBackend().encode([doc.text for doc in ordered]),
        dtype=np.float64,
    )


def code_feature_matrix(
    taxonomy: TaxonomyModel, documents: list[Document], item_ids: list[str]
) -> np.ndarray:
    ordered = documents_in_item_order(documents, item_ids)
    return np.asarray(taxonomy.transform(ordered), dtype=np.float64)


def cut_tree(tree: Tree, feature_matrix: np.ndarray) -> dict[str, Any]:
    if feature_matrix.shape[0] != len(tree.item_ids):
        raise SystemExit(
            f"{tree.tree_id}: feature rows {feature_matrix.shape[0]} != {len(tree.item_ids)}"
        )
    cut = build_dynamic_cut(
        tree,
        top_criterion=CUT_PARAMS["top_criterion"],
        cut_optimizer=CUT_PARAMS["cut_optimizer"],
        feature_matrix=feature_matrix,
        cut_polarity=CUT_PARAMS["cut_polarity"],
        min_width=CUT_PARAMS["min_width"],
        max_width=CUT_PARAMS["max_width"],
        target_width=CUT_PARAMS["target_width"],
        max_depth=CUT_PARAMS["max_depth"],
        threshold_steps=CUT_PARAMS["threshold_steps"],
    )
    validate_dynamic_cut(cut, tree)
    return cut


def cut_internal_ids(cut_root: dict[str, Any]) -> list[str]:
    ids: list[str] = []

    def walk(node: dict[str, Any]) -> None:
        ids.append(node["canonical_node_id"])
        for child in node.get("children") or []:
            walk(child)

    walk(cut_root)
    return ids


def _openai_key_present() -> bool:
    load_dotenv(VIEW_ROOT / ".env", override=True)
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def _leaf_title_labels(tree: Tree) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for node_id, node in tree.nodes.items():
        if node.get("kind") != "leaf":
            continue
        item_id = node["item_id"]
        doc = tree.documents_by_id.get(item_id)
        mapping[node_id] = (doc.title if doc and doc.title.strip() else item_id)
    return mapping


def _cluster_titles(tree: Tree, node_id: str, *, limit: int = 24) -> list[str]:
    node = tree.nodes[node_id]
    titles: list[str] = []
    for item_id in node["descendant_item_ids"]:
        doc = tree.documents_by_id.get(item_id)
        titles.append((doc.title if doc and doc.title.strip() else item_id))
        if len(titles) >= limit:
            break
    return titles


def label_cut_internals(
    tree: Tree,
    cut: dict[str, Any],
    *,
    cache_dir: Path,
) -> tuple[dict[str, str], int]:
    from openai import OpenAI

    client = OpenAI()
    internal_ids = cut_internal_ids(cut["root"])
    raw_dir = cache_dir / "raw" / tree.tree_id
    raw_dir.mkdir(parents=True, exist_ok=True)

    mapping = _leaf_title_labels(tree)
    called = 0
    for node_id in internal_ids:
        cache_path = raw_dir / f"{node_id}.json"
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            label = str(cached.get("label") or "").strip()
            if label:
                mapping[node_id] = label
                continue
        titles = _cluster_titles(tree, node_id)
        node = tree.nodes[node_id]
        user = (
            f"Tree: {tree.tree_id}\n"
            f"Posts in cluster: {node['descendant_count']}\n"
            "Sample titles:\n"
            + "\n".join(f"- {title}" for title in titles)
        )
        response = client.chat.completions.create(
            model=LABEL_MODEL,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You name clusters of Tiago Forte blog posts about "
                        "Building a Second Brain. Reply with only a 2-6 word "
                        "noun phrase. No quotes or explanation."
                    ),
                },
                {"role": "user", "content": user},
            ],
        )
        called += 1
        raw_text = (response.choices[0].message.content or "").strip()
        label = _clean_label(raw_text)
        cache_path.write_text(
            json.dumps(
                {
                    "node_id": node_id,
                    "model": LABEL_MODEL,
                    "label": label,
                    "raw_text": raw_text,
                    "usage": {
                        "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
                        "completion_tokens": getattr(
                            response.usage, "completion_tokens", None
                        ),
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        mapping[node_id] = label
        safe_label = label.encode("ascii", "replace").decode("ascii")
        print(
            f"  labeled {tree.tree_id} {node_id[:16]}... -> {safe_label}",
            flush=True,
        )

    if tree.tree_id == "semantic":
        mapping[tree.root_node_id] = "semantic"
    else:
        mapping[tree.root_node_id] = "CODE"
    return mapping, called


def _clean_label(text: str) -> str:
    cleaned = text.strip().strip("\"'`").splitlines()[0].strip()
    words = [token for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", cleaned)]
    if not words:
        return "untitled cluster"
    clipped = " ".join(words[:6])
    if len(words) < 2:
        return clipped
    return clipped


def write_export_md(
    path: Path,
    *,
    training_manifest: list[dict[str, Any]],
    stats: list[dict[str, Any]],
    labeled: bool,
    label_calls: int,
) -> None:
    yaml_n = sum(1 for row in training_manifest if row["source"] == "yaml_chunk")
    heading_n = sum(1 for row in training_manifest if row["source"] == "heading_section")
    lines = [
        "# Forte blogs orchard export",
        "",
        "Built a semantic TF-IDF tree and a CODE taxonomy tree over 279 Forte Labs",
        '"Building a Second Brain" posts. CODE was fit with TaxonomyModel.fit() on',
        "synthetic YAML chunks plus heading-explicit real sections. Both trees were",
        "cut with the AppWorld Calinski-optimal parameters.",
        (
            f"Cut-visible internals were labeled with `{LABEL_MODEL}`."
            if labeled
            else "Cut-visible internals were not labeled (OPENAI_API_KEY missing)."
        ),
        "",
        "## Sources",
        "",
        f"- Documents: `{POSTS_DIR.relative_to(WORKSPACE_ROOT).as_posix()}`",
        f"  ({EXPECTED_DOCUMENT_COUNT} markdown posts; stem → `item_id`,",
        "  frontmatter title → `title`, body → `text`, `source=\"forte_blogs\"`)",
        "- CODE seed: `orchard-view/artifacts/forte_blogs/code_taxonomy_seed.yaml`",
        "- Converted definition: `orchard-view/artifacts/forte_blogs/code_taxonomy.json`",
        "",
        "## CODE training",
        "",
        f"- Synthetic YAML chunks: {yaml_n}",
        f"- Heading-explicit sections (H1–H3, single CODE stage word): {heading_n}",
        f"- Training items total: {len(training_manifest)}",
        "- Synthetic chunks are training-only and are not orchard leaves.",
        f"- Gold post `{GOLD_STEM}` contributed all four CODE stages.",
        "- Fitted classifier `transform()`s the full 279-post corpus.",
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
        "",
        "## Labels",
        "",
        f"- Label set name: `{LABEL_SET_NAME}`",
        f"- Model: `{LABEL_MODEL}` (temperature 0) on cut-visible internals only",
        "- Leaves keep post titles",
        f"- API calls this run: {label_calls}" if labeled else "- API calls this run: 0 (skipped)",
        "",
        "## Results",
        "",
    ]
    for row in stats:
        warnings = row["warnings"] or ["(none)"]
        lines.append(f"### `{row['tree_id']}`")
        lines.append("")
        lines.append(f"- `top_partition_count`: **{row['top_partition_count']}**")
        lines.append(
            f"- aligned feature matrix shape: `{row['aligned_shape']}`; "
            f"diag min/max `{row['diag_min']:.6g}` / `{row['diag_max']:.6g}`"
        )
        lines.append(f"- cut-visible internals labeled: {row['internal_count']}")
        lines.append("- cutter `warnings`:")
        for warning in warnings:
            lines.append(f"  - {warning}")
        lines.append("")
    lines.extend(
        [
            "## Output layout",
            "",
            "```",
            "orchard-view/artifacts/forte_blogs/",
            "  code_taxonomy.json",
            "  training/manifest.json",
            "  orchard/          # Orchard.save()",
            "  cuts/             # semantic + CODE Calinski-optimal JSON",
            "  labels/           # gpt-4.1-mini mappings + raw response cache",
            "  node_descriptions.json",
            "  view/mockup_data.js",
            "  standalone/orchard_view_forte_<stamp>/",
            "  EXPORT.md",
            "```",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main() -> int:
    print("loading posts...", flush=True)
    documents = load_posts(POSTS_DIR)
    seed = yaml.safe_load(SEED_YAML.read_text(encoding="utf-8"))
    definition = yaml_to_definition(seed)
    _write_json(OUT_ROOT / "code_taxonomy.json", definition, sort_keys=True)

    print("collecting CODE training items...", flush=True)
    train_docs, train_labels, train_manifest = collect_training(seed, POSTS_DIR)
    _write_json(
        OUT_ROOT / "training" / "manifest.json",
        {
            "document_count": EXPECTED_DOCUMENT_COUNT,
            "training_item_count": len(train_manifest),
            "items": train_manifest,
        },
    )
    print(
        f"  {len(train_manifest)} training items "
        f"({sum(1 for row in train_manifest if row['source'] == 'yaml_chunk')} yaml, "
        f"{sum(1 for row in train_manifest if row['source'] == 'heading_section')} headings)",
        flush=True,
    )

    print("fitting CODE TaxonomyModel...", flush=True)
    fitted_code = TaxonomyModel.from_definition(definition).fit(train_docs, train_labels)

    print("building orchard (semantic + CODE)...", flush=True)
    orchard = OrchardBuilder(
        taxonomies=[fitted_code],
        include_semantic_with_taxonomies=True,
        metadata={"source": SOURCE_NAME, "label_set": LABEL_SET_NAME},
    ).build(documents)
    if set(orchard.trees) != {"semantic", "CODE"}:
        raise SystemExit(f"unexpected trees: {sorted(orchard.trees)}")
    if len(orchard.documents) != EXPECTED_DOCUMENT_COUNT:
        raise SystemExit(f"orchard has {len(orchard.documents)} docs")

    cuts: dict[str, dict[str, Any]] = {}
    matrices: dict[str, np.ndarray] = {}
    stats: list[dict[str, Any]] = []
    for tree_id in ("semantic", "CODE"):
        tree = orchard.tree(tree_id)
        print(f"cutting {tree_id} (Calinski optimal)...", flush=True)
        if tree_id == "semantic":
            matrix = semantic_feature_matrix(documents, list(tree.item_ids))
        else:
            matrix = code_feature_matrix(fitted_code, documents, list(tree.item_ids))
        cut = cut_tree(tree, matrix)
        cuts[tree_id] = cut
        matrices[tree_id] = matrix
        diag = (
            np.diag(matrix)
            if matrix.ndim == 2 and matrix.shape[0] == matrix.shape[1]
            else np.array([])
        )
        internal_ids = cut_internal_ids(cut["root"])
        stats.append(
            {
                "tree_id": tree_id,
                "top_partition_count": cut["top_partition_count"],
                "warnings": list(cut.get("warnings") or []),
                "aligned_shape": list(matrix.shape),
                "diag_min": float(diag.min()) if diag.size else float("nan"),
                "diag_max": float(diag.max()) if diag.size else float("nan"),
                "internal_count": len(internal_ids),
            }
        )
        print(
            f"  {tree_id} top_partition_count={cut['top_partition_count']} "
            f"internals={len(internal_ids)} warnings={len(cut.get('warnings') or [])}",
            flush=True,
        )

    cuts_dir = OUT_ROOT / "cuts"
    for tree_id, cut in cuts.items():
        _write_json(cuts_dir / f"{tree_id}.calinski_optimal.json", cut)

    labeled = False
    label_calls = 0
    node_descriptions: dict[str, dict[str, dict[str, Any]]] = {}
    if not _openai_key_present():
        print(
            "OPENAI_API_KEY missing; writing trees/cuts without LLM labels. "
            "HTML deliverable requires labels.",
            flush=True,
        )
    else:
        labels_dir = OUT_ROOT / "labels"
        try:
            for tree_id in ("semantic", "CODE"):
                tree = orchard.tree(tree_id)
                print(f"labeling {tree_id} cut internals with {LABEL_MODEL}...", flush=True)
                mapping, called = label_cut_internals(
                    tree, cuts[tree_id], cache_dir=labels_dir
                )
                label_calls += called
                import_labels(tree, mapping, name=LABEL_SET_NAME, make_active=True)
                _write_json(
                    labels_dir / f"{tree_id}.{LABEL_SET_NAME}.json",
                    {"name": LABEL_SET_NAME, "tree_id": tree_id, "labels": mapping},
                    sort_keys=True,
                )
                descriptions: dict[str, dict[str, Any]] = {}
                for node_id in cut_internal_ids(cuts[tree_id]["root"]):
                    descriptions[node_id] = {
                        "label": mapping.get(node_id),
                        "descendant_count": tree.nodes[node_id]["descendant_count"],
                    }
                node_descriptions[tree_id] = descriptions
            labeled = True
        except Exception as exc:
            detail = str(exc).encode("ascii", "replace").decode("ascii")
            print(
                f"labeling failed ({type(exc).__name__}: {detail}); "
                "writing trees/cuts without LLM labels. HTML deliverable requires labels.",
                flush=True,
            )

    orchard_dir = OUT_ROOT / "orchard"
    print(f"saving orchard to {orchard_dir}...", flush=True)
    orchard.save(orchard_dir)
    _write_json(OUT_ROOT / "node_descriptions.json", node_descriptions)
    write_export_md(
        OUT_ROOT / "EXPORT.md",
        training_manifest=train_manifest,
        stats=stats,
        labeled=labeled,
        label_calls=label_calls,
    )
    print(f"wrote packet under {OUT_ROOT}", flush=True)
    if not labeled:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
