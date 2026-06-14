# Taxonomic Prediction-Artifact Adapter

This document describes the design, formatting casing heuristics, and command-line instructions for the KeyAgent-Ant Taxonomic Prediction-Artifact Adapter. This layer translates real or synthetic machine learning prediction files (such as tabular `predictions.csv` files) into standardized, structured visual model prediction inputs expected by the Taxonomic KB Reasoning Integration Adapter.

---

## Architectural Role & Scope

The Taxonomic Prediction-Artifact Adapter acts as a deterministic formatting and structure-mapping boundary. In standard deep learning pipelines, evaluations are typically serialized into tabular formats (`.csv` or `.tsv`) with varying column headers, representing predicted classes, top-k probabilities, file paths, and training split assignments. 

To prevent downstream reasoning components from dealing with ad-hoc formats, this adapter converts arbitrary tabular structures into a standardized JSON list schema.

```
+-------------------+      +-----------------------------+      +--------------------+
|  predictions.csv  | ---> | Prediction-Artifact Adapter | ---> |  Standardized JSON |
+-------------------+      +-----------------------------+      +--------------------+
                                                                          |
                                                                          v
                                                                +--------------------+
                                                                | Integration Layer  |
                                                                +--------------------+
```

> [!IMPORTANT]
> **Defensive Safety Boundary**:
> The Prediction-Artifact Adapter is **exclusively a structural and formatting converter**. It does **not** perform biological reasoning, and it does **not** infer morphological traits from the images or records. 
> 
> By design:
> 1. It populates `observed_traits` as an empty dictionary `{}`.
> 2. When passed downstream to the integration adapter, this empty mapping safely triggers the `insufficient_trait_evidence` agreement status without causing errors or crashes.
> 3. Taxonomic validity and alias resolution remain strictly separated and are handled entirely downstream by the `KeyReasoner`.

---

## Mapping Specifications

### 1. Robust Column Header Mapping & Fallbacks

The adapter supports multiple common naming conventions for CNN prediction outputs. It scans the CSV file for any of the following registered headers (case-insensitive) to extract fields:

* **Image Identifier / Path**:
  - Primary: `image_id`
  - Fallbacks: `image_path`, `filename`, `file_name`, `path`
* **Data Split**:
  - Primary: `split`
  - Fallbacks: `dataset_split`, `subset`
* **Ground Truth Label**:
  - Primary: `true_label`
  - Fallbacks: `label`, `taxon_id`, `scientific_name`, `target`
* **Predicted Class Label**:
  - Primary: `pred_label`
  - Fallbacks: `prediction`, `predicted_label`, `top1_label`
* **Prediction Confidence / Score**:
  - Primary: `confidence`
  - Fallbacks: `score`, `top1_prob`, `probability`

### 2. View Orientation Auto-Detection

The adapter dynamically infers the image's camera view orientation (`view_type`) by analyzing the file path or image ID. It checks for specific sub-strings:
* `"head"` -> `view_type = "head"`
* `"profile"` -> `view_type = "profile"`
* `"dorsal"` -> `view_type = "dorsal"`
* If none of these match, it defaults to `None`.

### 3. Casing & Formatting Heuristics for Candidates

Since tabular classifiers might output either lowercased taxon identifiers (such as `"crematogaster"` or `"solenopsis_invicta"`) or capitalized scientific names (`"Crematogaster"` or `"Solenopsis invicta"`), the adapter employs a deterministic casing heuristic to map labels:

* **Scientific Name (`scientific_name`)**:
  - Assigned if the label contains a space (e.g., `"Solenopsis invicta"`).
  - Assigned if the label does not match lowercase snake_case/lowercase rules (e.g., `"Crematogaster"`).
* **Taxon Identifier (`taxon_id`)**:
  - Assigned if the label contains an underscore `_` and is entirely lowercase (e.g., `"solenopsis_invicta"`).
  - Assigned if the label is entirely lowercase (e.g., `"crematogaster"`).

*Note: These formatting classifications are heuristics. Final taxon validation, synonym mapping, and alias resolution are always deferred downstream to the taxonomic registry via the KeyReasoner.*

---

## CLI Usage

The prediction-artifact adapter is integrated directly into the `antid.keys` command-line utility via the `convert-predictions` subcommand.

### Command Syntax

```bash
PYTHONPATH=src .venv/bin/python -m antid.keys.cli convert-predictions \
  --predictions-csv <path_to_csv> \
  --output-json <path_to_output_json> \
  --top-k <limit_candidates_count>
```

### Parameters
* `--predictions-csv` (Required): Path to the input tabular CSV predictions file.
* `--output-json` (Required): Path where the standardized JSON array will be written.
* `--top-k` (Optional, Default: 3): Maximum number of visual candidates to include per record.

---

## JSON Output Schema Example

When a tabular prediction row is converted, it yields a standardized visual prediction object:

```json
[
  {
    "image_id": "casent0123456_profile",
    "view_type": "profile",
    "visual_candidates": [
      {
        "taxon_id": null,
        "scientific_name": "Crematogaster",
        "score": 0.85,
        "rank": 1
      },
      {
        "taxon_id": "solenopsis",
        "scientific_name": null,
        "score": 0.15,
        "rank": 2
      }
    ],
    "observed_traits": {},
    "metadata": {
      "image_path": "data/raw/images/crematogaster_ashmeadi/casent0123456_profile.jpg",
      "true_label": "crematogaster",
      "pred_label": "",
      "split": "test",
      "source": "antweb",
      "top1_prob": 0.85,
      "top2_prob": 0.15,
      "confidence": "",
      "adapter_source": "prediction_artifact_adapter"
    }
  }
]
```
