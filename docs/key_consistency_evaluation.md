# Taxonomic Key-Consistency Batch Evaluation Harness

This document describes the design, execution flow, input formats, output schemas, and command-line instructions for the KeyAgent-Ant Taxonomic Key-Consistency Batch Evaluation Harness (`key_consistency_evaluator.py`).

---

## Architectural Role & Scope

The batch key-consistency evaluation harness integrates tabular predictions CSV files with optional observed physical traits sidecars. It evaluates each image record against a loaded Taxonomic Knowledge Base (KB) via the reasoning integration adapter, and then aggregates agreement, conflict, missing trait, and rule violation statistics across the entire batch.

```
+--------------------+
|  predictions.csv   | ---\
+--------------------+    \      +-----------------------------+      +-----------------------+
                           +---> |  Key Consistency Evaluator  | ---> |  Batch Summary JSON   |
+--------------------+    /      +-----------------------------+      +-----------------------+
| traits sidecar     | ---/
| (JSON or JSONL)    |
+--------------------+
```

---

## Key Features

1. **Dual Sidecar Format Support**: Accepts physical trait observations in either standard JSON (dictionary mapping `image_id` to traits) or JSONL (line-by-line JSON records) formats.
2. **Deterministic Batch Aggregation**: Summarizes agreement status counts and rates, top-k candidate agreement, missing traits frequency, and rule conflict frequency.
3. **Graceful Handling of Out-of-Scope Candidates**: Catches candidate resolution errors (e.g., when a CNN model predicts a taxon not registered in the KB) on a per-row basis. Instead of crashing, it creates a specialized out-of-scope evidence packet with an appropriate unresolved or insufficient evidence agreement status.

---

## Advanced Evaluation Metrics & Refinements

To ensure key-consistency statistics accurately reflect biological agreement rather than random or default overlaps, several refined metrics and evaluation safeguards have been introduced:

### 1. Meaningful Evidence Fields (`meaningful_evidence_records` & `meaningful_evidence_rate`)
* **`meaningful_evidence_records`**: Calculated as `total_records - status_counts["insufficient_trait_evidence"]`.
* **`meaningful_evidence_rate`**: Calculated as `meaningful_evidence_records / total_records` (0.0 if total_records is 0).
* **Rationale**: This separates records where the system actually had usable trait evidence to evaluate against the Taxonomic KB from records where the system honestly reported insufficient evidence (e.g., because of missing sidecar entries or fully unobserved physical features). Tracking this allows developers to assess physical trait reporting coverage independently of model accuracy.

### 2. Refined Visual/Key Top Agreement Counting
* **Rationale**: We explicitly exclude records with `insufficient_trait_evidence` status from the `visual_key_top_agreement_count`. The count only includes records where:
  - `status != "insufficient_trait_evidence"`
  - `key_top_taxon_id` is not None
  - `visual_top_taxon_id == key_top_taxon_id`
* **Why Exclude Insufficient Evidence?**: This avoids treating default/no-evidence rankings or tie-breakers as genuine biological agreement. If there is no trait evidence, any overlap between the model's top prediction and the key reasoner's top-ranked candidate is purely a random coincidental artifact of empty/default scoring, rather than meaningful taxonomic validation.

### 3. Separate Out-of-Scope Visual Candidate Tracking
* **Rationale**: Standard model predictions may output taxa that are outside the scope of the current local taxonomic KB, resulting in `ValueError` during candidate registration checks.
* **Tracking Strategy**: Rather than crashing the batch evaluation or masking these failures as standard taxonomic key conflicts, we catch candidate registration errors gracefully on a per-row basis:
  - We increment `out_of_scope_candidate_records` and calculate `out_of_scope_candidate_rate`.
  - For fallback packets, we inject a clear `"evaluator_warning"` field containing structured debugging information:
    ```json
    "evaluator_warning": {
      "type": "out_of_scope_visual_candidate",
      "message": "Visual candidate is out of scope or unregistered...",
      "raw_error": "..."
    }
    ```
  - This separates registry-mismatch/out-of-scope issues from genuine biological key conflicts (where a taxon *is* registered but the physical traits disagree with the taxonomic rules).

---

## Input Formats

### 1. Tabular Predictions CSV
Standard predictions CSV file containing model predictions and metadata (e.g., `image_path`, `view_type`, `top1_label`, `top1_prob`, etc.).

### 2. Observed Physical Traits Sidecar
Physical traits observed for individual specimens/images. Supported in two formats:

#### A. Flat JSON Mapping
A dictionary where keys are image IDs and values are dictionaries of trait-value pairs.
```json
{
  "casent0123456_profile": {
    "postpetiole_attachment": "dorsal_surface_first_gastral_segment",
    "gaster_shape_dorsal": "heart_shaped"
  }
}
```

#### B. Line-by-Line JSONL
A text file where each line is a JSON object containing an `image_id` and an `observed_traits` dictionary.
```jsonl
{"image_id": "casent0123456_profile", "observed_traits": {"postpetiole_attachment": "dorsal_surface_first_gastral_segment"}}
{"image_id": "casent0789101_profile", "observed_traits": {"postpetiole_attachment": "dorsal_surface_first_gastral_segment"}}
```

---

## Batch Summary Output Schema

The evaluator produces a single consolidated JSON report containing a `summary` object and a list of `evidence_packets` for each analyzed record.

### Summary Object Structure

```json
{
  "summary": {
    "total_records": 3,
    "status_counts": {
      "insufficient_trait_evidence": 1,
      "visual_top_conflicts_with_key": 1,
      "visual_top_tied_for_key_top": 0,
      "visual_top_supported_by_key": 1,
      "visual_top_unresolved_by_key": 0,
      "key_prefers_different_taxon": 0
    },
    "support_rate": 0.3333333333333333,
    "conflict_rate": 0.3333333333333333,
    "insufficient_trait_evidence_rate": 0.3333333333333333,
    "unresolved_rate": 0.0,
    "key_prefers_different_taxon_rate": 0.0,
    "tied_for_key_top_rate": 0.0,
    "meaningful_evidence_records": 2,
    "meaningful_evidence_rate": 0.6666666666666666,
    "out_of_scope_candidate_records": 1,
    "out_of_scope_candidate_rate": 0.3333333333333333,
    "visual_key_top_agreement_count": 1,
    "visual_key_top_agreement_rate": 0.3333333333333333,
    "most_common_missing_traits": [
      {
        "trait_id": "gaster_shape_dorsal",
        "count": 1
      }
    ],
    "most_common_conflicting_rules": [
      {
        "rule_id": "mem_myrmicinae_001b",
        "count": 1
      }
    ]
  },
  "evidence_packets": [
    ...
  ]
}
```

---

## CLI Usage

The batch evaluator is integrated into the `antid.keys` command-line interface under the `evaluate-key-consistency` subcommand.

### Command Syntax

```bash
PYTHONPATH=src .venv/bin/python -m antid.keys.cli evaluate-key-consistency \
  --kb-dir <path_to_kb_directory> \
  --predictions-csv <path_to_predictions_csv> \
  --observed-traits <path_to_traits_sidecar> \
  --output-json <path_to_output_json> \
  --top-k <limit_candidates_count>
```

### Parameters
* `--kb-dir` (Required): Path to the taxonomic Knowledge Base directory.
* `--predictions-csv` (Required): Path to the tabular CSV predictions file.
* `--observed-traits` (Optional): Path to the JSON or JSONL physical traits sidecar file. If omitted, all evaluated records default to empty traits (insufficient evidence status).
* `--output-json` (Required): Path where the final summary and evidence packets report will be written.
* `--top-k` (Optional, Default: 5): Maximum number of top visual candidates to extract from each prediction row.
* `--no-candidate-filter` (Optional): If set, disables candidate visual filtering and evaluates the KB reasoner over all registered taxa in the registry rather than restricting evaluation to visual predictions.
