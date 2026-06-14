"""Trait visibility and evidence readiness audit module.

This module provides offline, deterministic auditing of the taxonomic KB,
trait schemas, selected specimens, and their image paths to verify alignment
before launching manual or automated annotation reviews.
"""

import os
import csv
import json
import yaml
from pathlib import Path
from .kb_loader import load_kb

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def check_image_readiness(path, image_root):
    """Verifies image path, file existence, and attempts to read dimensions.

    Args:
        path: Path to the image relative to image_root.
        image_root: The root directory for resolving image paths.

    Returns:
        A tuple of (exists: bool, width: int or None, height: bool or None, detail_status: str)
    """
    if not path:
        return False, None, None, "path_missing"
    full_path = os.path.join(image_root, path)
    if not os.path.exists(full_path):
        return False, None, None, "file_missing"

    if HAS_PIL:
        try:
            with Image.open(full_path) as img:
                width, height = img.size
                return True, width, height, "ok"
        except Exception as e:
            return True, None, None, f"unreadable: {e}"
    else:
        return True, None, None, "no_pil"


def get_reachable_terminals(rule, couplet_rules):
    """Recursively traverses downstream key rules to find all reachable terminal taxa.

    Args:
        rule: The current rule dictionary.
        couplet_rules: Map of couplet_id -> list of rule dictionaries.

    Returns:
        Set of reachable terminal taxon IDs.
    """
    terminals = set()
    if rule.get("terminal_taxon_id"):
        terminals.add(rule["terminal_taxon_id"])
    elif rule.get("next_couplet"):
        nc = rule["next_couplet"]
        if nc in couplet_rules:
            for r in couplet_rules[nc]:
                terminals.update(get_reachable_terminals(r, couplet_rules))
    return terminals


def find_rules_to_taxon(target_taxon, couplet_rules, current_couplet="1", path=None):
    """Finds all rules along the path from root couplet '1' to a target terminal taxon.

    Args:
        target_taxon: The taxon_id to search for.
        couplet_rules: Map of couplet_id -> list of rule dictionaries.
        current_couplet: The current couplet to search from.
        path: Accumulator list of rules.

    Returns:
        A list of paths, where each path is a list of rule dictionaries.
    """
    if path is None:
        path = []

    results = []
    for rule in couplet_rules.get(current_couplet, []):
        new_path = path + [rule]
        if rule.get("terminal_taxon_id") == target_taxon:
            results.append(new_path)
        elif rule.get("next_couplet"):
            nc = rule["next_couplet"]
            results.extend(find_rules_to_taxon(target_taxon, couplet_rules, nc, new_path))
    return results


def run_trait_visibility_audit(
    kb_dir,
    selection_csv,
    annotation_template_jsonl,
    image_root=".",
    output_dir="data/traits/trait_curated_v0_audit"
):
    """Runs a complete deterministic trait visibility and evidence readiness audit.

    Loads the KB, selection CSV, and annotation template, and produces:
    1. specimen_image_readiness.csv
    2. trait_schema_readiness.csv
    3. specimen_trait_visibility_matrix.csv
    4. kb_subset_coverage.json
    5. summary.json

    Args:
        kb_dir: Path to the KB directory containing YAML/JSON files.
        selection_csv: Path to the selected specimens CSV.
        annotation_template_jsonl: Path to the JSONL blank annotation template.
        image_root: Root directory for finding specimen images.
        output_dir: Directory where audited output files will be written.

    Returns:
        A dictionary containing the consolidated summary metrics.
    """
    # Create output parent directories
    os.makedirs(output_dir, exist_ok=True)

    # 1. Load KB via existing load_kb
    kb = load_kb(kb_dir)
    taxon_ids = kb["taxon_ids"]
    trait_ids = kb["trait_ids"]
    trait_defs = kb["trait_defs"]
    couplet_rules = kb["couplets"]

    # 2. Load Selection CSV
    if not os.path.exists(selection_csv):
        raise FileNotFoundError(f"Selection CSV file not found: {selection_csv}")

    specimens = []
    with open(selection_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            specimens.append(row)

    # 3. Load Annotation Template JSONL
    if not os.path.exists(annotation_template_jsonl):
        raise FileNotFoundError(f"Annotation template JSONL not found: {annotation_template_jsonl}")

    template_map = {}
    with open(annotation_template_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    record = json.loads(line)
                    if "specimen_id" in record:
                        template_map[record["specimen_id"]] = record
                except Exception:
                    pass

    # ==========================================
    # Task C: Specimen Image Readiness Audit
    # ==========================================
    specimen_readiness_rows = []
    specimens_ready_count = 0
    specimens_missing_files_count = 0
    split_counts = {"test": 0, "val": 0, "train": 0}

    for spec in specimens:
        spec_id = spec.get("specimen_id", "")
        cat_num = spec.get("catalog_number", "")
        kb_tax_id = spec.get("kb_taxon_id", "")
        scientific_name = spec.get("kb_scientific_name", "")
        dataset_genus = spec.get("dataset_genus", "")
        dataset_species = spec.get("dataset_species", "")
        source_split = spec.get("source_split", "")

        if source_split in split_counts:
            split_counts[source_split] += 1
        else:
            split_counts[source_split] = 1

        dorsal_path = spec.get("dorsal_image_path", "")
        head_path = spec.get("head_image_path", "")
        profile_path = spec.get("profile_image_path", "")
        duplicate_views = spec.get("duplicate_view_counts", "")

        # Run file checks
        d_exists, d_w, d_h, d_detail = check_image_readiness(dorsal_path, image_root)
        h_exists, h_w, h_h, h_detail = check_image_readiness(head_path, image_root)
        p_exists, p_w, p_h, p_detail = check_image_readiness(profile_path, image_root)

        all_views_present = bool(dorsal_path and head_path and profile_path)
        all_view_files_exist = bool(d_exists and h_exists and p_exists)

        # Determine readiness status
        readiness_status = "ready"
        notes_list = []

        if not spec_id or not cat_num:
            readiness_status = "invalid_template_record"
            notes_list.append("Missing specimen_id or catalog_number.")
        elif spec_id not in template_map:
            readiness_status = "invalid_template_record"
            notes_list.append("Specimen not found in annotation template JSONL.")
        elif kb_tax_id not in taxon_ids:
            readiness_status = "invalid_kb_taxon"
            notes_list.append(f"Taxon '{kb_tax_id}' not registered in taxon_registry.yaml.")
        elif not all_views_present:
            readiness_status = "missing_image_path"
            notes_list.append("One or more image paths are missing in selection CSV.")
        elif not all_view_files_exist:
            readiness_status = "missing_image_file"
            notes_list.append("One or more image files do not exist relative to image_root.")
            specimens_missing_files_count += 1
        elif "unreadable" in d_detail or "unreadable" in h_detail or "unreadable" in p_detail:
            readiness_status = "warning"
            notes_list.append(f"One or more images exist but could not be parsed by Pillow (D: {d_detail}, H: {h_detail}, P: {p_detail}).")
        else:
            specimens_ready_count += 1

        notes = " ".join(notes_list)

        spec_readiness = {
            "specimen_id": spec_id,
            "catalog_number": cat_num,
            "kb_taxon_id": kb_tax_id,
            "kb_scientific_name": scientific_name,
            "dataset_genus": dataset_genus,
            "dataset_species": dataset_species,
            "source_split": source_split,
            "dorsal_image_path": dorsal_path,
            "dorsal_exists": str(d_exists).lower(),
            "dorsal_width": d_w if d_w is not None else "",
            "dorsal_height": d_h if d_h is not None else "",
            "head_image_path": head_path,
            "head_exists": str(h_exists).lower(),
            "head_width": h_w if h_w is not None else "",
            "head_height": h_h if h_h is not None else "",
            "profile_image_path": profile_path,
            "profile_exists": str(p_exists).lower(),
            "profile_width": p_w if p_w is not None else "",
            "profile_height": p_h if p_h is not None else "",
            "all_views_present": str(all_views_present).lower(),
            "all_view_files_exist": str(all_view_files_exist).lower(),
            "duplicate_view_counts": duplicate_views,
            "readiness_status": readiness_status,
            "notes": notes
        }
        specimen_readiness_rows.append(spec_readiness)

    # Save specimen_image_readiness.csv
    specimen_csv_path = os.path.join(output_dir, "specimen_image_readiness.csv")
    spec_fieldnames = [
        "specimen_id", "catalog_number", "kb_taxon_id", "kb_scientific_name",
        "dataset_genus", "dataset_species", "source_split",
        "dorsal_image_path", "dorsal_exists", "dorsal_width", "dorsal_height",
        "head_image_path", "head_exists", "head_width", "head_height",
        "profile_image_path", "profile_exists", "profile_width", "profile_height",
        "all_views_present", "all_view_files_exist", "duplicate_view_counts",
        "readiness_status", "notes"
    ]
    with open(specimen_csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=spec_fieldnames)
        writer.writeheader()
        writer.writerows(specimen_readiness_rows)

    # ==========================================
    # Task D: Trait Schema Readiness Audit
    # ==========================================
    trait_schema_rows = []
    traits_used_in_rules_count = 0
    traits_not_used_in_rules_count = 0
    traits_with_view_metadata_count = 0
    traits_missing_view_metadata_count = 0

    # Build trait to rules mapping
    trait_to_rules = {tid: [] for tid in trait_ids}
    for couplet_id, rules in couplet_rules.items():
        for rule in rules:
            for cond in rule.get("conditions", []):
                cond_tid = cond.get("trait_id")
                if cond_tid in trait_to_rules:
                    trait_to_rules[cond_tid].append(rule["rule_id"])

    # Build schema readiness rows
    for trait in kb["trait_schema"].get("traits", []):
        trait_id = trait.get("trait_id", "")
        trait_name = trait.get("name", "")
        allowed_vals = trait.get("allowed_values", [])
        visible_views = trait.get("visible_in_views", [])
        body_region = trait.get("body_region", "")

        # Check references
        used_rules = sorted(list(set(trait_to_rules.get(trait_id, []))))
        used_in_key = len(used_rules) > 0

        if used_in_key:
            traits_used_in_rules_count += 1
        else:
            traits_not_used_in_rules_count += 1

        has_allowed_values = len(allowed_vals) > 0
        has_view_metadata = len(visible_views) > 0

        if has_view_metadata:
            traits_with_view_metadata_count += 1
        else:
            traits_missing_view_metadata_count += 1

        # Calculate affected taxa
        affected = set()
        for couplet_id, rules in couplet_rules.items():
            for rule in rules:
                if rule["rule_id"] in used_rules:
                    affected.update(get_reachable_terminals(rule, couplet_rules))

        # Status
        schema_readiness_status = "ready_for_visibility_mapping"
        notes_list = []

        if not trait_id or not trait_name:
            schema_readiness_status = "requires_schema_review"
            notes_list.append("Missing trait_id or name.")
        elif not has_allowed_values:
            schema_readiness_status = "missing_allowed_values"
            notes_list.append("No allowed values defined in trait schema.")
        elif not has_view_metadata:
            schema_readiness_status = "missing_view_metadata"
            notes_list.append("No visible_in_views defined in trait schema.")
        elif not used_in_key:
            schema_readiness_status = "not_used_in_current_key"
            notes_list.append("Trait is defined in schema but never referenced in key rules.")

        notes = " ".join(notes_list)

        trait_row = {
            "trait_id": trait_id,
            "trait_name": trait_name,
            "allowed_values": "; ".join(allowed_vals),
            "visible_in_views": "; ".join(visible_views),
            "body_region": body_region,
            "used_in_key_rules": str(used_in_key).lower(),
            "key_rule_ids": ", ".join(used_rules),
            "affected_taxa": ", ".join(sorted(list(affected))),
            "has_allowed_values": str(has_allowed_values).lower(),
            "has_view_metadata": str(has_view_metadata).lower(),
            "schema_readiness_status": schema_readiness_status,
            "notes": notes
        }
        trait_schema_rows.append(trait_row)

    # Save trait_schema_readiness.csv
    trait_csv_path = os.path.join(output_dir, "trait_schema_readiness.csv")
    trait_fieldnames = [
        "trait_id", "trait_name", "allowed_values", "visible_in_views",
        "body_region", "used_in_key_rules", "key_rule_ids", "affected_taxa",
        "has_allowed_values", "has_view_metadata", "schema_readiness_status", "notes"
    ]
    with open(trait_csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=trait_fieldnames)
        writer.writeheader()
        writer.writerows(trait_schema_rows)

    # ==========================================
    # Task E: Specimen × Trait Visibility Matrix
    # ==========================================
    matrix_rows = []
    visibility_status_counts = {}
    review_recommendation_counts = {}

    for spec_readiness in specimen_readiness_rows:
        # Construct specimen's available views
        spec_id = spec_readiness["specimen_id"]
        cat_num = spec_readiness["catalog_number"]
        kb_tax_id = spec_readiness["kb_taxon_id"]
        dataset_genus = spec_readiness["dataset_genus"]
        dataset_species = spec_readiness["dataset_species"]

        available_views = []
        if spec_readiness["dorsal_exists"] == "true":
            available_views.append("dorsal")
        if spec_readiness["head_exists"] == "true":
            available_views.append("head")
        if spec_readiness["profile_exists"] == "true":
            available_views.append("profile")

        available_views_set = set(available_views)

        for trait_row in trait_schema_rows:
            trait_id = trait_row["trait_id"]
            expected_views = [v.strip() for f in trait_row["visible_in_views"].split(";") if f.strip() for v in [f.strip()]]
            used_in_rules = trait_row["used_in_key_rules"] == "true"

            # Compute usable paths
            usable_paths_dict = {}
            for v in expected_views:
                if v in available_views_set:
                    # Get path from specimen_readiness
                    path_key = f"{v}_image_path"
                    usable_paths_dict[v] = spec_readiness.get(path_key, "")

            usable_paths_str = "; ".join([f"{k}:{v}" for k, v in usable_paths_dict.items()])

            # Determine status and recommendation
            notes_list = []
            if not expected_views:
                visibility_status = "schema_missing_view_metadata"
                review_recommendation = "schema_review_needed"
                notes_list.append("Trait schema has no defined visible_in_views.")
            elif not used_in_rules:
                visibility_status = "not_used_in_current_key"
                review_recommendation = "defer"
                notes_list.append("Trait is currently bypassed since it's not in the key.")
            else:
                # Check required views coverage
                missing_views = [v for v in expected_views if v not in available_views_set]
                if missing_views:
                    visibility_status = "missing_required_view"
                    review_recommendation = "expert_review_needed"
                    notes_list.append(f"Specimen lacks required image view(s): {', '.join(missing_views)}.")
                else:
                    visibility_status = "ready_for_image_review"
                    # Recommend action based on views
                    if expected_views == ["dorsal"]:
                        review_recommendation = "inspect_dorsal"
                    elif expected_views == ["head"]:
                        review_recommendation = "inspect_head"
                    elif expected_views == ["profile"]:
                        review_recommendation = "inspect_profile"
                    else:
                        review_recommendation = "inspect_multiple_views"

            notes = " ".join(notes_list)

            # Record stats
            visibility_status_counts[visibility_status] = visibility_status_counts.get(visibility_status, 0) + 1
            review_recommendation_counts[review_recommendation] = review_recommendation_counts.get(review_recommendation, 0) + 1

            matrix_row = {
                "specimen_id": spec_id,
                "catalog_number": cat_num,
                "kb_taxon_id": kb_tax_id,
                "dataset_genus": dataset_genus,
                "dataset_species": dataset_species,
                "trait_id": trait_id,
                "expected_views": ", ".join(expected_views),
                "available_views": ", ".join(available_views),
                "usable_image_paths": usable_paths_str,
                "used_in_key_rules": str(used_in_rules).lower(),
                "visibility_status": visibility_status,
                "review_recommendation": review_recommendation,
                "notes": notes
            }
            matrix_rows.append(matrix_row)

    # Save specimen_trait_visibility_matrix.csv
    matrix_csv_path = os.path.join(output_dir, "specimen_trait_visibility_matrix.csv")
    matrix_fieldnames = [
        "specimen_id", "catalog_number", "kb_taxon_id", "dataset_genus", "dataset_species",
        "trait_id", "expected_views", "available_views", "usable_image_paths",
        "used_in_key_rules", "visibility_status", "review_recommendation", "notes"
    ]
    with open(matrix_csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=matrix_fieldnames)
        writer.writeheader()
        writer.writerows(matrix_rows)

    # ==========================================
    # Task F: KB Subset Coverage Analysis
    # ==========================================
    represented_kb_taxa = sorted(list(set([s["kb_taxon_id"] for s in specimens if s.get("kb_taxon_id")])))
    unrepresented_kb_taxa = sorted(list(set(taxon_ids) - set(represented_kb_taxa)))

    # Taxa with insufficient specimens (< 5 selected specimens)
    taxon_spec_counts = {}
    for s in specimens:
        tid = s.get("kb_taxon_id")
        if tid:
            taxon_spec_counts[tid] = taxon_spec_counts.get(tid, 0) + 1

    taxa_with_insufficient_specimens = []
    for tid in sorted(list(taxon_ids)):
        cnt = taxon_spec_counts.get(tid, 0)
        if cnt < 5:
            taxa_with_insufficient_specimens.append(tid)

    # Trait & Rule path tracing
    # Find all path-of-rules leading to each represented taxon
    represented_rules_exercised_set = set()
    for target_tax in represented_kb_taxa:
        paths = find_rules_to_taxon(target_tax, couplet_rules)
        for path_of_rules in paths:
            for rule in path_of_rules:
                represented_rules_exercised_set.add(rule["rule_id"])

    represented_rules_exercised = sorted(list(represented_rules_exercised_set))

    # All rules in rules_data
    all_rule_ids = set()
    for rules in couplet_rules.values():
        for r in rules:
            all_rule_ids.add(r["rule_id"])

    unrepresented_rules = sorted(list(all_rule_ids - represented_rules_exercised_set))

    # Traits used in represented rules
    represented_traits_used_set = set()
    for rules in couplet_rules.values():
        for r in rules:
            if r["rule_id"] in represented_rules_exercised_set:
                for cond in r.get("conditions", []):
                    represented_traits_used_set.add(cond["trait_id"])

    represented_traits_used = sorted(list(represented_traits_used_set))
    unrepresented_traits = sorted(list(trait_ids - represented_traits_used_set))

    coverage_payload = {
        "represented_kb_taxa": represented_kb_taxa,
        "unrepresented_kb_taxa": unrepresented_kb_taxa,
        "taxa_with_insufficient_specimens": taxa_with_insufficient_specimens,
        "represented_rules_exercised": represented_rules_exercised,
        "unrepresented_rules": unrepresented_rules,
        "represented_traits_used": represented_traits_used,
        "unrepresented_traits": unrepresented_traits
    }

    # Save kb_subset_coverage.json
    coverage_json_path = os.path.join(output_dir, "kb_subset_coverage.json")
    with open(coverage_json_path, "w", encoding="utf-8") as f:
        json.dump(coverage_payload, f, indent=2)

    # ==========================================
    # Task G: Consolidated Audit Summary JSON
    # ==========================================
    selected_species_set = set()
    for spec in specimens:
        genus = spec.get("dataset_genus", "")
        species = spec.get("dataset_species", "")
        if genus and species:
            selected_species_set.add(f"{genus}_{species}")

    summary_payload = {
        "status": "success",
        "selected_specimens": len(specimens),
        "selected_taxa": len(represented_kb_taxa),
        "selected_species": len(selected_species_set),
        "split_counts": split_counts,
        "kb_trait_count": len(trait_ids),
        "kb_rule_count": len(all_rule_ids),
        "traits_used_in_rules": traits_used_in_rules_count,
        "traits_not_used_in_rules": traits_not_used_in_rules_count,
        "traits_with_view_metadata": traits_with_view_metadata_count,
        "traits_missing_view_metadata": traits_missing_view_metadata_count,
        "specimens_ready": specimens_ready_count,
        "specimens_missing_files": specimens_missing_files_count,
        "specimen_trait_rows": len(matrix_rows),
        "visibility_status_counts": visibility_status_counts,
        "review_recommendation_counts": review_recommendation_counts,
        "represented_kb_taxa": represented_kb_taxa,
        "unrepresented_kb_taxa": unrepresented_kb_taxa,
        "output_dir": output_dir
    }

    # Save summary.json
    summary_json_path = os.path.join(output_dir, "summary.json")
    with open(summary_json_path, "w", encoding="utf-8") as f:
        json.dump(summary_payload, f, indent=2)

    return summary_payload
