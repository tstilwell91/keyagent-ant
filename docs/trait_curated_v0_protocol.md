# Trait Curated v0 Selection and Curation Protocol

This document defines the developer-level protocol and methodology for the creation and manual curation of the first trait-grounded specimen subset (`trait_curated_v0`).

---

## 1. Objectives

The primary goal of `trait_curated_v0` is to establish a high-confidence, physically grounded, multi-view evaluation subset. This subset bridges raw image models (CNNs/Vision models) and deterministic symbolic knowledge engines (the taxonomic KB key reasoner).

### Why Specimen-Level Selection?
Ant taxonomic keys are written to operate on physical individual specimens, not on isolated individual image perspectives. To evaluate taxonomic consistency accurately, we must select and curate physical specimens across three distinct standard viewing angles (dorsal, head, profile).

---

## 2. Selection Methodology

The selection process is strictly deterministic and offline, implemented in `src/antid/keys/trait_curation_dataset.py`.

### A. Fallback Specimen Grouping
To handle datasets where specimen tracking identifiers are incomplete:
1. We compute a unique specimen tracking key:
   $$\text{specimen\_key} = \begin{cases} \text{specimen\_id} & \text{if specimen\_id is non-empty} \\ \text{catalog\_number} & \text{otherwise} \end{cases}$$
2. We group all image files matching a given `specimen_key`. Rows without both identifiers are not silently dropped as long as `catalog_number` exists.
3. Both identifiers are preserved and written to all down-stream artifacts to maintain absolute lineage auditability.

### B. Relaxed Tri-View Completeness & Representative Selection
A specimen is considered tri-view complete if it has **at least one** dorsal, head, and profile view (rather than exactly one). This avoids rejecting valid specimens just because AntWeb or the import manifest has duplicate view entries.

When duplicate images exist for a given view, we choose exactly one representative image deterministically:
1. **Quality Rank Filter**: If `image_quality_flag` is present and meaningful, we prioritize high-quality flags. The quality categories are mapped to ranks:
   - **Rank 0 (High)**: `["high", "excellent", "checked", "good"]`
   - **Rank 1 (Normal)**: `["unchecked", ""]`
   - **Rank 2 (Custom)**: Any other flag value
   - **Rank 3 (Poor)**: `["low", "poor", "bad"]`
2. **Alphabetical Tie-Breaker**: If multiple images share the same quality rank (or quality flag is absent), we sort the `image_path` alphabetically and choose the first.
3. **Duplicate Tracking**: The count of duplicate images found for each view type is written to the output CSV under the `duplicate_view_counts` column (e.g. `"dorsal:1,head:2,profile:1"`).

### C. Seeded Selection & Fallback Splits
To extract a balance of up to $N$ specimens per KB-covered taxon (default is 5):
1. We prioritize drawing from the preferred split (default: `test`).
2. If the preferred split does not contain enough tri-view complete candidates to reach $N$, the selection engine automatically falls back to `val`, and then `train` splits.
3. Candidates are pre-sorted alphabetically by `specimen_key` before applying the seeded random shuffles. This eliminates filesystem traversal non-determinism, ensuring identical selections across different environments given the same seed.

---

## 3. Blank Template & Non-Evidentiary Policy

To protect biological integrity, **no trait values are inferred automatically from genus/species labels or taxonomy**. Specimen templates must be generated as blank, strictly non-evidentiary scaffolds.

### A. Template JSONL Format
Each record written to the annotation template must preserve standard structure:
- `specimen_id` and `catalog_number` identifiers.
- `images` map of representative views with their unique image IDs and paths.
- `observed_traits` initialized to `{}` (empty object).
- `source_evidence` initialized to `[]` (empty list).
- `annotation_metadata` with tracking headers:

```json
"annotation_metadata": {
  "annotation_round": "trait_curated_v0",
  "annotation_status": "not_started",
  "trait_values_verified": false,
  "trait_source_policy": "blank_template_no_traits_inferred",
  "review_status": "needs_expert_or_source_review",
  "annotator": null,
  "notes": ""
}
```

---

## 4. Manual Curation Workflow

Curation must proceed through manual verification by humans (experts or trained annotators):
1. **Inspection**: Curation tools load the JSONL record, and display the dorsal, head, and profile images side-by-side.
2. **Scoring**: Annotators observe the physical features in the images and record corresponding trait values matching the KB `trait_schema.yaml`.
3. **Review Policy**: Once observed, the status is updated to `needs_review` or `completed` with the annotator's signature (`annotator` field) and explicit verification flag (`trait_values_verified: true`).
