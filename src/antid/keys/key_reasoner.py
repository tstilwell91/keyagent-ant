"""Taxonomic knowledge base reasoning and scoring engine.

This module implements deterministic key reasoning, path-based hierarchical scoring,
candidate resolution, missing/unknown trait detection, and structured reason outputs.
"""

from typing import Union, List, Dict, Any, Optional
from .kb_loader import load_kb


class KeyReasoner:
    """Deterministic reasoning engine for KeyAgent-Ant taxonomic keys."""

    def __init__(self, kb_dir_or_dict: Union[str, dict]):
        """Initializes the reasoner with a KB directory path or pre-loaded KB dict."""
        if isinstance(kb_dir_or_dict, str):
            self.kb = load_kb(kb_dir_or_dict)
        elif isinstance(kb_dir_or_dict, dict):
            self.kb = kb_dir_or_dict
        else:
            raise TypeError("kb_dir_or_dict must be a directory path or pre-loaded KB dict.")

        self.manifest = self.kb["manifest"]
        self.trait_schema = self.kb["trait_schema"]
        self.taxon_registry = self.kb["taxon_registry"]
        self.key_rules = self.kb["key_rules"]
        self.valid_source_ids = self.kb["valid_source_ids"]
        self.trait_ids = self.kb["trait_ids"]
        self.taxon_ids = self.kb["taxon_ids"]
        self.trait_defs = self.kb["trait_defs"]
        self.couplets = self.kb["couplets"]

    def resolve_candidate_taxa(self, candidate_taxa_inputs: Optional[List[str]]) -> List[str]:
        """Resolves input taxon IDs or names to valid taxon_id values.

        Enforces Constraint 6:
        - Accepts taxon_id values first (case-insensitively).
        - Optionally supports scientific names as aliases only if unambiguous.
        - Raises ValueError if ambiguous or unknown.
        """
        if not candidate_taxa_inputs:
            # If none provided, default to all registered taxa
            return sorted(list(self.taxon_ids))

        resolved = []
        for inp in candidate_taxa_inputs:
            inp_lower = inp.strip().lower()

            # 1. Match taxon_id case-insensitively
            matched_id = None
            for tx in self.taxon_registry.get("taxa", []):
                if tx["taxon_id"].lower() == inp_lower:
                    matched_id = tx["taxon_id"]
                    break

            if matched_id:
                resolved.append(matched_id)
                continue

            # 2. Match scientific_name case-insensitively
            scientific_matches = []
            for tx in self.taxon_registry.get("taxa", []):
                if tx["scientific_name"].lower() == inp_lower:
                    scientific_matches.append(tx["taxon_id"])

            if len(scientific_matches) == 1:
                resolved.append(scientific_matches[0])
            elif len(scientific_matches) > 1:
                raise ValueError(
                    f"Candidate taxon alias '{inp}' is ambiguous and matches multiple registered taxa: {scientific_matches}"
                )
            else:
                raise ValueError(
                    f"Candidate taxon '{inp}' does not match any registered taxon_id or scientific_name in the registry."
                )

        return resolved

    def find_path_to_taxon(self, target_taxon: str) -> Optional[List[dict]]:
        """Finds the unique sequence of rules leading to target_taxon from root couplet '1'."""
        def _find(c_id: str, path: List[dict]) -> Optional[List[dict]]:
            for rule in self.couplets.get(c_id, []):
                new_path = path + [rule]
                term = rule.get("terminal_taxon_id")
                if term == target_taxon:
                    return new_path
                nc = rule.get("next_couplet")
                if nc and nc in self.couplets:
                    res = _find(nc, new_path)
                    if res is not None:
                        return res
            return None

        return _find("1", [])

    def evaluate_rule(self, rule: dict, observed_traits: Dict[str, Any]) -> int:
        """Evaluates a single rule against observed traits.

        Returns:
            +1: Supported (all conditions match)
            -1: Conflicted (at least one condition mismatch)
             0: Unresolved (no mismatch, but at least one condition is unobserved)
        """
        has_unobserved = False

        for cond in rule["conditions"]:
            t_id = cond["trait_id"]
            op = cond["operator"]
            rule_val = cond["value"]

            if t_id not in observed_traits or observed_traits[t_id] is None:
                has_unobserved = True
                continue

            obs_val = observed_traits[t_id]

            # Condition evaluations (Constraint 4)
            if op == "equals":
                match = (obs_val == rule_val)
            elif op == "not_equals":
                match = (obs_val != rule_val)
            elif op == "in":
                # Ensure rule_val is iterable/list
                vals = rule_val if isinstance(rule_val, list) else [rule_val]
                match = (obs_val in vals)
            elif op == "not_in":
                vals = rule_val if isinstance(rule_val, list) else [rule_val]
                match = (obs_val not in vals)
            else:
                # Should be caught by validation, but safeguard
                raise ValueError(f"Unallowed operator: '{op}'")

            if not match:
                return -1

        if has_unobserved:
            return 0
        return 1

    def reason(self, observed_traits: Dict[str, Any], candidate_taxa: Optional[List[str]] = None, view_type: Optional[str] = None) -> Dict[str, Any]:
        """Runs the deterministic reasoning engine over observed traits.

        Args:
            observed_traits: Dictionary mapping trait_id to observed value.
            candidate_taxa: Optional list of taxon IDs or scientific names to restrict evaluation.
            view_type: Optional view identifier (e.g. 'head', 'profile', 'dorsal') to prioritize missing traits.

        Returns:
            A detailed reasoning dictionary containing ranked taxa, scores, rules, and dynamic actions.
        """
        # Resolve candidate taxa
        resolved_candidates = self.resolve_candidate_taxa(candidate_taxa)

        # Detect unknown traits (Constraint 7)
        unknown_traits = []
        for t_id in observed_traits.keys():
            if t_id not in self.trait_ids:
                unknown_traits.append(t_id)

        # Initialize results
        raw_scores = {}
        normalized_scores = {}
        supporting_rules = {}
        conflicting_rules = {}
        unresolved_rules = {}
        all_missing_trait_ids = set()

        # Compute scoring and categorize rules for each candidate taxon
        for taxon_id in resolved_candidates:
            path = self.find_path_to_taxon(taxon_id)
            if not path:
                # Registered taxon but has no rule path in current key
                raw_scores[taxon_id] = 0
                normalized_scores[taxon_id] = 0.0
                supporting_rules[taxon_id] = []
                conflicting_rules[taxon_id] = []
                unresolved_rules[taxon_id] = []
                continue

            taxon_raw = 0
            supporting = []
            conflicting = []
            unresolved = []

            for rule in path:
                r_id = rule["rule_id"]
                score = self.evaluate_rule(rule, observed_traits)
                
                if score == 1:
                    taxon_raw += 1
                    supporting.append(r_id)
                elif score == -1:
                    taxon_raw -= 1
                    conflicting.append(r_id)
                else:  # score == 0
                    unresolved.append(r_id)
                    # Collect missing trait IDs from this unresolved rule
                    for cond in rule["conditions"]:
                        c_tid = cond["trait_id"]
                        if c_tid not in observed_traits or observed_traits[c_tid] is None:
                            all_missing_trait_ids.add(c_tid)

            raw_scores[taxon_id] = taxon_raw
            normalized_scores[taxon_id] = float(taxon_raw) / len(path)
            supporting_rules[taxon_id] = supporting
            conflicting_rules[taxon_id] = conflicting
            unresolved_rules[taxon_id] = unresolved

        # Format ranked taxa
        ranked_taxa = []
        for taxon_id in resolved_candidates:
            # Fetch scientific name for readability
            sc_name = next(t["scientific_name"] for t in self.taxon_registry["taxa"] if t["taxon_id"] == taxon_id)
            ranked_taxa.append({
                "taxon_id": taxon_id,
                "scientific_name": sc_name,
                "raw_score": raw_scores[taxon_id],
                "normalized_score": normalized_scores[taxon_id],
            })

        # Sort ranked taxa by normalized_score descending, then raw_score descending
        ranked_taxa.sort(key=lambda x: (x["normalized_score"], x["raw_score"]), reverse=True)

        # Structure missing traits (Constraint 7)
        missing_traits_details = []
        for t_id in sorted(list(all_missing_trait_ids)):
            t_def = self.trait_defs[t_id]
            missing_traits_details.append({
                "trait_id": t_id,
                "name": t_def["name"],
                "body_region": t_def["body_region"],
                "visible_in_views": t_def["visible_in_views"],
            })

        # Categorize missing traits by view_type if provided
        categorized_missing_traits = {
            "all_missing": missing_traits_details
        }
        if view_type:
            view_lower = view_type.strip().lower()
            relevant = []
            other = []
            for t in missing_traits_details:
                if any(v.lower() == view_lower for v in t["visible_in_views"]):
                    relevant.append(t)
                else:
                    other.append(t)
            categorized_missing_traits["relevant_to_current_view"] = relevant
            categorized_missing_traits["other_views"] = other

        # Generate recommended next action (Constraint 7)
        # Note: recommended_next_action is currently returned as a temporary string field.
        # TODO: Future versions should return a structured object with:
        # - action_type (e.g., 'observe_trait', 'complete', 'conflict')
        # - trait_id (e.g., 'antenna_segment_count')
        # - reason (explanation text)
        # - visible_in_current_view (boolean matching view_type)
        recommended_next_action = ""
        if ranked_taxa:
            top_taxon = ranked_taxa[0]
            top_id = top_taxon["taxon_id"]
            top_sc_name = top_taxon["scientific_name"]
            top_unresolved_rule_ids = unresolved_rules.get(top_id, [])

            if top_unresolved_rule_ids:
                # Find the first unresolved rule on its path
                path_rules = self.find_path_to_taxon(top_id) or []
                first_unresolved_rule = None
                for r in path_rules:
                    if r["rule_id"] in top_unresolved_rule_ids:
                        first_unresolved_rule = r
                        break
                
                if first_unresolved_rule:
                    # Find missing traits for this specific rule
                    rule_missing = []
                    for cond in first_unresolved_rule["conditions"]:
                        ctid = cond["trait_id"]
                        if ctid not in observed_traits or observed_traits[ctid] is None:
                            t_name = self.trait_defs[ctid]["name"]
                            t_views = self.trait_defs[ctid]["visible_in_views"]
                            rule_missing.append(f"'{t_name}' (visible in {t_views})")
                    
                    if rule_missing:
                        recommended_next_action = (
                            f"To verify candidate '{top_sc_name}', please observe the following "
                            f"missing trait(s): {', '.join(rule_missing)}."
                        )
            else:
                # All rules on path resolved
                if top_taxon["normalized_score"] == 1.0:
                    recommended_next_action = f"Taxon '{top_sc_name}' is fully supported by the observations."
                elif top_taxon["normalized_score"] < 0:
                    recommended_next_action = "All candidates are conflicted. Please verify the observed traits for errors."
                else:
                    recommended_next_action = f"Candidate '{top_sc_name}' is partially supported with no remaining unresolved traits."
        else:
            recommended_next_action = "No candidate taxa evaluated."

        # Extract limitations from source manifest (Constraint 7)
        limitations = {
            "geographic_scope": self.manifest.get("geographic_scope", "Unknown"),
            "caste_scope": self.manifest.get("caste_scope", "Unknown"),
            "taxonomic_scope": self.manifest.get("taxonomic_scope", "Unknown"),
            "notes": self.manifest.get("notes", []),
            "extraction_scope": self.manifest.get("extraction_scope", "Unknown"),
        }

        return {
            "ranked_taxa": ranked_taxa,
            "raw_scores": raw_scores,
            "normalized_scores": normalized_scores,
            "supporting_rules": supporting_rules,
            "conflicting_rules": conflicting_rules,
            "unresolved_rules": unresolved_rules,
            "missing_traits": categorized_missing_traits,
            "unknown_traits": unknown_traits,
            "recommended_next_action": recommended_next_action,
            "limitations": limitations,
        }


def reason_over_traits(
    kb_dir_or_dict: Union[str, dict],
    observed_traits: Dict[str, Any],
    candidate_taxa: Optional[List[str]] = None,
    view_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Wraps KeyReasoner reasoning capability as a top-level functional API."""
    reasoner = KeyReasoner(kb_dir_or_dict)
    return reasoner.reason(observed_traits, candidate_taxa, view_type)
