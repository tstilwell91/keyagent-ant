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

## 5. Expanded Unit & Integration Test Suite

We expanded our unit and integration test suite to include the `prediction_artifact_adapter`. All 30 tests pass successfully:

```bash
PYTHONPATH=src .venv/bin/pytest -v
```

```text
============================= test session starts ==============================
platform darwin -- Python 3.12.8, pytest-9.1.0, pluggy-1.6.0
collected 30 items

tests/test_kb_loader.py::test_get_couplet_base_id PASSED                 [  3%]
tests/test_kb_loader.py::test_valid_kb_loading PASSED                    [  6%]
tests/test_kb_loader.py::test_missing_required_file PASSED               [ 10%]
tests/test_kb_loader.py::test_invalid_source_id_rule PASSED              [ 13%]
tests/test_kb_loader.py::test_invalid_operator PASSED                    [ 16%]
tests/test_kb_loader.py::test_mutual_exclusion_both PASSED               [ 20%]
tests/test_kb_loader.py::test_mutual_exclusion_neither PASSED            [ 23%]
tests/test_duplicate_trait_id PASSED                                     [ 26%]
tests/test_kb_loader.py::test_unreachable_couplet PASSED                 [ 30%]
tests/test_kb_loader.py::test_cyclic_couplet_path PASSED                 [ 33%]
tests/test_kb_loader.py::test_unknown_next_couplet_reference PASSED      [ 36%]
tests/test_key_reasoner.py::test_resolve_candidate_taxa PASSED           [ 40%]
tests/test_key_reasoner.py::test_evaluate_rule_operators PASSED          [ 43%]
tests/test_key_reasoner.py::test_deterministic_scoring_crematogaster PASSED [ 46%]
tests/test_key_reasoner.py::test_missing_and_unknown_traits PASSED       [ 50%]
tests/test_key_reasoner.py::test_recommended_next_action_and_limitations PASSED [ 53%]
tests/test_reasoning_adapter.py::test_schema_validations PASSED          [ 56%]
tests/test_reasoning_adapter.py::test_adapter_missing_required_fields PASSED [ 60%]
tests/test_reasoning_adapter.py::test_adapter_insufficient_evidence PASSED [ 63%]
tests/test_reasoning_adapter.py::test_adapter_visual_top_supported PASSED [ 66%]
tests/test_reasoning_adapter.py::test_adapter_visual_top_conflicts PASSED [ 70%]
tests/test_reasoning_adapter.py::test_adapter_key_prefers_different PASSED [ 73%]
tests/test_reasoning_adapter.py::test_deterministic_tie_breaking PASSED  [ 76%]
tests/test_reasoning_adapter.py::test_cli_integration_subcommand PASSED  [ 80%]
tests/test_prediction_artifact_adapter.py::test_classify_label_formatting_heuristic PASSED [ 83%]
tests/test_prediction_artifact_adapter.py::test_prediction_row_to_model_output_scenarios PASSED [ 86%]
tests/test_prediction_artifact_adapter.py::test_load_predictions_csv PASSED [ 90%]
tests/test_prediction_artifact_adapter.py::test_convert_predictions_csv_to_model_outputs PASSED [ 93%]
tests/test_prediction_artifact_adapter.py::test_cli_convert_predictions_subcommand PASSED [ 96%]
tests/test_prediction_artifact_adapter.py::test_predictions_to_reasoning_integration PASSED [100%]

============================== 30 passed in 0.09s = 0.09s ==============================
```

---

## 6. Actual CLI Verification of Predictions Subcommand

We successfully validated the conversion command on the mock predictions CSV dataset.

### Execution Command
```bash
PYTHONPATH=src .venv/bin/python -m antid.keys.cli convert-predictions \
  --predictions-csv examples/kb/mock_predictions.csv \
  --output-json examples/kb/mock_model_outputs_from_predictions.json \
  --top-k 3
```

### Command Output
```json
{
  "status": "success",
  "message": "Successfully converted predictions CSV 'examples/kb/mock_predictions.csv' to model outputs JSON 'examples/kb/mock_model_outputs_from_predictions.json' containing 3 records.",
  "records_count": 3
}
```
