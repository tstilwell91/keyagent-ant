"""Trait curation dataset selection module.

Provides utilities to select real physical specimens from curated splits
and generate structured selection CSVs and blank non-evidentiary annotation templates.
"""

import csv
import json
import os
import random
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from .kb_loader import load_kb


def row_matches_taxon(row: Dict[str, Any], taxon: Dict[str, Any]) -> bool:
    """Checks if a split CSV row matches a KB taxon registry entry case-insensitively."""
    genus_val = str(row.get("genus", "")).strip().lower()
    species_val = str(row.get("species", "")).strip().lower()
    
    taxon_id = str(taxon.get("taxon_id", "")).strip().lower()
    scientific_name = str(taxon.get("scientific_name", "")).strip().lower()
    
    rank = str(taxon.get("rank", "")).strip().lower()
    if rank == "genus":
        return genus_val == scientific_name or genus_val == taxon_id
    elif rank == "species":
        binomial_space = f"{genus_val} {species_val}".strip()
        binomial_under = f"{genus_val}_{species_val}".strip()
        return (
            binomial_space == scientific_name or
            binomial_space == taxon_id or
            binomial_under == scientific_name or
            binomial_under == taxon_id or
            species_val == scientific_name or
            species_val == taxon_id
        )
    return False


def choose_representative_image(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Selects one representative image deterministically when multiple images exist for a view.

    Prefers image_quality_flag if available and meaningful (non-empty and not unchecked).
    Otherwise sorts by image_path alphabetically and chooses the first.
    """
    def sort_key(r: Dict[str, Any]):
        q = str(r.get("image_quality_flag", "")).strip().lower()
        path = str(r.get("image_path", "")).strip().lower()
        
        # Define quality rank score (lower is better)
        if q in ["high", "excellent", "checked", "good"]:
            rank = 0
        elif q in ["unchecked", ""]:
            rank = 1
        elif q in ["low", "poor", "bad"]:
            rank = 3
        else:
            rank = 2  # other custom flags
        return (rank, path)

    sorted_rows = sorted(rows, key=sort_key)
    return sorted_rows[0]


def select_trait_curation_specimens(
    split_dir: str,
    kb_dir: str,
    output_selection: str,
    output_template: str,
    specimens_per_taxon: int = 5,
    preferred_split: str = "test",
    seed: int = 42,
    allow_split_fallback: bool = True
) -> Dict[str, Any]:
    """Selects physical specimens from splits and writes selection and template files.

    Args:
        split_dir: Directory containing train.csv, val.csv, and test.csv.
        kb_dir: Path to the taxonomic KB directory.
        output_selection: Path to write the selection CSV.
        output_template: Path to write the JSONL blank annotation template.
        specimens_per_taxon: Maximum specimens to select per KB taxon.
        preferred_split: Split to prioritize (test, val, or train).
        seed: Random seed for deterministic selection.
        allow_split_fallback: If True, falls back to other splits if preferred split lacks quota.

    Returns:
        A JSON-serializable execution summary report.
    """
    # 1. Verify existence of required split files
    splits = ["train", "val", "test"]
    for s_name in splits:
        path = os.path.join(split_dir, f"{s_name}.csv")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Required split file {s_name}.csv not found in split directory: {split_dir}. "
                "Ensure v2_curated splits are generated."
            )

    # 2. Load KB to find covered taxa
    kb = load_kb(kb_dir)
    kb_taxa = kb["taxon_registry"].get("taxa", [])
    kb_taxon_ids = {t["taxon_id"] for t in kb_taxa}

    # 3. Read split CSVs and map/group rows
    all_rows = []
    unmapped_dataset_taxa = set()

    for s_name in splits:
        path = os.path.join(split_dir, f"{s_name}.csv")
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Add source split metadata
                row["_source_file_split"] = s_name
                all_rows.append(row)

                # Track unmapped taxa
                matched = False
                for t in kb_taxa:
                    if row_matches_taxon(row, t):
                        matched = True
                        break
                if not matched:
                    g = str(row.get("genus", "")).strip()
                    s = str(row.get("species", "")).strip()
                    tax_name = f"{g} {s}".strip() if s else g
                    if tax_name:
                        unmapped_dataset_taxa.add(tax_name)

    # 4. Group rows by specimen key fallback
    # Group by: specimen_id if non-empty, otherwise catalog_number
    specimens_grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in all_rows:
        spec_id = str(row.get("specimen_id", "")).strip()
        cat_num = str(row.get("catalog_number", "")).strip()
        specimen_key = spec_id if spec_id else cat_num
        if not specimen_key:
            continue
        if specimen_key not in specimens_grouped:
            specimens_grouped[specimen_key] = []
        specimens_grouped[specimen_key].append(row)

    # 5. Build candidate specimen objects that are tri-view complete
    candidates: List[Dict[str, Any]] = []
    for spec_key, rows in specimens_grouped.items():
        # Check views
        dorsal_rows = [r for r in rows if str(r.get("view_type")).strip().lower() == "dorsal"]
        head_rows = [r for r in rows if str(r.get("view_type")).strip().lower() == "head"]
        profile_rows = [r for r in rows if str(r.get("view_type")).strip().lower() == "profile"]

        # Tri-view completeness requires AT LEAST one of each view
        if len(dorsal_rows) >= 1 and len(head_rows) >= 1 and len(profile_rows) >= 1:
            # Deterministically choose representative images
            dorsal_row = choose_representative_image(dorsal_rows)
            head_row = choose_representative_image(head_rows)
            profile_row = choose_representative_image(profile_rows)

            first_row = rows[0]
            # Match first row to KB taxon
            matched_taxon = None
            for t in kb_taxa:
                if row_matches_taxon(first_row, t):
                    matched_taxon = t
                    break

            if matched_taxon:
                candidates.append({
                    "specimen_key": spec_key,
                    "specimen_id": first_row.get("specimen_id", "").strip(),
                    "catalog_number": first_row.get("catalog_number", "").strip(),
                    "kb_taxon_id": matched_taxon["taxon_id"],
                    "kb_scientific_name": matched_taxon["scientific_name"],
                    "dataset_genus": first_row.get("genus", "").strip(),
                    "dataset_species": first_row.get("species", "").strip(),
                    "source_split": first_row.get("_source_file_split"),
                    "dorsal_row": dorsal_row,
                    "head_row": head_row,
                    "profile_row": profile_row,
                    "duplicate_view_counts": f"dorsal:{len(dorsal_rows)},head:{len(head_rows)},profile:{len(profile_rows)}",
                    "tri_view_complete": True
                })

    # 6. Set deterministic selection setup
    # Sort KB taxa to ensure stable processing order
    sorted_kb_taxa = sorted(kb_taxa, key=lambda t: t["taxon_id"])
    
    preferred_split = preferred_split.strip().lower()
    if preferred_split == "test":
        splits_order = ["test", "val", "train"]
    elif preferred_split == "val":
        splits_order = ["val", "test", "train"]
    elif preferred_split == "train":
        splits_order = ["train", "test", "val"]
    else:
        splits_order = [preferred_split, "test", "val", "train"]
        seen_splits = set()
        splits_order = [x for x in splits_order if not (x in seen_splits or seen_splits.add(x))]

    if not allow_split_fallback:
        splits_order = [preferred_split]

    selected_specimens: List[Dict[str, Any]] = []
    taxa_with_insufficient_specimens = []

    # Use a single random state for perfect seed determinism across runs
    rng = random.Random(seed)

    for taxon in sorted_kb_taxa:
        t_id = taxon["taxon_id"]
        taxon_candidates = [c for c in candidates if c["kb_taxon_id"] == t_id]

        selected_for_taxon = []
        for sp in splits_order:
            candidates_in_sp = [c for c in taxon_candidates if c["source_split"] == sp]
            # Ensure stable sort by key before shuffle
            candidates_in_sp = sorted(candidates_in_sp, key=lambda x: x["specimen_key"])
            rng.shuffle(candidates_in_sp)

            # Draw up to remaining quota
            quota = specimens_per_taxon - len(selected_for_taxon)
            if quota <= 0:
                break
            selected_for_taxon.extend(candidates_in_sp[:quota])

        if len(selected_for_taxon) < specimens_per_taxon:
            taxa_with_insufficient_specimens.append(t_id)

        selected_specimens.extend(selected_for_taxon)

    # 7. Write Output CSV (Selection metadata sheet)
    Path(output_selection).parent.mkdir(parents=True, exist_ok=True)
    
    csv_headers = [
        "specimen_id", "catalog_number", "kb_taxon_id", "kb_scientific_name",
        "dataset_genus", "dataset_species", "source_split",
        "dorsal_image_path", "head_image_path", "profile_image_path",
        "dorsal_image_id", "head_image_id", "profile_image_id",
        "selection_reason", "annotation_priority", "tri_view_complete",
        "notes", "duplicate_view_counts"
    ]

    with open(output_selection, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        
        for spec in selected_specimens:
            d_row = spec["dorsal_row"]
            h_row = spec["head_row"]
            p_row = spec["profile_row"]

            # Extract image IDs as filename stems
            d_id = os.path.splitext(os.path.basename(d_row["image_path"]))[0]
            h_id = os.path.splitext(os.path.basename(h_row["image_path"]))[0]
            p_id = os.path.splitext(os.path.basename(p_row["image_path"]))[0]

            priority = "high" if spec["source_split"] == preferred_split else "medium"

            row_dict = {
                "specimen_id": spec["specimen_id"],
                "catalog_number": spec["catalog_number"],
                "kb_taxon_id": spec["kb_taxon_id"],
                "kb_scientific_name": spec["kb_scientific_name"],
                "dataset_genus": spec["dataset_genus"],
                "dataset_species": spec["dataset_species"],
                "source_split": spec["source_split"],
                "dorsal_image_path": d_row["image_path"],
                "head_image_path": h_row["image_path"],
                "profile_image_path": p_row["image_path"],
                "dorsal_image_id": d_id,
                "head_image_id": h_id,
                "profile_image_id": p_id,
                "selection_reason": f"deterministic_selection_from_{spec['source_split']}",
                "annotation_priority": priority,
                "tri_view_complete": "true",
                "notes": f"Selected using preferred_split={preferred_split}, seed={seed}. Multi-image view resolving applied.",
                "duplicate_view_counts": spec["duplicate_view_counts"]
            }
            writer.writerow(row_dict)

    # 8. Write Output JSONL (Explicitly Non-Evidentiary blank annotation template scaffold)
    Path(output_template).parent.mkdir(parents=True, exist_ok=True)

    with open(output_template, "w", encoding="utf-8") as f:
        for spec in selected_specimens:
            d_row = spec["dorsal_row"]
            h_row = spec["head_row"]
            p_row = spec["profile_row"]

            d_id = os.path.splitext(os.path.basename(d_row["image_path"]))[0]
            h_id = os.path.splitext(os.path.basename(h_row["image_path"]))[0]
            p_id = os.path.splitext(os.path.basename(p_row["image_path"]))[0]

            template_record = {
                "specimen_id": spec["specimen_id"],
                "catalog_number": spec["catalog_number"],
                "kb_taxon_id": spec["kb_taxon_id"],
                "kb_scientific_name": spec["kb_scientific_name"],
                "dataset_genus": spec["dataset_genus"],
                "dataset_species": spec["dataset_species"],
                "source_split": spec["source_split"],
                "images": {
                    "dorsal": {"image_id": d_id, "image_path": d_row["image_path"]},
                    "head": {"image_id": h_id, "image_path": h_row["image_path"]},
                    "profile": {"image_id": p_id, "image_path": p_row["image_path"]}
                },
                "observed_traits": {},
                "source_evidence": [],
                "annotation_metadata": {
                    "annotation_round": "trait_curated_v0",
                    "annotation_status": "not_started",
                    "trait_values_verified": False,
                    "trait_source_policy": "blank_template_no_traits_inferred",
                    "review_status": "needs_expert_or_source_review",
                    "annotator": None,
                    "notes": ""
                }
            }
            f.write(json.dumps(template_record) + "\n")

    # 9. Count statistics
    taxon_counts = {}
    split_counts = {}
    for spec in selected_specimens:
        t_id = spec["kb_taxon_id"]
        taxon_counts[t_id] = taxon_counts.get(t_id, 0) + 1
        
        sp = spec["source_split"]
        split_counts[sp] = split_counts.get(sp, 0) + 1

    selected_taxa = sorted(list(taxon_counts.keys()))

    return {
        "status": "success",
        "selected_specimens": len(selected_specimens),
        "selected_taxa": len(selected_taxa),
        "specimens_per_taxon_requested": specimens_per_taxon,
        "taxon_counts": taxon_counts,
        "split_counts": split_counts,
        "unmapped_dataset_taxa": sorted(list(unmapped_dataset_taxa)),
        "taxa_with_insufficient_specimens": sorted(taxa_with_insufficient_specimens),
        "output_selection": output_selection,
        "output_template": output_template
    }
