"""Trait sidecar annotation tooling module.

Provides utilities to generate, validate, and summarize observed-trait sidecar files.
Supports JSON and JSONL sidecar formats and facilitates manual or semi-manual annotation workflows.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from .kb_loader import load_kb
from .key_consistency_evaluator import load_observed_traits_sidecar
from .prediction_artifact_adapter import convert_predictions_csv_to_model_outputs


def validate_observed_traits_sidecar(
    kb_dir: str,
    observed_traits_path: str
) -> Dict[str, Any]:
    """Validates every observed trait in a sidecar against the taxonomic KB trait schema.

    Args:
        kb_dir: Path to the taxonomic KB directory.
        observed_traits_path: Path to the JSON/JSONL observed-traits sidecar file.

    Returns:
        A JSON-serializable report dictionary:
        {
          "status": "success" or "error",
          "records_count": int,
          "invalid_records": [
            {
              "image_id": "...",
              "trait_id": "...",
              "value": "...",
              "error": "..."
            }
          ],
          "trait_counts": {
            "trait_id": int
          }
        }
    """
    # 1. Load the Knowledge Base (strictly validates schema files internally)
    kb = load_kb(kb_dir)
    trait_defs = kb["trait_defs"]

    # 2. Load the observed traits sidecar
    sidecar_traits = load_observed_traits_sidecar(observed_traits_path)

    invalid_records = []
    trait_counts = {}

    # 3. Perform row-by-row validation of observed traits
    for img_id, traits in sidecar_traits.items():
        if not isinstance(traits, dict):
            invalid_records.append({
                "image_id": img_id,
                "trait_id": None,
                "value": None,
                "error": f"Observed traits for record '{img_id}' is not a dictionary. Got type: {type(traits).__name__}"
            })
            continue

        for t_id, val in traits.items():
            if t_id not in trait_defs:
                invalid_records.append({
                    "image_id": img_id,
                    "trait_id": t_id,
                    "value": val,
                    "error": f"Trait ID '{t_id}' is not defined in the trait schema."
                })
            else:
                allowed_values = trait_defs[t_id].get("allowed_values", [])
                if val not in allowed_values:
                    invalid_records.append({
                        "image_id": img_id,
                        "trait_id": t_id,
                        "value": val,
                        "error": f"Value '{val}' is not allowed for trait '{t_id}'. Allowed values: {allowed_values}"
                    })
                else:
                    # Accumulate valid trait counts
                    trait_counts[t_id] = trait_counts.get(t_id, 0) + 1

    status = "error" if invalid_records else "success"

    return {
        "status": status,
        "records_count": len(sidecar_traits),
        "invalid_records": invalid_records,
        "trait_counts": trait_counts
    }


def summarize_trait_sidecar_coverage(
    kb_dir: str,
    observed_traits_path: str
) -> Dict[str, Any]:
    """Generates a coverage and frequency summary report for an observed-traits sidecar.

    Args:
        kb_dir: Path to the taxonomic KB directory.
        observed_traits_path: Path to the JSON/JSONL observed-traits sidecar file.

    Returns:
        A dictionary containing coverage summary statistics:
        {
          "records_count": int,
          "total_trait_observations": int,
          "records_with_no_traits": int,
          "trait_frequency": {trait_id: count},
          "value_frequency_by_trait": {trait_id: {value: count}},
          "missing_schema_traits": [trait_id],
          "observed_schema_traits": [trait_id],
          "coverage_rate_by_schema_trait": {trait_id: float},
          "schema_trait_count": int,
          "covered_schema_trait_count": int
        }
    """
    kb = load_kb(kb_dir)
    trait_defs = kb["trait_defs"]
    schema_trait_ids = set(trait_defs.keys())

    sidecar_traits = load_observed_traits_sidecar(observed_traits_path)

    records_count = len(sidecar_traits)
    total_trait_observations = 0
    records_with_no_traits = 0
    trait_frequency = {}
    value_frequency_by_trait = {}

    for img_id, traits in sidecar_traits.items():
        if not isinstance(traits, dict):
            continue

        valid_obs_count = 0
        for t_id, val in traits.items():
            if t_id in trait_defs:
                allowed_values = trait_defs[t_id].get("allowed_values", [])
                if val in allowed_values:
                    valid_obs_count += 1
                    trait_frequency[t_id] = trait_frequency.get(t_id, 0) + 1
                    
                    if t_id not in value_frequency_by_trait:
                        value_frequency_by_trait[t_id] = {}
                    value_frequency_by_trait[t_id][val] = value_frequency_by_trait[t_id].get(val, 0) + 1

        if valid_obs_count == 0:
            records_with_no_traits += 1
        total_trait_observations += valid_obs_count

    # Identify missing vs observed schema traits
    observed_schema_traits_set = set(trait_frequency.keys()) & schema_trait_ids
    missing_schema_traits = sorted(list(schema_trait_ids - observed_schema_traits_set))
    observed_schema_traits = sorted(list(observed_schema_traits_set))

    # Compute coverage rates per schema trait
    coverage_rate_by_schema_trait = {}
    for t_id in schema_trait_ids:
        count = trait_frequency.get(t_id, 0)
        rate = float(count) / records_count if records_count > 0 else 0.0
        coverage_rate_by_schema_trait[t_id] = rate

    schema_trait_count = len(schema_trait_ids)
    covered_schema_trait_count = len(observed_schema_traits_set)

    return {
        "records_count": records_count,
        "total_trait_observations": total_trait_observations,
        "records_with_no_traits": records_with_no_traits,
        "trait_frequency": trait_frequency,
        "value_frequency_by_trait": value_frequency_by_trait,
        "missing_schema_traits": missing_schema_traits,
        "observed_schema_traits": observed_schema_traits,
        "coverage_rate_by_schema_trait": coverage_rate_by_schema_trait,
        "schema_trait_count": schema_trait_count,
        "covered_schema_trait_count": covered_schema_trait_count
    }


def generate_trait_annotation_template(
    predictions_csv: str,
    output_jsonl: str,
    max_records: Optional[int] = None,
    include_empty_traits: bool = True
) -> None:
    """Generates a blank trait annotation scaffold (JSONL format) from a predictions CSV.

    Args:
        predictions_csv: Path to the input predictions.csv.
        output_jsonl: Path to save the blank JSONL template.
        max_records: Maximum number of records to write.
        include_empty_traits: If True, writes "observed_traits": {} in the template.
    """
    # 1. Load predictions and convert them using the prediction adapter
    model_outputs = convert_predictions_csv_to_model_outputs(predictions_csv)

    # Apply record limit if provided
    if max_records is not None:
        model_outputs = model_outputs[:max_records]

    # 2. Ensure the parent directory of the output JSONL file exists
    Path(output_jsonl).parent.mkdir(parents=True, exist_ok=True)

    # 3. Write line-by-line JSONL records
    with open(output_jsonl, "w", encoding="utf-8") as f:
        for mo in model_outputs:
            out_record = {
                "image_id": mo["image_id"],
                "view_type": mo.get("view_type"),
                "observed_traits": {} if include_empty_traits else {},
                "metadata": mo.get("metadata", {})
            }
            f.write(json.dumps(out_record) + "\n")
