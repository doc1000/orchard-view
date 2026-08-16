cursor analysis of orchard:
A few library facts that matter:

TaxonomyModel.fit() is still TF-IDF. The neural path is modernbert_logistic: encode with ModernBERTFeatureBackend, fit logistic (C=0.1, class_weight="balanced", max_iter=1000, random_state=20260725), then set classifier + feature_encoder and taxonomy_transform="modernbert_logistic" (or save_head / load_head). Calling .fit() would wipe that and fall back to cue/TF-IDF.

CODE will not fuse by default. Packaged fused dicts exist only for trees named domain / function. A custom CODE tree stays {CODE_raw_js: 1.0} unless you pass taxonomy_weights / profiles. Semantic does auto-fuse MiniLM 0.66 + TF-IDF 0.34 when orchard[embeddings] is present.

Closest packaged analog for a single taxonomy (function-only):

CODE_raw_js=0.60, description_minilm_centered_cosine=0.25, tfidf_cosine=0.15

Cuts must follow the fused tree, not raw TF-IDF / raw CODE rows. Keep the builder’s shared layer_matrices and fuse_to_dissimilarity(...) per profile (or persist layers with layer_matrix_persist). Passing a fresh TF-IDF matrix into Calinski would score a different geometry than the tree.

orchard-view does not install neural extras yet. pyproject.toml depends on orchard with no [ml]. The run needs orchard[ml] (MiniLM + ModernBERT). Missing extras should fail loudly — no allow_offline_fallback.


my response:

Great eval on the library.  seems like we should fix those first in the orchard library vs working around it here.  Give me a short prompt for each of your points that I can use invididually to make some small changes in the orchard library directly... in another agent window.

The taxonomyModel.fit() sounds potentially destructive... its needs to be explicit or somehow protected.  the default should be the underlying modernBert pathway.  check orchard/docs/site for general instructions... this might be partly expalined.

the fused trees: i want the default for taxonomyModel tree weights to follow the PATTERN that domain and function trees use: weight to the taxonomy, weight to semantics, weight to tfidf.  use the same weights but applied to the new taxonomy.  It should not default to weight =1.

Cuts must DEFINITELY follow the existing fused tree... the weighted matrix that generated the linkages should be associated with the z-array (tree) quite clearly.  a diff matrix is pretty useless.  we should validate that this is the case.

A question... do you need to load the [ml] extras on the calling side?  should i instead load them on the Orchard side... seems a lot cleaner to load them as a dependency on the Orchard side.

save the prompts as  an .md file in planning that I can export and use in the other folder.
