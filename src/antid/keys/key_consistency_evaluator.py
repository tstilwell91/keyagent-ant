"""Batch key-consistency evaluation harness.

Runs tabular predictions through the prediction-artifact adapter and reasoning adapter,
and aggregates KB agreement, conflict, and missing trait/rule statistics across all records.
"""

import os
import json
from typing import Dict, Any, List, Optional, Union
from .kb_loader import load_kb
from .prediction_artifact_adapter import convert_predictions_csv_to_model_outputs
from .reasoning_adapter import build_reasoning_evidence_packet


def load_observed_traits_sidecar(path: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """Loads observed physical traits sidecar from a JSON or JSONL file.

    Accepted JSON format:
    {
      "image_id_1": {
        "trait_id": "value"
      }
    }

    Accepted JSONL format:
    {"image_id": "image_id_1", "observed_traits": {"trait_id": "value"}}
    {"image_id": "image_id_2", "observed_traits": {"trait_id": "value"}}

    Args:
        path: Path to the JSON or JSONL sidecar file. If None, returns an empty dict.

    Returns:
        A dictionary mapping image_id to its physical traits dictionary.
    """
    if not path:
        return {}

    if not os.path.exists(path):
        raise FileNotFoundError(f"Observed traits sidecar file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
    except Exception as e:
        raise ValueError(f"Failed to read sidecar file '{path}': {e}")

    if not content:
        return {}

    # Try full JSON loading
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            # Check if this is actually a single-line JSONL record
            if "image_id" in data and "observed_traits" in data:
                pass  # Fall through to JSONL parsing
            else:
                is_valid_full_json = True
                for img_id, traits in data.items():
                    if not isinstance(traits, dict):
                        is_valid_full_json = False
                        break
                if is_valid_full_json:
                    return data
    except json.JSONDecodeError:
        pass

    # Fallback to line-by-line JSONL loading
    traits_map = {}
    for line_num, line in enumerate(content.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError("Line must be a valid JSON object.")
            if "image_id" not in record:
                raise KeyError("Missing required field 'image_id'.")
            if "observed_traits" not in record:
                raise KeyError("Missing required field 'observed_traits'.")
            
            img_id = record["image_id"]
            traits = record["observed_traits"]
            if not isinstance(traits, dict):
                raise TypeError("'observed_traits' must be a JSON object/dictionary.")
            
            traits_map[img_id] = traits
        except Exception as e:
            raise ValueError(f"Error parsing JSONL sidecar on line {line_num}: {e}")

    return traits_map


def evaluate_predictions_csv_with_kb(
    kb_dir: str,
    predictions_csv: str,
    top_k: int = 5,
    observed_traits_path: Optional[str] = None,
    candidate_taxa_from_visual: bool = True
) -> Dict[str, Any]:
    """Runs a batch key-consistency evaluation over model predictions.

    Args:
        kb_dir: Path to the taxonomic KB directory.
        predictions_csv: Path to the predictions.csv file.
        top_k: Maximum number of visual candidates to extract per prediction row.
        observed_traits_path: Optional path to a sidecar JSON/JSONL physical traits file.
        candidate_taxa_from_visual: If True, evaluates only candidates from the model predictions.

    Returns:
        A JSON-serializable dictionary containing the batch "summary" metrics
        and the full list of "evidence_packets".
        The summary includes 'meaningful_evidence_records' and 'meaningful_evidence_rate' to separate
        records where the KB had usable trait evidence from records where the system honestly reports
        insufficient evidence. It also tracks 'out_of_scope_candidate_records' and
        'out_of_scope_candidate_rate' separately from biological agreement/conflict.
    """
    # 1. Warm-load the KB first to ensure it is valid
    load_kb(kb_dir)

    # 2. Parse predictions CSV into standardized model-output dictionaries
    model_outputs = convert_predictions_csv_to_model_outputs(predictions_csv, top_k=top_k)

    # 3. Load optional physical traits sidecar mapping
    sidecar_traits = load_observed_traits_sidecar(observed_traits_path)

    # 4. Process each record and build structured reasoning evidence packets
    evidence_packets = []
    out_of_scope_candidate_records = 0
    for mo in model_outputs:
        img_id = mo["image_id"]
        # Attach sidecar physical traits if available, otherwise preserve/default to empty dict
        if img_id in sidecar_traits:
            mo["observed_traits"] = sidecar_traits[img_id]
        
        try:
            packet = build_reasoning_evidence_packet(
                kb_dir_or_dict=kb_dir,
                model_output=mo,
                candidate_taxa_from_visual=candidate_taxa_from_visual
            )
            # Standard successful packet contains no evaluator warnings
            packet["evaluator_warning"] = None
        except ValueError as e:
            # Handle out-of-scope or unregistered/ambiguous candidate taxa gracefully
            out_of_scope_candidate_records += 1
            error_msg = str(e)
            top_vc_id = mo["visual_candidates"][0].get("taxon_id") or mo["visual_candidates"][0].get("scientific_name") if mo.get("visual_candidates") else None
            
            # Formulate fallback/unresolved packet
            status = "insufficient_trait_evidence" if not mo.get("observed_traits") else "visual_top_unresolved_by_key"
            reason = f"Out-of-scope or unregistered visual candidate: {error_msg}"
            
            agreement_summary = {
                "status": status,
                "visual_top_taxon_id": top_vc_id,
                "key_top_taxon_id": None,
                "visual_top_raw_key_score": 0,
                "visual_top_normalized_key_score": 0.0,
                "reason": reason
            }
            
            key_reasoning = {
                "raw_scores": {},
                "normalized_scores": {},
                "supporting_rules": {},
                "conflicting_rules": {},
                "unresolved_rules": {},
                "missing_traits": {"all_missing": []},
                "ranked_taxa": [],
                "recommended_next_action": "Out-of-scope candidate cannot be resolved with the key.",
                "limitations": {"out_of_scope": True, "error": error_msg}
            }
            
            next_action_obj = {
                "action_type": "none",
                "trait_id": None,
                "reason": "Out-of-scope candidate cannot be resolved with the key.",
                "source": "kb_reasoner",
                "raw_recommendation": "Out-of-scope candidate cannot be resolved with the key."
            }
            
            evaluator_warning = {
                "type": "out_of_scope_visual_candidate",
                "message": f"Visual candidate is out of scope or unregistered in the taxonomic knowledge base: {error_msg}",
                "raw_error": error_msg
            }
            
            packet = {
                "image_id": mo["image_id"],
                "view_type": mo.get("view_type"),
                "visual_candidates": mo.get("visual_candidates", []),
                "observed_traits": mo.get("observed_traits", {}),
                "key_reasoning": key_reasoning,
                "agreement_summary": agreement_summary,
                "conflict_summary": [],
                "missing_trait_summary": [],
                "recommended_next_action": next_action_obj,
                "limitations": {"out_of_scope": True, "error": error_msg},
                "final_identification": None,
                "identification_decision_policy": "not_applied",
                "evaluator_warning": evaluator_warning
            }
            
        evidence_packets.append(packet)

    # 5. Aggregate and compute batch summary statistics
    total_records = len(evidence_packets)

    # Pre-initialize counts for all 6 mutually exclusive agreement statuses to prevent missing keys
    status_counts = {
        "insufficient_trait_evidence": 0,
        "visual_top_conflicts_with_key": 0,
        "visual_top_tied_for_key_top": 0,
        "visual_top_supported_by_key": 0,
        "visual_top_unresolved_by_key": 0,
        "key_prefers_different_taxon": 0
    }

    visual_key_top_agreement_count = 0
    missing_traits_freq = {}
    conflicting_rules_freq = {}

    for packet in evidence_packets:
        summary = packet["agreement_summary"]
        status = summary["status"]
        if status in status_counts:
            status_counts[status] += 1
        else:
            status_counts[status] = 1

        # Check visual top candidate and key top candidate agreement
        # Refined: Exclude insufficient_trait_evidence records and require non-null key_top_taxon_id
        v_top = summary.get("visual_top_taxon_id")
        k_top = summary.get("key_top_taxon_id")
        if status != "insufficient_trait_evidence" and k_top is not None and v_top == k_top:
            visual_key_top_agreement_count += 1

        # Track missing traits
        for mt in packet.get("missing_trait_summary", []):
            tid = mt["trait_id"]
            missing_traits_freq[tid] = missing_traits_freq.get(tid, 0) + 1

        # Track conflicting rules
        for item in packet.get("conflict_summary", []):
            for rule in item.get("conflicting_rules", []):
                conflicting_rules_freq[rule] = conflicting_rules_freq.get(rule, 0) + 1

    # Compute rates safely
    def get_rate(count: int) -> float:
        return float(count) / total_records if total_records > 0 else 0.0

    support_rate = get_rate(status_counts["visual_top_supported_by_key"])
    conflict_rate = get_rate(status_counts["visual_top_conflicts_with_key"])
    insufficient_trait_evidence_rate = get_rate(status_counts["insufficient_trait_evidence"])
    unresolved_rate = get_rate(status_counts["visual_top_unresolved_by_key"])
    key_prefers_different_taxon_rate = get_rate(status_counts["key_prefers_different_taxon"])
    tied_for_key_top_rate = get_rate(status_counts["visual_top_tied_for_key_top"])
    visual_key_top_agreement_rate = get_rate(visual_key_top_agreement_count)

    # Compute advanced evidence-adequacy statistics
    meaningful_evidence_records = total_records - status_counts["insufficient_trait_evidence"]
    meaningful_evidence_rate = float(meaningful_evidence_records) / total_records if total_records > 0 else 0.0

    out_of_scope_candidate_rate = float(out_of_scope_candidate_records) / total_records if total_records > 0 else 0.0

    # Sort missing traits frequency (count descending, alphabetical trait_id ascending)
    sorted_missing = sorted(missing_traits_freq.items(), key=lambda x: (-x[1], x[0]))
    most_common_missing_traits = [
        {"trait_id": tid, "count": count} for tid, count in sorted_missing
    ]

    # Sort conflicting rules frequency (count descending, alphabetical rule_id ascending)
    sorted_conflicts = sorted(conflicting_rules_freq.items(), key=lambda x: (-x[1], x[0]))
    most_common_conflicting_rules = [
        {"rule_id": rule_id, "count": count} for rule_id, count in sorted_conflicts
    ]

    summary_payload = {
        "total_records": total_records,
        "status_counts": status_counts,
        "support_rate": support_rate,
        "conflict_rate": conflict_rate,
        "insufficient_trait_evidence_rate": insufficient_trait_evidence_rate,
        "unresolved_rate": unresolved_rate,
        "key_prefers_different_taxon_rate": key_prefers_different_taxon_rate,
        "tied_for_key_top_rate": tied_for_key_top_rate,
        "meaningful_evidence_records": meaningful_evidence_records,
        "meaningful_evidence_rate": meaningful_evidence_rate,
        "out_of_scope_candidate_records": out_of_scope_candidate_records,
        "out_of_scope_candidate_rate": out_of_scope_candidate_rate,
        "visual_key_top_agreement_count": visual_key_top_agreement_count,
        "visual_key_top_agreement_rate": visual_key_top_agreement_rate,
        "most_common_missing_traits": most_common_missing_traits,
        "most_common_conflicting_rules": most_common_conflicting_rules
    }

    return {
        "summary": summary_payload,
        "evidence_packets": evidence_packets
    }
