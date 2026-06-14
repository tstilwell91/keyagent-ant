"""Reasoning adapter that integrates vision model outputs with KB reasoning.

Accepts visual prediction candidates and observed traits, executes deterministic
key reasoning, and produces a structured reasoning evidence packet for downstream
explanation generation or decision-making.
"""

from typing import Union, Dict, Any, Optional, List
from .key_reasoner import KeyReasoner
from .evidence_schema import VisualCandidate, ModelEvidenceInput, ReasoningEvidencePacket


def build_reasoning_evidence_packet(
    kb_dir_or_dict: Union[str, dict],
    model_output: Dict[str, Any],
    candidate_taxa_from_visual: bool = True
) -> Dict[str, Any]:
    """Integrates model visual predictions with deterministic key reasoning.

    Args:
        kb_dir_or_dict: KB directory path or pre-loaded KB dictionary.
        model_output: Dictionary containing visual model output and observed traits.
        candidate_taxa_from_visual: If True, evaluates only candidates from model_output.

    Returns:
        A JSON-serializable dictionary matching ReasoningEvidencePacket schema.
    """
    # 1. Parse and Validate model_output
    if not isinstance(model_output, dict):
        raise TypeError("model_output must be a dictionary.")

    # Convert visual candidates to VisualCandidate dataclasses for strict validation
    if "visual_candidates" not in model_output:
        raise ValueError("model_output missing required field 'visual_candidates'.")
    if "observed_traits" not in model_output:
        raise ValueError("model_output missing required field 'observed_traits'.")
    if "image_id" not in model_output:
        raise ValueError("model_output missing required field 'image_id'.")
    if "metadata" not in model_output:
        raise ValueError("model_output missing required field 'metadata'.")

    visual_candidates = []
    for vc in model_output["visual_candidates"]:
        if not isinstance(vc, dict):
            raise TypeError("Every visual candidate entry must be a dictionary.")
        visual_candidates.append(
            VisualCandidate(
                taxon_id=vc.get("taxon_id"),
                scientific_name=vc.get("scientific_name"),
                score=float(vc["score"]),
                rank=int(vc["rank"])
            )
        )

    model_input = ModelEvidenceInput(
        image_id=model_output["image_id"],
        view_type=model_output.get("view_type"),
        visual_candidates=visual_candidates,
        observed_traits=model_output["observed_traits"],
        metadata=model_output["metadata"]
    )
    # Strictly validate fields via schema dataclasses
    model_input.validate()

    # 2. Instantiate KeyReasoner and resolve candidate taxon IDs
    reasoner = KeyReasoner(kb_dir_or_dict)

    raw_candidates = []
    for vc in visual_candidates:
        val = vc.taxon_id or vc.scientific_name
        if val:
            raw_candidates.append(val)

    # Resolves and validates candidates against the KB registry case-insensitively
    resolved_candidates = reasoner.resolve_candidate_taxa(raw_candidates)

    # Find the visual top candidate (rank == 1)
    v_candidates_sorted = sorted(visual_candidates, key=lambda x: x.rank)
    top_vc = v_candidates_sorted[0]
    top_vc_input = top_vc.taxon_id or top_vc.scientific_name
    top_visual_id = reasoner.resolve_candidate_taxa([top_vc_input])[0]

    # 3. Perform deterministic reasoning
    eval_candidates = resolved_candidates if candidate_taxa_from_visual else None
    key_reasoning = reasoner.reason(
        observed_traits=model_input.observed_traits,
        candidate_taxa=eval_candidates,
        view_type=model_input.view_type
    )

    # 4. Apply deterministic tie-breaking logic to ranked_taxa
    ranked_taxa = key_reasoning["ranked_taxa"]
    # Sort alphabetically by taxon_id first (tie breaker)
    ranked_taxa.sort(key=lambda x: x["taxon_id"])
    # Sort by scores descending (normalized_score, raw_score)
    ranked_taxa.sort(key=lambda x: (x["normalized_score"], x["raw_score"]), reverse=True)

    # Identify top score and ties
    top_kb_taxa = []
    key_top_id = None
    if ranked_taxa:
        best_norm = ranked_taxa[0]["normalized_score"]
        best_raw = ranked_taxa[0]["raw_score"]
        top_kb_taxa = [
            t["taxon_id"] for t in ranked_taxa 
            if t["normalized_score"] == best_norm and t["raw_score"] == best_raw
        ]
        # Alphabetically first of the top score candidates
        key_top_id = top_kb_taxa[0]

    # Fetch visual top candidate key scores
    visual_top_raw = key_reasoning["raw_scores"].get(top_visual_id, 0)
    visual_top_norm = key_reasoning["normalized_scores"].get(top_visual_id, 0.0)
    visual_top_conflicts = len(key_reasoning["conflicting_rules"].get(top_visual_id, []))
    visual_top_unresolved = len(key_reasoning["unresolved_rules"].get(top_visual_id, []))

    # Evaluate if we have sufficient trait evidence
    # It is insufficient if observed_traits is empty or if no rules have been resolved to support or conflict
    has_any_resolution = any(
        len(key_reasoning["supporting_rules"][t]) > 0 or len(key_reasoning["conflicting_rules"][t]) > 0
        for t in key_reasoning["supporting_rules"]
    )

    # 5. Formulate structured agreement summary
    if not model_input.observed_traits or not has_any_resolution:
        status = "insufficient_trait_evidence"
        key_top_id = None
        reason = "No observed traits or no definitive rules resolved (supported/conflicted) in the key."
    elif visual_top_conflicts > 0 or visual_top_raw < 0:
        status = "visual_top_conflicts_with_key"
        reason = f"Top visual candidate '{top_visual_id}' has conflicting rules in the taxonomic key."
    elif top_visual_id in top_kb_taxa:
        if len(top_kb_taxa) > 1:
            status = "visual_top_tied_for_key_top"
            reason = f"Top visual candidate '{top_visual_id}' is tied with other candidates {top_kb_taxa} for the top key score."
        else:
            if visual_top_raw > 0:
                status = "visual_top_supported_by_key"
                reason = f"Top visual candidate '{top_visual_id}' is uniquely supported by the key."
            else:
                status = "visual_top_unresolved_by_key"
                reason = f"Top visual candidate '{top_visual_id}' is unresolved but is the unique top candidate."
    else:
        status = "key_prefers_different_taxon"
        reason = f"The key prefers taxon '{key_top_id}' over visual top candidate '{top_visual_id}'."

    agreement_summary = {
        "status": status,
        "visual_top_taxon_id": top_visual_id,
        "key_top_taxon_id": key_top_id,
        "visual_top_raw_key_score": visual_top_raw,
        "visual_top_normalized_key_score": visual_top_norm,
        "reason": reason
    }

    # 6. Formulate conflict summary
    conflict_summary = []
    for vc in model_input.visual_candidates:
        vc_inp = vc.taxon_id or vc.scientific_name
        vc_resolved_id = reasoner.resolve_candidate_taxa([vc_inp])[0]
        c_raw = key_reasoning["raw_scores"].get(vc_resolved_id, 0)
        if c_raw < 0:
            conflict_summary.append({
                "taxon_id": vc_resolved_id,
                "score": vc.score,
                "rank": vc.rank,
                "key_raw_score": c_raw,
                "key_normalized_score": key_reasoning["normalized_scores"].get(vc_resolved_id, 0.0),
                "conflicting_rules": key_reasoning["conflicting_rules"].get(vc_resolved_id, [])
            })

    # 7. Formulate missing trait summary
    missing_trait_summary = []
    for mt in key_reasoning["missing_traits"]["all_missing"]:
        missing_trait_summary.append({
            "trait_id": mt["trait_id"],
            "name": mt["name"],
            "body_region": mt["body_region"],
            "visible_in_views": mt["visible_in_views"]
        })

    # 8. Normalize recommended_next_action
    raw_rec = key_reasoning.get("recommended_next_action", "")
    is_none = (
        "fully supported" in raw_rec.lower() or 
        "no remaining unresolved traits" in raw_rec.lower() or 
        not missing_trait_summary
    )
    action_type = "none" if is_none else "observe_trait"

    # Identify the precise missing trait recommended for the top candidate
    recommended_trait_id = None
    target_taxon_id = key_top_id or top_visual_id
    if target_taxon_id:
        unresolved = key_reasoning["unresolved_rules"].get(target_taxon_id, [])
        if unresolved:
            path = reasoner.find_path_to_taxon(target_taxon_id) or []
            for rule in path:
                if rule["rule_id"] in unresolved:
                    for cond in rule["conditions"]:
                        ctid = cond["trait_id"]
                        if ctid not in model_input.observed_traits or model_input.observed_traits[ctid] is None:
                            recommended_trait_id = ctid
                            break
                    if recommended_trait_id:
                        break

    next_action_obj = {
        "action_type": action_type,
        "trait_id": recommended_trait_id,
        "reason": raw_rec,
        "source": "kb_reasoner",
        "raw_recommendation": raw_rec
    }

    # 9. Build ReasoningEvidencePacket and return as dict
    packet = ReasoningEvidencePacket(
        image_id=model_input.image_id,
        view_type=model_input.view_type,
        visual_candidates=[
            {"taxon_id": vc.taxon_id, "scientific_name": vc.scientific_name, "score": vc.score, "rank": vc.rank}
            for vc in visual_candidates
        ],
        observed_traits=model_input.observed_traits,
        key_reasoning=key_reasoning,
        agreement_summary=agreement_summary,
        conflict_summary=conflict_summary,
        missing_trait_summary=missing_trait_summary,
        recommended_next_action=next_action_obj,
        limitations=key_reasoning.get("limitations", {}),
        final_identification=None,
        identification_decision_policy="not_applied"
    )

    return packet.to_dict()
