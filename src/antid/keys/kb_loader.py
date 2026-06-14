"""Knowledge base loading and strict validation module.

This module handles loading and validating the 4 files of the KeyAgent-Ant taxonomic KB:
1. source_manifest.yaml
2. trait_schema.yaml
3. taxon_registry.yaml
4. key_rules.json
"""

import os
import json
import re
import yaml


def get_couplet_base_id(couplet_str: str) -> str:
    """Extracts the base couplet ID by stripping trailing letters (e.g., '1a' -> '1')."""
    return re.sub(r"[a-zA-Z]+$", "", couplet_str)


def extract_source_ids(manifest_data: dict) -> set:
    """Extracts all valid source_id values from source_manifest.yaml metadata."""
    valid_source_ids = set()
    
    # 1. Direct top-level string or list
    if "source_id" in manifest_data:
        sid = manifest_data["source_id"]
        if isinstance(sid, str):
            valid_source_ids.add(sid)
        elif isinstance(sid, list):
            valid_source_ids.update(sid)
            
    # 2. Top-level list source_ids
    if "source_ids" in manifest_data:
        sids = manifest_data["source_ids"]
        if isinstance(sids, list):
            valid_source_ids.update(sids)
            
    # 3. List of sources dictionary
    if "sources" in manifest_data:
        sources = manifest_data["sources"]
        if isinstance(sources, list):
            for s in sources:
                if isinstance(s, dict) and "source_id" in s:
                    valid_source_ids.add(s["source_id"])
                    
    return valid_source_ids


def load_kb(kb_dir: str) -> dict:
    """Loads and strictly validates all 4 KeyAgent-Ant KB files in kb_dir.

    Args:
        kb_dir: Absolute path to the directory containing the KB files.

    Returns:
        A dictionary containing the parsed and validated KB contents:
        {
            "manifest": dict,
            "trait_schema": dict,
            "taxon_registry": dict,
            "key_rules": dict,
            "valid_source_ids": set,
            "trait_ids": set,
            "taxon_ids": set,
            "couplets": dict,  # couplet_id -> list of rule dicts
        }

    Raises:
        FileNotFoundError: If any of the required files is missing.
        ValueError: If any validation rule is violated.
    """
    manifest_path = os.path.join(kb_dir, "source_manifest.yaml")
    trait_path = os.path.join(kb_dir, "trait_schema.yaml")
    taxon_path = os.path.join(kb_dir, "taxon_registry.yaml")
    rules_path = os.path.join(kb_dir, "key_rules.json")

    # Verify all files exist
    for path in [manifest_path, trait_path, taxon_path, rules_path]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Required KB file not found: {path}")

    # Load file contents
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = yaml.safe_load(f) or {}
    except Exception as e:
        raise ValueError(f"Failed to parse source_manifest.yaml: {e}")

    try:
        with open(trait_path, "r", encoding="utf-8") as f:
            trait_data = yaml.safe_load(f) or {}
    except Exception as e:
        raise ValueError(f"Failed to parse trait_schema.yaml: {e}")

    try:
        with open(taxon_path, "r", encoding="utf-8") as f:
            taxon_data = yaml.safe_load(f) or {}
    except Exception as e:
        raise ValueError(f"Failed to parse taxon_registry.yaml: {e}")

    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            rules_data = json.load(f) or {}
    except Exception as e:
        raise ValueError(f"Failed to parse key_rules.json: {e}")

    # ==========================================
    # 1. Source Manifest & Source ID Validation
    # ==========================================
    valid_source_ids = extract_source_ids(manifest_data)
    if not valid_source_ids:
        raise ValueError("source_manifest.yaml must define at least one valid source_id.")

    # ==========================================
    # 2. Trait Schema Validation
    # ==========================================
    if "traits" not in trait_data or not isinstance(trait_data["traits"], list):
        raise ValueError("trait_schema.yaml must contain a top-level 'traits' list.")

    trait_ids = set()
    trait_defs = {}
    for trait in trait_data["traits"]:
        if not isinstance(trait, dict):
            raise ValueError("Every trait entry in trait_schema.yaml must be a dictionary.")
        
        required_fields = ["trait_id", "name", "body_region", "allowed_values", "visible_in_views"]
        for field in required_fields:
            if field not in trait:
                raise ValueError(f"Trait entry missing required field '{field}': {trait}")
        
        t_id = trait["trait_id"]
        if t_id in trait_ids:
            raise ValueError(f"Duplicate trait_id in schema: '{t_id}'")
        trait_ids.add(t_id)
        trait_defs[t_id] = trait

    # ==========================================
    # 3. Taxon Registry Validation
    # ==========================================
    if "taxa" not in taxon_data or not isinstance(taxon_data["taxa"], list):
        raise ValueError("taxon_registry.yaml must contain a top-level 'taxa' list.")

    taxon_ids = set()
    for taxon in taxon_data["taxa"]:
        if not isinstance(taxon, dict):
            raise ValueError("Every taxon entry in taxon_registry.yaml must be a dictionary.")
        
        required_fields = ["taxon_id", "scientific_name", "rank"]
        for field in required_fields:
            if field not in taxon:
                raise ValueError(f"Taxon entry missing required field '{field}': {taxon}")
        
        tax_id = taxon["taxon_id"]
        if tax_id in taxon_ids:
            raise ValueError(f"Duplicate taxon_id in registry: '{tax_id}'")
        taxon_ids.add(tax_id)

    # ==========================================
    # 4. Key Rules Parsing and Target Validation
    # ==========================================
    if "rules" not in rules_data or not isinstance(rules_data["rules"], list):
        raise ValueError("key_rules.json must contain a top-level 'rules' list.")

    root_source_id = rules_data.get("source_id")
    rule_ids = set()
    couplet_rules = {}

    allowed_operators = {"equals", "not_equals", "in", "not_in"}

    for rule in rules_data["rules"]:
        if not isinstance(rule, dict):
            raise ValueError("Every rule entry in key_rules.json must be a dictionary.")
        
        required_fields = ["rule_id", "couplet", "conditions"]
        for field in required_fields:
            if field not in rule:
                raise ValueError(f"Rule entry missing required field '{field}': {rule}")

        r_id = rule["rule_id"]
        if r_id in rule_ids:
            raise ValueError(f"Duplicate rule_id in rules: '{r_id}'")
        rule_ids.add(r_id)

        # Multi-source ID Validation (Constraint 1)
        r_source_id = rule.get("source_id") or root_source_id
        if not r_source_id:
            raise ValueError(f"Rule '{r_id}' has no defined or inherited source_id.")
        if r_source_id not in valid_source_ids:
            raise ValueError(f"Rule '{r_id}' references unknown source_id '{r_source_id}'. Valid sources: {valid_source_ids}")

        # Conditions and Operator Validation (Constraint 4)
        conditions = rule["conditions"]
        if not isinstance(conditions, list):
            raise ValueError(f"Rule '{r_id}' conditions must be a list.")
        for cond in conditions:
            if not isinstance(cond, dict):
                raise ValueError(f"Conditions in rule '{r_id}' must be dictionaries.")
            for field in ["trait_id", "operator", "value"]:
                if field not in cond:
                    raise ValueError(f"Condition in rule '{r_id}' missing required field '{field}': {cond}")
            
            c_trait_id = cond["trait_id"]
            if c_trait_id not in trait_ids:
                raise ValueError(f"Condition in rule '{r_id}' references unknown trait_id '{c_trait_id}'")
            
            c_op = cond["operator"]
            if c_op not in allowed_operators:
                raise ValueError(f"Condition in rule '{r_id}' uses unallowed operator '{c_op}'. Allowed: {allowed_operators}")

        # Rule Mutual Exclusion Validation (Constraint 3)
        term_taxon = rule.get("terminal_taxon_id")
        next_coup = rule.get("next_couplet")

        # Must have exactly one of terminal_taxon_id or next_couplet
        has_term = term_taxon is not None and term_taxon != ""
        has_next = next_coup is not None and next_coup != ""

        if has_term and has_next:
            raise ValueError(f"Rule '{r_id}' violates mutual exclusion: defines both terminal_taxon_id and next_couplet.")
        if not has_term and not has_next:
            raise ValueError(f"Rule '{r_id}' violates mutual exclusion: defines neither terminal_taxon_id nor next_couplet.")

        if has_term and term_taxon not in taxon_ids:
            raise ValueError(f"Rule '{r_id}' references unknown terminal_taxon_id '{term_taxon}' in taxon registry.")

        # Group rules by couplet base ID
        base_id = get_couplet_base_id(rule["couplet"])
        if base_id not in couplet_rules:
            couplet_rules[base_id] = []
        couplet_rules[base_id].append(rule)

    # ==========================================
    # 5. Couplet Path & Topology Validation (Constraint 3)
    # ==========================================
    defined_couplets = set(couplet_rules.keys())
    if "1" not in defined_couplets:
        raise ValueError("Knowledge base rules must contain a root couplet '1' (e.g., '1a', '1b').")

    # Validate next_couplet references.
    # Note: Couplet "7" is explicitly whitelisted here as a temporary POC behavior because the
    # current POC ruleset extracts only couplets 1 through 6, and "7" acts as the out-of-scope 
    # boundary couplet.
    # TODO: Future KBs should declare out-of-scope/boundary couplets in their source_manifest.yaml
    # metadata instead of hard-coding specific couplet IDs in the loader.
    for r_id, rule in [(r["rule_id"], r) for rules in couplet_rules.values() for r in rules]:
        nc = rule.get("next_couplet")
        if nc is not None and nc != "":
            if nc not in defined_couplets and nc != "7":
                raise ValueError(f"Rule '{r_id}' has unknown next_couplet reference '{nc}'.")

    # Validate reachable couplets
    reachable = set()
    def traverse_reachable(c_id):
        if c_id in reachable:
            return
        reachable.add(c_id)
        for r in couplet_rules.get(c_id, []):
            nc = r.get("next_couplet")
            if nc and nc in defined_couplets:
                traverse_reachable(nc)

    traverse_reachable("1")

    unreachable = defined_couplets - reachable
    if unreachable:
        raise ValueError(f"Unreachable couplets detected (not reachable from root couplet '1'): {sorted(list(unreachable))}")

    # Validate cyclic couplet paths (Cycle detection via DFS)
    visited = set()
    rec_stack = set()

    def detect_cycle(c_id) -> bool:
        visited.add(c_id)
        rec_stack.add(c_id)
        for r in couplet_rules.get(c_id, []):
            nc = r.get("next_couplet")
            if nc and nc in defined_couplets:
                if nc not in visited:
                    if detect_cycle(nc):
                        return True
                elif nc in rec_stack:
                    return True
        rec_stack.remove(c_id)
        return False

    if detect_cycle("1"):
        raise ValueError("Cyclic couplet path detected in the knowledge base couplet graph.")

    return {
        "manifest": manifest_data,
        "trait_schema": trait_data,
        "taxon_registry": taxon_data,
        "key_rules": rules_data,
        "valid_source_ids": valid_source_ids,
        "trait_ids": trait_ids,
        "taxon_ids": taxon_ids,
        "trait_defs": trait_defs,
        "couplets": couplet_rules,
    }
