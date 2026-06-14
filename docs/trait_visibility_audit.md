# Trait Visibility and Evidence Readiness Audit

This document describes the purpose, design, execution flow, input/output schemas, and command-line instructions for the **Trait Visibility and Evidence Readiness Audit** (`trait_visibility_audit.py`).

---

## Why This Audit Exists

Before deploying deep learning classifiers or launching large-scale manual annotation campaigns, it is critical to verify that our digital assets (specimen image paths, taxonomic registrations, and morphological trait schemas) are aligned. 

The **Trait Visibility and Evidence Readiness Audit** serves as a pre-flight sanity check. It performs a completely **deterministic, offline, additive, and unit-testable evaluation** of:
1. Whether selected specimens have valid image paths.
2. Whether those image files physically exist and are readable on disk.
3. Whether our morphological trait schema contains the necessary metadata (such as body regions and view requirements).
4. Whether the available specimen views align with the views required to observe specific key-relevant traits.

---

## Neuro-Symbolic System Context & Non-Evidentiary Design

KeyAgent-Ant uses a **neuro-symbolic design** to identify biological specimens:
* **Neural Component**: Deep convolutional networks or vision-language models predict species probabilities and detect physical trait features from tri-view images.
* **Symbolic Component**: A Taxonomic Knowledge Base (KB) containing logical keys and rules reasons over morphological traits to validate, rank, or explain identification candidates.

```
       +---------------------------------------------+
       |             Selected Specimens              |
       |  (tri-view image paths & metadata from CSV) |
       +---------------------------------------------+
                              |
                              v
       +---------------------------------------------+
       |        Deterministic Offline Audit         |
       |  (compares available views with KB rules)   |
       +---------------------------------------------+
                              |
         +--------------------+--------------------+
         |                                         |
         v                                         v
+------------------+                     +------------------+
| Specimen Readiness |                     |  Schema Readiness |
|   (Image Paths)  |                     |  (View Metadata) |
+------------------+                     +------------------+
         |                                         |
         +--------------------+--------------------+
                              |
                              v
       +---------------------------------------------+
       |         Evidence & Curation Decisions       |
       |  (proceed to annotation / adjust metadata)  |
       +---------------------------------------------+
```

### CRITICAL: Zero Morphology Values Assigned
This audit is **strictly non-evidentiary**:
* It **never assigns biological trait values** (e.g., it does not state whether a specimen has propodeal spines).
* It **never infers traits** from genus/species labels.
* It is purely concerned with **readiness and visibility**—meaning, does the physical evidence exist to allow a human or model to make an observation?

---

## Audit Output Files and Schemas

Executing the audit generates five structured outputs inside the designated output directory (e.g., `data/traits/trait_curated_v0_audit/`):

### 1. `specimen_image_readiness.csv`
Per-specimen audit of physical image readability, dimensions, and path existence.

| Column | Type | Description |
| :--- | :--- | :--- |
| `specimen_id` | String | Unique specimen identifier (e.g., CASENT number). |
| `catalog_number` | String | Catalog number from metadata. |
| `kb_taxon_id` | String | Resolved KB taxon ID. |
| `kb_scientific_name` | String | Scientific name mapped in KB. |
| `dataset_genus` | String | Genus label from dataset. |
| `dataset_species` | String | Species label from dataset. |
| `source_split` | String | Dataset split (`test`, `val`, or `train`). |
| `dorsal_image_path` | String | Mapped path to the dorsal view image. |
| `dorsal_exists` | Boolean | Whether the dorsal image file exists on disk. |
| `dorsal_width` | Integer/Null | Pixel width of dorsal image (if readable). |
| `dorsal_height` | Integer/Null | Pixel height of dorsal image (if readable). |
| `head_image_path` | String | Mapped path to the head view image. |
| `head_exists` | Boolean | Whether the head image file exists on disk. |
| `head_width` | Integer/Null | Pixel width of head image (if readable). |
| `head_height` | Integer/Null | Pixel height of head image (if readable). |
| `profile_image_path`| String | Mapped path to the profile view image. |
| `profile_exists` | Boolean | Whether the profile image file exists on disk. |
| `profile_width` | Integer/Null | Pixel width of profile image (if readable). |
| `profile_height`| Integer/Null | Pixel height of profile image (if readable). |
| `all_views_present` | Boolean | Whether all three standard view paths are present. |
| `all_view_files_exist`| Boolean | Whether all three image files physically exist on disk. |
| `duplicate_view_counts`| String | Counts of alternative/duplicate views found. |
| `readiness_status` | Enum | `ready`, `missing_image_path`, `missing_image_file`, `invalid_kb_taxon`, `invalid_template_record`, `warning`. |
| `notes` | String | Descriptive audit logs or warnings. |

### 2. `trait_schema_readiness.csv`
Audit of traits defined in `trait_schema.yaml`, detailing their usage in couplet rules and view requirements.

| Column | Type | Description |
| :--- | :--- | :--- |
| `trait_id` | String | Uniquely identifies the trait. |
| `trait_name` | String | Human-readable label for the trait. |
| `allowed_values` | String | Semi-colon separated list of valid categorical states. |
| `visible_in_views` | String | Comma-separated list of standard views showing this trait. |
| `body_region` | String | Affected biological body region. |
| `used_in_key_rules` | Boolean | Whether the trait is evaluated in any couplet rule. |
| `key_rule_ids` | String | Comma-separated list of key rules evaluating this trait. |
| `affected_taxa` | String | List of terminal taxa impacted by rules using this trait. |
| `has_allowed_values`| Boolean | True if schema defines non-empty allowed values. |
| `has_view_metadata` | Boolean | True if schema defines non-empty required views. |
| `schema_readiness_status`| Enum | `ready_for_visibility_mapping`, `missing_allowed_values`, `missing_view_metadata`, `not_used_in_current_key`, `requires_schema_review`. |
| `notes` | String | Descriptive schema warnings. |

### 3. `specimen_trait_visibility_matrix.csv`
Detailed cross-product mapping of selected specimens against schema traits to evaluate visibility readiness.

| Column | Type | Description |
| :--- | :--- | :--- |
| `specimen_id` | String | Unique specimen identifier. |
| `catalog_number` | String | Catalog number. |
| `kb_taxon_id` | String | Resolved KB taxon. |
| `dataset_genus` | String | Dataset genus. |
| `dataset_species` | String | Dataset species. |
| `trait_id` | String | Mapped schema trait. |
| `expected_views` | String | Views required to evaluate this trait. |
| `available_views`| String | Views present on disk for this specimen. |
| `usable_image_paths`| String| Semicolon-separated path(s) to images covering expected views. |
| `used_in_key_rules`| Boolean | Whether this trait is used in any key rule. |
| `visibility_status`| Enum | `ready_for_image_review`, `missing_required_view`, `schema_missing_view_metadata`, `not_used_in_current_key`, `requires_expert_review`, `not_image_auditable_unknown`. |
| `review_recommendation`| Enum| `inspect_dorsal`, `inspect_head`, `inspect_profile`, `inspect_multiple_views`, `schema_review_needed`, `expert_review_needed`, `defer`. |
| `notes` | String | Diagnostic notes. |

### 4. `kb_subset_coverage.json`
Exposes representation and testability gap metrics for the selected specimens.

* **`represented_kb_taxa`**: KB taxa represented by at least one selected specimen.
* **`unrepresented_kb_taxa`**: KB taxa completely missing from the selection.
* **`taxa_with_insufficient_specimens`**: List of taxa lacking selection specimens.
* **`represented_rules_exercised`**: Rules that can be tested by specimens in the selection.
* **`unrepresented_rules`**: Rules that cannot be exercised due to missing taxa.
* **`represented_traits_used`**: Traits used by rules associated with represented taxa.
* **`unrepresented_traits`**: Traits not used by rules for represented taxa.

### 5. `summary.json`
A consolidated JSON report aggregating high-level metrics for CLI display and build-pipeline status checks.

---

## Running the Audit

The audit can be triggered via the `antid.keys.cli` tool:

```bash
PYTHONPATH=src .venv/bin/python -m antid.keys.cli audit-trait-visibility \
  --kb-dir data/kb/poc_myrmicinae_mem \
  --selection-csv data/traits/trait_curated_v0_selection.csv \
  --annotation-template data/traits/trait_curated_v0_annotation_template.jsonl \
  --image-root . \
  --output-dir data/traits/trait_curated_v0_audit
```

---

## Interpreting Statuses and Decisions

The audit outputs inform several high-level developer and curator decisions:

### A. Specimen Readiness Statuses
* **`ready`**: Tri-view image paths are complete, and all three files physically exist on disk and are readable.
* **`missing_image_path`**: One or more required tri-view paths are blank in the selection CSV.
* **`missing_image_file`**: Path exists, but the physical file is missing from disk.
* **`warning`**: Paths exist and files are present, but PIL reported readability warnings or size anomalies.

### B. Schema Readiness Statuses
* **`ready_for_visibility_mapping`**: Trait is fully defined with valid allowed values and view metadata, and is actively used in KB key rules.
* **`missing_view_metadata`**: Trait is missing the `visible_in_views` parameter in the schema, meaning we cannot deterministically map required images.
* **`not_used_in_current_key`**: Trait is defined in the schema but is not referenced by any rules in `key_rules.json`.

### C. Visibility Statuses
* **`ready_for_image_review`**: The trait is used in the key, view metadata is defined, and the required specimen views are present on disk.
* **`missing_required_view`**: The trait is used in the key, but one or more required views are missing or unreadable on disk for this specimen.

---

## Strategic Decisions the Audit Informs

The audit reports are designed to guide the next development steps:

1. **Proceed to Source-Backed Evidence Collection**:
   * *Trigger*: Specimen readiness is `ready` and visibility matrix is `ready_for_image_review` for all key-relevant traits.
   * *Action*: We can safely launch visual annotation reviews or pass specimen images to neural feature extractors.
2. **Revise Trait Schema View Metadata**:
   * *Trigger*: High count of `schema_missing_view_metadata` or `missing_view_metadata`.
   * *Action*: Coordinate with biological experts to update `trait_schema.yaml` with correct camera views.
3. **Revise Selected Specimen Subset**:
   * *Trigger*: High count of `missing_image_file` or unrepresented key taxa/rules in `kb_subset_coverage.json`.
   * *Action*: Run the specimen curation selection script again, or verify dataset downloads to resolve missing files.
4. **Seek Expert Review for Specific Traits**:
   * *Trigger*: Visibility status is `requires_expert_review` or `not_image_auditable_unknown`.
   * *Action*: Flags traits that cannot be easily inspected from standard 2D macro photographs, prompting alternative physical specimen check workflows.
5. **Defer Trait-Supervised Modeling Until Evidence Exists**:
   * *Trigger*: Specimens have `missing_image_file` status.
   * *Action*: Warns the development team to pause neural model training pipelines targeting those traits until the underlying images have been downloaded.
