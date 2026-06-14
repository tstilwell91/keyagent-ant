# Taxonomic KB Reasoning Integration Adapter

This document describes the design, schema, and command-line instructions for the KeyAgent-Ant Taxonomic KB Reasoning Integration Adapter. This layer integrates raw vision model (CNN) predictions with deterministic dichotomous key reasoning to produce an integrated, structured evidence packet.

---

## Architectural Role & Scope

The integration adapter operates as a bridging layer between machine-learning visual predictions and biological taxonomic knowledge bases. It performs structured data validation, executes deterministic key reasoning, computes visual/taxonomic agreements, and maps next recommended actions.

> [!IMPORTANT]
> **Defensive Safety Boundary**:
> The adapter is explicitly designed to **assemble structured evidence only** and must not make the final taxonomic decision or identification. 
> To enforce this boundary, every assembled packet contains explicit non-decision fields:
> ```json
> {
>   "final_identification": null,
>   "identification_decision_policy": "not_applied"
> }
> ```
> Downstream decision-making agents or human experts are responsible for reviewing the assembled evidence and formulating final classifications.

---

## Assembled Evidence Schema

The adapter processes visual prediction vectors and observed physical traits, outputting a structured `ReasoningEvidencePacket`. This packet is strictly validated and converted into a standard serializable dictionary.

### Assembled Packet Structure

The output dictionary contains the following major blocks:

1. **Identifiers**:
   - `image_id`: Unique string ID of the specimen image.
   - `view_type`: Optional image view orientation (`head`, `profile`, `dorsal`).
2. **Visual Candidates**:
   - Array of visual classifications representing CNN predictions, each containing `taxon_id`, `scientific_name`, `score` (probability), and `rank`.
3. **Observed Traits**:
   - Map of observed morphological traits and their states.
4. **Key Reasoning Output**:
   - The full, transparent output of the underlying `KeyReasoner` engine (scores, matching/conflicting rules, and lists).
5. **Agreement Summary**:
   - A structured comparison object mapping the relationship between the top visual model candidate and the top KB-supported taxon:
     - `status`: One of six explicit statuses (see below).
     - `visual_top_taxon_id`: Resolved taxon ID of the top visual candidate.
     - `key_top_taxon_id`: Taxon ID of the top KB candidate.
     - `visual_top_raw_key_score`: Raw KB score of the top visual candidate.
     - `visual_top_normalized_key_score`: Normalized KB score of the top visual candidate.
     - `reason`: Friendly string explanation of the status.
6. **Conflict Summary**:
   - Filtered list of visual candidates that have active conflicts (`raw_score < 0`), including their model score, rank, raw score, normalized score, and list of conflicting rule IDs.
7. **Missing Trait Summary**:
   - Structured list of unobserved traits needed to resolve candidates, grouped by body region and view visibility.
8. **Structured Recommended Next Action**:
   - Normalized next action object to suggest targeted observations:
     - `action_type`: `"observe_trait"` if there are unresolved traits on the top candidate's path; otherwise `"none"`.
     - `trait_id`: The ID of the specific trait recommended to observe next.
     - `reason`: Explanatory message from the key.
     - `source`: Always `"kb_reasoner"`.
     - `raw_recommendation`: The raw original recommendation string.
9. **Limitations**:
   - Geographic scope, taxonomic scope, and rule limitations inherited from the KB source manifest.

---

## Core Algorithmic Logic

### 1. Six Distinct Agreement Statuses

The adapter maps the relationship between the top visual prediction and the KB reasoning into six distinct, mutually-exclusive statuses:

* `insufficient_trait_evidence`: Assembled when `observed_traits` is empty or no definitive rules are supported/conflicted.
* `visual_top_conflicts_with_key`: Assembled when the top visual candidate has a raw score < 0 or active conflicts.
* `visual_top_tied_for_key_top`: Assembled when the top visual candidate is among multiple candidates tied for the top KB score.
* `key_prefers_different_taxon`: Assembled when the top visual candidate is valid, but the KB ranks a different taxon strictly higher.
* `visual_top_supported_by_key`: Assembled when the top visual candidate has positive support (`raw_score > 0`), no conflicts, and is the unique top KB candidate.
* `visual_top_unresolved_by_key`: Assembled when the top visual candidate has only unresolved rules (raw score 0), no conflicts, and is the unique top candidate.

### 2. Deterministic Tie-Breaking Behavior

When multiple taxa have identical scores (identical `normalized_score` and `raw_score`), the adapter sorts them **alphabetically by taxon_id**. This ensures a completely stable, deterministic ranking order across ties:

* Sort alphabetically by `taxon_id` ascending first.
* Sort by scores descending next.
* If the visual top candidate is tied for the top KB score, it is classified as `visual_top_tied_for_key_top` instead of `key_prefers_different_taxon`.

---

## CLI Integration & Usage

You can run the integration adapter using the CLI's `integrate` subcommand.

### Command Syntax

```bash
PYTHONPATH=src .venv/bin/python -m antid.keys.cli integrate \
  --kb-dir <kb_directory_path> \
  --model-output <model_output_json_path>
```

### Command Options

* `--kb-dir`: Absolute or relative path to the taxonomic KB directory (e.g. `data/kb/poc_myrmicinae_mem`).
* `--model-output`: Path to a JSON file containing model visual predictions and observed traits.
* `--no-candidate-filter`: If specified, the reasoner will evaluate all registered taxa in the KB rather than restricting itself to the visual candidates.

---

## Assembled Evidence Mock CLI Run Examples

### 1. Visual Top Supported by Key

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
    "reason": "Taxon 'Crematogaster' is fully supported by the key based on observed traits.",
    "source": "kb_reasoner",
    "raw_recommendation": "Taxon 'Crematogaster' is fully supported by the key based on observed traits."
  },
  "final_identification": null,
  "identification_decision_policy": "not_applied"
}
```

### 2. Visual Top Conflicts with Key

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
  "agreement_summary": {
    "status": "visual_top_conflicts_with_key",
    "visual_top_taxon_id": "solenopsis",
    "key_top_taxon_id": "crematogaster",
    "visual_top_raw_key_score": -1,
    "visual_top_normalized_key_score": -0.16666666666666666,
    "reason": "Top visual candidate 'solenopsis' has conflicting rules in the taxonomic key."
  },
  "conflict_summary": [
    {
      "taxon_id": "solenopsis",
      "score": 0.9,
      "rank": 1,
      "key_raw_score": -1,
      "key_normalized_score": -0.16666666666666666,
      "conflicting_rules": [
        "mem_myrmicinae_001b"
      ]
    }
  ],
  "final_identification": null,
  "identification_decision_policy": "not_applied"
}
```
