# Morphological Trait Sidecar Annotation Tooling

This document describes the design, execution, input formats, output schemas, and command-line instructions for the KeyAgent-Ant Morphological Trait Sidecar Annotation Tooling (`trait_sidecar_tools.py`).

---

## Rationale & Architectural Design

The batch key-consistency evaluator and the reasoning integration adapter verify and validate taxonomic identifications by comparing machine-learning visual predictions with taxonomic key rules. However, their utility depends on the presence of observed morphological traits for the specimens being analyzed.

The Trait Sidecar Annotation Tooling provides lightweight, offline, deterministic utilities to generate, validate, and summarize observed-trait sidecar files. By enabling researchers and systems to easily scaffold, validate, and review trait annotations, these tools form the basis of morphological validation pipelines.

```
+------------------+         +----------------------------+         +-------------------------------+
| predictions.csv  | ------> | generate-trait-template    | ------> | poc_observed_traits_template  |
+------------------+         +----------------------------+         +-------------------------------+
                                                                                    |
                                                                                    v (Manual/Semi-manual Annotation)
                                                                                    |
+------------------+         +----------------------------+         +-------------------------------+
|  taxonomic KB    | ------> | validate-traits            | <------ | annotated traits sidecar file |
+------------------+         | summarize-traits           |         +-------------------------------+
                             +----------------------------+
```

---

## Technical Constraints & Safety Boundaries

> [!IMPORTANT]
> **This tooling is strictly offline and deterministic.**
> - It **does not** infer traits automatically.
> - It **does not** make final taxonomic identifications.
> - It **does not** call any LLMs or external APIs (e.g. Gemini, Vertex AI, Firebase).
> - It **does not** invoke any CNN or image classification checkpoints.

The trait sidecar tools exist solely to validate and organize observed morphological evidence. They help support future work with:
- **Concept Bottleneck Models (CBMs)**: Enabling model verification of discrete morphological concepts (e.g. gaster shape, spine count) before making taxonomic predictions.
- **Explainable AI (XAI)**: Grounding taxonomic reasoning in verifiable physical traits rather than end-to-end classification probability scores.
- **Manual Annotation Workflows**: Scaffolding blank trait templates for taxonomists to populate manually or semi-manually.

---

## Sidecar Data Formats

The sidecar files represent the physical trait observations of individual specimens/images. Supported in both standard JSON mapping and line-by-line JSONL formats:

### 1. Flat JSON Mapping
A single JSON object mapping each `image_id` to its nested `observed_traits` dictionary:
```json
{
  "casent0123456_profile": {
    "postpetiole_attachment": "dorsal_surface_first_gastral_segment",
    "gaster_shape_dorsal": "heart_shaped",
    "petiole_node_state": "no_node_dorsoventrally_flattened"
  }
}
```

### 2. Line-by-Line JSONL
A text file where each line is a valid, independent JSON object defining `image_id`, `view_type`, `observed_traits`, and `metadata`:
```json
{"image_id": "casent0123456_profile", "view_type": "profile", "observed_traits": {"postpetiole_attachment": "dorsal_surface_first_gastral_segment"}, "metadata": {}}
{"image_id": "casent0789101_profile", "view_type": "profile", "observed_traits": {"postpetiole_attachment": "dorsal_surface_first_gastral_segment"}, "metadata": {}}
```

---

## CLI Usage and Subcommands

The tooling is integrated into the `antid.keys` command-line interface under three distinct subcommands.

### 1. Generate Trait Annotation Template

Scaffolds a blank JSONL template using prediction outputs, populating `image_id`, `view_type`, and `metadata` from the source predictions CSV while keeping `observed_traits` completely blank.

#### Command
```bash
PYTHONPATH=src .venv/bin/python -m antid.keys.cli generate-trait-template \
  --predictions-csv examples/kb/mock_predictions.csv \
  --output-jsonl data/traits/poc_observed_traits_template.jsonl \
  --max-records 10
```

#### Parameters
- `--predictions-csv` (Required): Path to the tabular predictions CSV.
- `--output-jsonl` (Required): Destination path for the JSONL template (the parent directory is created automatically if it does not exist).
- `--max-records` (Optional): Maximum number of records to write.
- `--no-empty-traits` (Optional): If set, disables the empty `observed_traits` dictionary output.

#### Output
```json
{
  "status": "success",
  "message": "Successfully generated blank trait annotation template with 3 records.",
  "output_file": "data/traits/poc_observed_traits_template.jsonl",
  "records_count": 3
}
```

---

### 2. Validate Observed Traits

Strictly validates every entry in a traits sidecar against the taxonomic KB trait schema, checking if each `trait_id` is registered and if its observed value is permitted by `trait_schema.yaml`.

#### Command
```bash
PYTHONPATH=src .venv/bin/python -m antid.keys.cli validate-traits \
  --kb-dir data/kb/poc_myrmicinae_mem \
  --observed-traits examples/kb/mock_observed_traits.json
```

#### Output (Success)
```json
{
  "status": "success",
  "records_count": 2,
  "invalid_records": [],
  "trait_counts": {
    "postpetiole_attachment": 2,
    "gaster_shape_dorsal": 2,
    "petiole_node_state": 2
  }
}
```

#### Output (Error)
If unknown trait IDs or non-permitted values are found, the command exits with status code `1` and prints:
```json
{
  "status": "error",
  "records_count": 1,
  "invalid_records": [
    {
      "image_id": "casent0123456_profile",
      "trait_id": "gaster_shape_dorsal",
      "value": "invalid_unallowed_shape",
      "error": "Value 'invalid_unallowed_shape' is not allowed for trait 'gaster_shape_dorsal'. Allowed values: ['heart_shaped', 'not_heart_shaped', 'unknown']"
    }
  ],
  "trait_counts": {}
}
```

---

### 3. Summarize Trait Sidecar Coverage

Analyzes the level of annotation completeness, counting total records, individual trait observations, missing schema traits, observed schema traits, and calculating exact coverage rates and value frequencies per trait defined in the schema.

#### Command
```bash
PYTHONPATH=src .venv/bin/python -m antid.keys.cli summarize-traits \
  --kb-dir data/kb/poc_myrmicinae_mem \
  --observed-traits examples/kb/mock_observed_traits.json
```

#### Output
```json
{
  "records_count": 2,
  "total_trait_observations": 6,
  "records_with_no_traits": 0,
  "trait_frequency": {
    "postpetiole_attachment": 2,
    "gaster_shape_dorsal": 2,
    "petiole_node_state": 2
  },
  "value_frequency_by_trait": {
    "postpetiole_attachment": {
      "dorsal_surface_first_gastral_segment": 2
    },
    "gaster_shape_dorsal": {
      "heart_shaped": 2
    },
    "petiole_node_state": {
      "no_node_dorsoventrally_flattened": 2
    }
  },
  "missing_schema_traits": [
    "antenna_club_segments",
    "antenna_segment_count",
    "antennal_scrobe_position",
    "clypeus_longitudinal_carinae",
    "frontal_carinae_state",
    "mandible_tooth_count",
    "propodeal_armament",
    "spongiform_tissue_petiole_postpetiole"
  ],
  "observed_schema_traits": [
    "gaster_shape_dorsal",
    "petiole_node_state",
    "postpetiole_attachment"
  ],
  "coverage_rate_by_schema_trait": {
    "postpetiole_attachment": 1.0,
    "gaster_shape_dorsal": 1.0,
    "petiole_node_state": 1.0,
    "antenna_segment_count": 0.0,
    "antennal_scrobe_position": 0.0,
    "antenna_club_segments": 0.0,
    "spongiform_tissue_petiole_postpetiole": 0.0,
    "frontal_carinae_state": 0.0,
    "clypeus_longitudinal_carinae": 0.0,
    "propodeal_armament": 0.0,
    "mandible_tooth_count": 0.0
  },
  "schema_trait_count": 11,
  "covered_schema_trait_count": 3
}
```

---

## Limitations

1. **Static Schema Dependencies**: The validation and coverage summary are strictly bound to the configuration of `trait_schema.yaml`. Changing the schema will immediately affect the validation state of any pre-existing sidecar files.
2. **Deterministic Syntactic Checking Only**: The validation system only evaluates syntactic conformity (i.e. whether trait IDs and values match schema definitions). It does not assess the biological or context-level accuracy of the physical trait claims.
