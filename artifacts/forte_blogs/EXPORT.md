# Forte blogs orchard export

Built a semantic TF-IDF tree and a CODE taxonomy tree over 279 Forte Labs
"Building a Second Brain" posts. CODE was fit with TaxonomyModel.fit() on
synthetic YAML chunks plus heading-explicit real sections. Both trees were
cut with the AppWorld Calinski-optimal parameters.
Cut-visible internals were labeled with `gpt-4.1-mini-2025-04-14`.

## Sources

- Documents: `forte_second_brain_scraper/forte-building-a-second-brain/posts`
  (279 markdown posts; stem → `item_id`,
  frontmatter title → `title`, body → `text`, `source="forte_blogs"`)
- CODE seed: `orchard-view/artifacts/forte_blogs/code_taxonomy_seed.yaml`
- Converted definition: `orchard-view/artifacts/forte_blogs/code_taxonomy.json`

## CODE training

- Synthetic YAML chunks: 20
- Heading-explicit sections (H1–H3, single CODE stage word): 25
- Training items total: 45
- Synthetic chunks are training-only and are not orchard leaves.
- Gold post `0027-building-a-second-brain-the-definitive-introductory-guide` contributed all four CODE stages.
- Fitted classifier `transform()`s the full 279-post corpus.

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
- API calls this run: 90

## Results

### `semantic`

- `top_partition_count`: **3**
- aligned feature matrix shape: `[279, 18402]`; diag min/max `nan` / `nan`
- cut-visible internals labeled: 7
- cutter `warnings`:
  - member_e8d743baea375f9a3f2980870a39a701e450f13302e87220f51f4b3fbdd78982 retains 187 leaves at max_depth=5
  - member_1ccc55d93edfbf9a529e251dd4b19683b17855e36d579e12c27900a5d8418607 retains 77 leaves at max_depth=5

### `CODE`

- `top_partition_count`: **5**
- aligned feature matrix shape: `[279, 4]`; diag min/max `nan` / `nan`
- cut-visible internals labeled: 84
- cutter `warnings`:
  - (none)

## Output layout

```
orchard-view/artifacts/forte_blogs/
  code_taxonomy.json
  training/manifest.json
  orchard/          # Orchard.save()
  cuts/             # semantic + CODE Calinski-optimal JSON
  labels/           # gpt-4.1-mini mappings + raw response cache
  node_descriptions.json
  view/mockup_data.js
  standalone/orchard_view_forte_<stamp>/
  EXPORT.md
```
