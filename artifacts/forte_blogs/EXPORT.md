# Forte blogs orchard export

Built a fused MiniLM/TF-IDF semantic tree and a fused CODE taxonomy tree
over 279 Forte Labs "Building a Second Brain" posts. CODE was trained as
ModernBERT + logistic (`HEAD_HYPERPARAMS`); `TaxonomyModel.fit()` was not
called. Both trees were cut on the fused dissimilarity that produced each
tree's linkage (AppWorld Calinski-optimal parameters).
Cut-visible internals were labeled with `gpt-4.1-mini-2025-04-14`.

## Sources

- Documents: `forte_second_brain_scraper/forte-building-a-second-brain/posts`
  (279 markdown posts; stem → `item_id`,
  frontmatter title → `title`, body → `text`, `source="forte_blogs"`)
- CODE seed: `orchard-view/artifacts/forte_blogs/code_taxonomy_seed.yaml`
- Converted definition: `orchard-view/artifacts/forte_blogs/code_taxonomy.json`
- CODE head: `orchard-view/artifacts/forte_blogs/code_head.npz`

## Fusion

- `taxonomy_transform`: `modernbert_logistic`
- `fusion_mode`: `variance_calibrated`
- `embedding_backend`: `MiniLMEmbeddingBackend`
- `offline_fallback`: `False`
- Semantic weights (library default): `description_minilm_centered_cosine` **0.66**, `tfidf_cosine` **0.34**
- CODE weights (explicit; not packaged domain/function dicts): `CODE_raw_js` **0.5**, `description_minilm_centered_cosine` **0.3**, `tfidf_cosine` **0.2**
- Cuts used `fuse_to_dissimilarity` on the builder's shared `layer_matrices`
  with that tree's profile weights and `fusion_mode`. Not raw TF-IDF and
  not raw CODE probability rows.

## CODE training

- Synthetic YAML chunks: 20
- Heading-explicit sections (H1–H3, single CODE stage word): 25
- Training items total: 45
- Synthetic chunks are training-only and are not orchard leaves.
- Gold post `0027-building-a-second-brain-the-definitive-introductory-guide` contributed all four CODE stages.
- Fitted ModernBERT logistic `transform()`s the full 279-post corpus.
- Logistic hyperparameters: `{'C': 0.1, 'class_weight': 'balanced', 'max_iter': 1000, 'random_state': 20260725}`

## Cut parameters (both trees)

- `top_criterion`: `optimal`
- `cut_optimizer`: `calinski_harabasz_score`
- `cut_polarity`: `1`
- `min_width`: `3`
- `max_width`: `10`
- `target_width`: `null`
- `max_depth`: `5`
- `threshold_steps`: `32`

## Labels

- Label set name: `gpt41mini`
- Model: `gpt-4.1-mini-2025-04-14` (temperature 0) on cut-visible internals only
- Leaves keep post titles
- API calls this run: 130

## Results

### `semantic`

- `top_partition_count`: **3**
- aligned fused D shape: `[279, 279]`; diag min/max `0` / `0`
- cut-visible internals labeled: 65
- cutter `warnings`:
  - member_d487359888738487bce30a32fb4f59c5cdda6b6b6cad287d9507349f543ad00e retains 18 leaves at max_depth=5
  - member_fa3ae54a7efaa0b80a428bfd5f2a36451c75c6c3cd5433b757456f4e485861ed retains 30 leaves at max_depth=5
  - member_28e166087735dba5cfb683e9f8057ad48baa23bfb6bc07d9e8b94534dcbf755d retains 12 leaves at max_depth=5
  - member_dc514307b8cea06d9fe014713710f3cf3dcff3378361662d681c97fac79dda1f retains 12 leaves at max_depth=5

### `CODE`

- `top_partition_count`: **3**
- aligned fused D shape: `[279, 279]`; diag min/max `0` / `0`
- cut-visible internals labeled: 65
- cutter `warnings`:
  - member_0f08aba821b7175e09d7751584e39c89d5276a65240918b0592933453192cfdf retains 14 leaves at max_depth=5
  - member_03006e037bf875d81f27872b786c892fe1eb2e3e77f53a9fb6dae2ce36a04287 retains 24 leaves at max_depth=5

## Output layout

```
orchard-view/artifacts/forte_blogs/
  code_taxonomy.json
  code_taxonomy_seed.yaml
  code_head.npz
  training/manifest.json
  orchard/          # Orchard.save() + compressed layer_matrices
  cuts/             # semantic + CODE Calinski-optimal JSON (fused D)
  labels/           # gpt-4.1-mini mappings + raw response cache
  node_descriptions.json
  view/mockup_data.js
  standalone/orchard_view_forte_<stamp>/
  EXPORT.md
```
