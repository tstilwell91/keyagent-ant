# Walkthrough - Taxonomic KB Validation, Reasoning, and Integration Adapter

This document summarizes the design, implementation, and verification of the deterministic taxonomic Knowledge Base (KB) validation and reasoning harness, the downstream vision-reasoning Integration Adapter, and the Prediction-Artifact Adapter for KeyAgent-Ant.

---

## 1. Taxonomic KB Validation & Reasoning Harness

The first milestone established a robust, deterministic core to validate taxonomic schemas and perform rule-based matching.

### A. Core Components Introduced (`src/antid/keys/`)
1. **`__init__.py`**:
   - Establishes the package namespace and exposes public interfaces (`load_kb`, `reason_over_traits`, and `KeyReasoner`).
2. **`kb_loader.py`**:
   - Loads the 4 KB files (`source_manifest.yaml`, `trait_schema.yaml`, `taxon_registry.yaml`, and `key_rules.json`).
   - Implements **Multi-Source Manifest Validation**: Collects registered `source_id` values dynamically and validates every rule's resolved `source_id` against them.
   - Implements **Strict Topological Verification**: Runs cycle-detection via DFS, unreachability verification from root couplet `"1"`, unknown `next_couplet` links (with `"7"` whitelisted as a temporary POC boundary couplet), and strict mutual exclusion checks on `terminal_taxon_id` and `next_couplet`.
   - Validates that condition operators are strictly within `["equals", "not_equals", "in", "not_in"]`.
3. **`key_reasoner.py`**:
   - Implements **Case-Insensitive Unambiguous Candidate Filtering**: Accepts taxon IDs first, then scientific names as aliases only if unique in the registry.
   - Implements **Path-Based Scoring**: Evaluates rules as supported (+1), conflicted (-1), or unresolved (0) and computes taxon raw and normalized scores.
   - Tracks and reports missing traits (categorized by `view_type` if provided) and unknown traits.
   - Generates next action recommendations and extracts manifest limitations.

### B. Verification of Validation Harness
Run validation commands on the actual proof-of-concept (POC) KB:
```bash
PYTHONPATH=src .venv/bin/python -m antid.keys.cli validate \
  --kb-dir data/kb/poc_myrmicinae_mem
```

#### Output:
```json
{
  "status": "success",
  "message": "Knowledge base validation passed for 'data/kb/poc_myrmicinae_mem'.",
  "summary": {
    "source_manifest_id": [
      "mem_myrmicinae_genera_se_us"
    ],
    "traits_count": 11,
    "taxa_count": 6,
    "couplets_count": 6
  }
}
```

---

## 2. Reasoning Integration Adapter

The second milestone bridges the gap between machine-learning visual predictions (CNN output) and deterministic biological reasoning rules. It receives visual model predictions and observed traits, resolves candidates, triggers reasoning, performs tie-breaking, and assembles structured output.

### A. Four Core Architectural Requirements Completed

To ensure defensive execution and precise structuring, we implemented the four requirements:

1. **Normalized Structured Next Action**:
   Instead of a temporary flat string, `recommended_next_action` is a structured object. It identifies the target trait recommendation by tracking the unobserved conditions on the top candidate's path:
   ```json
   "recommended_next_action": {
     "action_type": "none",  // or "observe_trait"
     "trait_id": null,       // or "antenna_segment_count"
     "reason": "Taxon 'Crematogaster' is fully supported by the observations.",
     "source": "kb_reasoner",
     "raw_recommendation": "Taxon 'Crematogaster' is fully supported by the observations."
   }
   ```

2. **Explicit Non-Decision Safety Fields**:
   The adapter operates as an evidence assembler only, not a final decision-maker. It injects explicit non-decision indicators into every packet:
   ```json
   {
     "final_identification": null,
     "identification_decision_policy": "not_applied"
   }
   ```

3. **Structured Agreement Summary & Six Mutually-Exclusive Statuses**:
   The adapter evaluates the top visual candidate (rank 1) and ranks its relationship against the KB reasoning using six explicit statuses:
   - `insufficient_trait_evidence`: Observed traits are empty or no definitive rules have been resolved to support or conflict.
   - `visual_top_conflicts_with_key`: Top visual candidate has active conflicts (raw score < 0).
   - `visual_top_tied_for_key_top`: Top visual candidate is tied with other taxa for the top KB score.
   - `key_prefers_different_taxon`: Top visual candidate is valid, but the key prefers a different taxon strictly higher.
   - `visual_top_supported_by_key`: Top visual candidate has positive support, no conflicts, and is the unique top KB candidate.
   - `visual_top_unresolved_by_key`: Top visual candidate has only unresolved rules, no conflicts, and is the unique top candidate.

   Output structure:
   ```json
   "agreement_summary": {
     "status": "visual_top_supported_by_key",
     "visual_top_taxon_id": "crematogaster",
     "key_top_taxon_id": "crematogaster",
     "visual_top_raw_key_score": 1,
     "visual_top_normalized_key_score": 1.0,
     "reason": "Top visual candidate 'crematogaster' is uniquely supported by the key."
   }
   ```

4. **Deterministic Tie-Breaking Logic**:
   When multiple taxa have identical normalized and raw scores, the adapter sorts them **alphabetically by `taxon_id`**. This ensures stable, deterministic ranking across all platforms. If the visual top candidate is tied for the top KB score, it is classified as `visual_top_tied_for_key_top` instead of `key_prefers_different_taxon`.

---

## 3. Actual CLI Verification of Integration Adapter

Both mock model predictions are successfully verified under the `integrate` subcommand.

### A. Integrated Visual Support Case (`mock_model_output_01.json`)
```bash
PYTHONPATH=src .venv/bin/python -m antid.keys.cli integrate \
  --kb-dir data/kb/poc_myrmicinae_mem \
  --model-output examples/kb/mock_model_output_01.json
```

#### Output (Snippet):
```json
{
  "image_id": "casent0123456_profile",
  "view_type": "profile",
  "visual_candidates": [
    {
      "taxon_id": "crematogaster",
      "scientific_name": "Crematogaster",
      "score": 0.85,
      "rank": 1
    },
    {
      "taxon_id": "solenopsis",
      "scientific_name": "Solenopsis",
      "score": 0.12,
      "rank": 2
    }
  ],
  "observed_traits": {
    "postpetiole_attachment": "dorsal_surface_first_gastral_segment",
    "gaster_shape_dorsal": "heart_shaped",
    "petiole_node_state": "no_node_dorsoventrally_flattened"
  },
  "agreement_summary": {
    "status": "visual_top_supported_by_key",
    "visual_top_taxon_id": "crematogaster",
    "key_top_taxon_id": "crematogaster",
    "visual_top_raw_key_score": 1,
    "visual_top_normalized_key_score": 1.0,
    "reason": "Top visual candidate 'crematogaster' is uniquely supported by the key."
  },
  "recommended_next_action": {
    "action_type": "none",
    "trait_id": null,
    "reason": "Taxon 'Crematogaster' is fully supported by the observations.",
    "source": "kb_reasoner",
    "raw_recommendation": "Taxon 'Crematogaster' is fully supported by the observations."
  },
  "final_identification": null,
  "identification_decision_policy": "not_applied"
}
```

### B. Integrated Conflict Case (`mock_model_output_02.json`)
```bash
PYTHONPATH=src .venv/bin/python -m antid.keys.cli integrate \
  --kb-dir data/kb/poc_myrmicinae_mem \
  --model-output examples/kb/mock_model_output_02.json
```

#### Output (Snippet):
```json
{
  "image_id": "casent0789101_profile",
  "view_type": "profile",
  "visual_candidates": [
    {
      "taxon_id": "solenopsis",
      "scientific_name": "Solenopsis",
      "score": 0.9,
      "rank": 1
    },
    {
      "taxon_id": "crematogaster",
      "scientific_name": "Crematogaster",
      "score": 0.05,
      "rank": 2
    }
  ],
  "observed_traits": {
    "postpetiole_attachment": "dorsal_surface_first_gastral_segment",
    "gaster_shape_dorsal": "heart_shaped",
    "petiole_node_state": "no_node_dorsoventrally_flattened"
  },
  "agreement_summary": {
    "status": "visual_top_conflicts_with_key",
    "visual_top_taxon_id": "solenopsis",
    "key_top_taxon_id": "crematogaster",
    "visual_top_raw_key_score": -2,
    "visual_top_normalized_key_score": -0.3333333333333333,
    "reason": "Top visual candidate 'solenopsis' has conflicting rules in the taxonomic key."
  },
  "conflict_summary": [
    {
      "taxon_id": "solenopsis",
      "score": 0.9,
      "rank": 1,
      "key_raw_score": -2,
      "key_normalized_score": -0.3333333333333333,
      "conflicting_rules": [
        "mem_myrmicinae_001b",
        "mem_myrmicinae_006b"
      ]
    }
  ],
  "final_identification": null,
  "identification_decision_policy": "not_applied"
}
```

---

## 4. Prediction-Artifact Adapter

The third milestone introduces a formatting and mapping boundary layer to parse ML model outputs (typically serialized as tabular `predictions.csv` files) into standardized visual model prediction objects expected by our Integration Adapter.

### A. Core Architectural Requirements Completed

1. **Deterministic Label Casing Heuristics**:
   To translate flat prediction strings to standard taxonomical targets without relying on downstream knowledge:
   - If the label contains a space, it is classified as `scientific_name` (e.g., `"Solenopsis invicta"`).
   - Else if the label contains an underscore `_` and is entirely lowercase, it is classified as `taxon_id` (e.g., `"solenopsis_invicta"`).
   - Else if the label is entirely lowercase, it is classified as `taxon_id` (e.g., `"crematogaster"`).
   - All other formats default to `scientific_name` (e.g., `"Crematogaster"`).

2. **Column Map & Scan Fallbacks**:
   The adapter safely scans and resolves headers dynamically:
   - `image_id` maps to any of: `image_id`, `image_path`, `filename`, `file_name`, `path`.
   - `split` maps to: `split`, `dataset_split`, `subset`.
   - `true_label` maps to: `true_label`, `label`, `taxon_id`, `scientific_name`, `target`.
   - `pred_label` maps to: `pred_label`, `prediction`, `predicted_label`, `top1_label`.
   - `confidence` maps to: `confidence`, `score`, `top1_prob`, `probability`.

3. **Defensive Structural Scope**:
   - `observed_traits` is defaulted to `{}` (empty map).
   - This prevents the formatting adapter from making any biological claims, leaving trait observation strictly to downstream adapters or human experts.

---

## 5. Taxonomic Key-Consistency Batch Evaluation Harness

The fourth milestone introduces the batch evaluation harness (`key_consistency_evaluator.py`), which evaluates consistency across a set of model predictions and observed traits.

### A. Key Technical Achievements

1. **Dual Physical Traits Sidecar Parsing**:
   - Safely parses observed physical traits from standard JSON maps (dictionaries) as well as line-by-line JSONL streams.
   - Robustly verifies type structures and handles malformed or single-line records cleanly.

2. **Graceful Out-of-Scope Handling**:
   - Implements per-row defensive recovery. If a CNN model predicts a candidate that does not exist in the Taxonomic KB registry, the evaluator catches the downstream `ValueError`.
   - Instead of terminating evaluation, it generates a fallback/unresolved evidence packet and assigns an appropriate unresolved status (e.g., `insufficient_trait_evidence` if no observations exist, or `visual_top_unresolved_by_key`).

3. **Consolidated Metric Aggregation**:
   - Aggregates overall agreement statuses, rates, missing traits frequency, and active rule conflicts into a clean, unified report format.

### B. Advanced Refinements & Rationale

To ensure that key-consistency statistics accurately reflect biological agreement rather than random or default overlaps, several refined metrics and evaluation safeguards have been introduced:

1. **Meaningful Evidence Rate (`meaningful_evidence_records` & `meaningful_evidence_rate`)**
   - **`meaningful_evidence_records`**: `total_records - status_counts["insufficient_trait_evidence"]`
   - **`meaningful_evidence_rate`**: `meaningful_evidence_records / total_records` (0.0 if total_records is 0)
   - **Rationale**: This separates records where the system actually had usable trait evidence to evaluate against the Taxonomic KB from records where the system honestly reported insufficient evidence (e.g., because of missing sidecar entries or fully unobserved physical features). Tracking this allows developers to assess physical trait reporting coverage independently of model accuracy.

2. **Refined Visual/Key Top Agreement Counting (Excluding Insufficient Evidence)**
   - **Rationale**: We explicitly exclude records with `insufficient_trait_evidence` status from the `visual_key_top_agreement_count`. The count only includes records where:
     - `status != "insufficient_trait_evidence"`
     - `key_top_taxon_id` is not None
     - `visual_top_taxon_id == key_top_taxon_id`
   - **Why Exclude Insufficient Evidence?**: This avoids treating default/no-evidence rankings or tie-breakers as genuine biological agreement. If there is no trait evidence, any overlap between the model's top prediction and the key reasoner's top-ranked candidate is purely a random coincidental artifact of empty/default scoring, rather than meaningful taxonomic validation.

3. **Separate Out-of-Scope Visual Candidate Tracking**
   - **Rationale**: Standard model predictions may output taxa that are outside the scope of the current local taxonomic KB, resulting in `ValueError` during candidate registration checks.
   - **Tracking Strategy**: Rather than crashing the batch evaluation or masking these failures as standard taxonomic key conflicts, we catch candidate registration errors gracefully on a per-row basis:
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

## 6. Comprehensive Test Suite Execution

We expanded our unit and integration test suite to cover all milestones. All 83 tests pass successfully:

```bash
PYTHONPATH=src .venv/bin/pytest -v
```

```text
============================== 83 passed in 0.26s ==============================
```

---

## 7. Actual CLI Verification of Consistency Evaluation Subcommand

The batch consistency evaluator was executed over the mock predictions dataset and sidecar trait observations.

### Execution Command
```bash
PYTHONPATH=src .venv/bin/python -m antid.keys.cli evaluate-key-consistency \
  --kb-dir data/kb/poc_myrmicinae_mem \
  --predictions-csv examples/kb/mock_predictions.csv \
  --observed-traits examples/kb/mock_observed_traits.json \
  --output-json examples/kb/mock_key_consistency_eval.json \
  --top-k 3
```

### Subcommand Output Summary
```json
{
  "status": "success",
  "records_count": 3,
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
  "meaningful_evidence_records": 2,
  "meaningful_evidence_rate": 0.6666666666666666,
  "out_of_scope_candidate_records": 1,
  "out_of_scope_candidate_rate": 0.3333333333333333
}
```
The consolidated JSON report was successfully generated at `examples/kb/mock_key_consistency_eval.json`.
