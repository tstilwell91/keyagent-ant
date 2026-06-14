"""Prediction artifact adapter that converts predictions.csv rows into model-output schema.

Bridges raw machine learning evaluator predictions with the taxonomic reasoning adapter.
Supports extracting visual candidates, inferring image_id and view_type, and preserving
all model metrics in metadata.
"""

import os
import csv
from typing import Dict, Any, List, Optional


def classify_label_formatting(label: str) -> bool:
    """Determines whether a label is a scientific_name (True) or taxon_id (False).

    This is strictly a formatting heuristic:
    - If label contains a space, treat it as scientific_name.
    - Else if label contains "_" and is lowercase/snake_case, treat it as taxon_id.
    - Else if label is fully lowercase, treat it as taxon_id.
    - Else treat it as scientific_name.

    NOTE: This is strictly a formatting/syntax heuristic. Final taxon validation, registry
    checks, and alias resolution must happen downstream via KeyReasoner.resolve_candidate_taxa.
    """
    if " " in label:
        return True  # scientific_name
    elif "_" in label and label.islower():
        return False  # taxon_id
    elif label.islower():
        return False  # taxon_id
    else:
        return True  # scientific_name


def prediction_row_to_model_output(
    row: Dict[str, Any],
    top_k: int = 5,
    observed_traits: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Converts a single dict-like predictions CSV row into the model-output schema.

    Args:
        row: A dictionary containing prediction metrics and image metadata from a CSV row.
        top_k: The maximum number of top candidates to extract (default: 5).
        observed_traits: Optional physical traits dict. Defaults to empty dictionary.

    Returns:
        A JSON-serializable dictionary matching the model-output schema.
    """
    # 1. Extract image_id
    image_id = None
    if "image_id" in row and row["image_id"]:
        image_id = str(row["image_id"]).strip()
    elif "image_path" in row and row["image_path"]:
        # Fallback to the file stem of the image path
        filename = os.path.basename(str(row["image_path"]).strip())
        image_id = os.path.splitext(filename)[0]

    if not image_id:
        raise ValueError("Could not extract a valid image_id or image_path stem from row.")

    # 2. Extract view_type
    view_type = None
    if "view_type" in row and row["view_type"]:
        view_type = str(row["view_type"]).strip().lower()
    else:
        # Infer view_type by scanning for keywords in image_path or image_id
        search_target = ""
        if "image_path" in row and row["image_path"]:
            search_target = str(row["image_path"]).lower()
        elif "image_id" in row and row["image_id"]:
            search_target = str(row["image_id"]).lower()

        if "profile" in search_target:
            view_type = "profile"
        elif "head" in search_target:
            view_type = "head"
        elif "dorsal" in search_target:
            view_type = "dorsal"

    # 3. Extract visual candidates up to top_k
    candidates = []

    # Attempt to locate standard multi-class prediction patterns first
    for i in range(1, top_k + 1):
        lbl_col = f"top{i}_label"
        prob_col = f"top{i}_prob"

        # Look for alternative metric columns
        if prob_col not in row:
            prob_col = f"top{i}_score"
        if prob_col not in row:
            prob_col = f"top{i}_confidence"

        if lbl_col in row and row[lbl_col] is not None:
            lbl_val = str(row[lbl_col]).strip()
            if lbl_val:
                prob_val = 1.0
                if prob_col in row and row[prob_col] is not None:
                    try:
                        prob_val = float(row[prob_col])
                    except (ValueError, TypeError):
                        prob_val = 1.0
                candidates.append((lbl_val, prob_val))

    # Support alternative evaluator outputs (single top prediction)
    if not candidates:
        if "pred_label" in row and row["pred_label"] is not None:
            lbl_val = str(row["pred_label"]).strip()
            if lbl_val:
                prob_val = 1.0
                if "confidence" in row and row["confidence"] is not None:
                    try:
                        prob_val = float(row["confidence"])
                    except (ValueError, TypeError):
                        prob_val = 1.0
                candidates.append((lbl_val, prob_val))

    # Format candidates
    visual_candidates = []
    for idx, (label, score) in enumerate(candidates, start=1):
        is_scientific = classify_label_formatting(label)
        
        taxon_id = None
        scientific_name = None
        if is_scientific:
            scientific_name = label
        else:
            taxon_id = label

        visual_candidates.append({
            "taxon_id": taxon_id,
            "scientific_name": scientific_name,
            "score": score,
            "rank": idx
        })

    # Limit to top_k
    visual_candidates = visual_candidates[:top_k]

    # Ensure we got at least one candidate
    if not visual_candidates:
        # If there are column headers like top1_label but all row values are empty
        raise ValueError(f"No valid visual candidates could be extracted for image_id '{image_id}'.")

    # 4. Handle observed_traits (default to empty dict if missing)
    if observed_traits is None:
        observed_traits = {}

    # 5. Build rich metadata
    metadata = {}
    metadata_fields = ["image_path", "true_label", "pred_label", "split", "source"]
    for field in metadata_fields:
        if field in row and row[field] is not None:
            metadata[field] = row[field]

    # Capture all probability, score, or confidence columns to aid debugging/diagnostics
    for key, val in row.items():
        if any(substring in key.lower() for substring in ["prob", "score", "confidence"]) and key not in metadata:
            try:
                metadata[key] = float(val) if val is not None else None
            except (ValueError, TypeError):
                metadata[key] = val

    metadata["adapter_source"] = "prediction_artifact_adapter"

    return {
        "image_id": image_id,
        "view_type": view_type,
        "visual_candidates": visual_candidates,
        "observed_traits": observed_traits,
        "metadata": metadata
    }


def load_predictions_csv(path: str) -> List[Dict[str, Any]]:
    """Loads a predictions CSV file into a list of row dictionaries.

    Args:
        path: Path to the predictions.csv file.

    Returns:
        A list of row dicts.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Predictions CSV file not found: {path}")

    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Filter out any None or empty keys that could come from trailing commas
            clean_row = {k: v for k, v in row.items() if k is not None}
            rows.append(clean_row)
    return rows


def convert_predictions_csv_to_model_outputs(
    path: str,
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """Loads and converts a predictions CSV file into standard model-output dicts.

    Args:
        path: Path to the predictions.csv file.
        top_k: Maximum number of visual candidates to extract per row.

    Returns:
        A list of serialized model-output dictionaries.
    """
    rows = load_predictions_csv(path)
    converted = []
    for idx, row in enumerate(rows, start=1):
        try:
            converted.append(prediction_row_to_model_output(row, top_k=top_k))
        except Exception as e:
            raise ValueError(f"Failed to convert CSV row {idx} (image_id/path: {row.get('image_id') or row.get('image_path')}): {e}")
    return converted
