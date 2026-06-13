#!/usr/bin/env python3
"""
src/antid/data/build_dataset_variants.py

This script processes the legacy AntWeb CSV metadata and generates three reproducible
metadata-only dataset manifests:
1. Dataset v1-original: Baseline reproduction (all valid rows, 97 species, mixed caste, uncapped)
2. Dataset v1-specimen-aware: Identical to v1-original but intended for specimen-level grouped splits
3. Dataset v2-curated: High-quality curated subset (worker caste only, complete tri-view, capped at 30 specimens per species)

It also includes comprehensive schema, curation, and split leakage validation checks.
"""

import argparse
import csv
import logging
import os
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Set up logger
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def parse_scientific_name(scientific_name: str) -> Tuple[str, str]:
    """
    Split the scientific name string and return (genus, species).
    Ensures robust binomial extraction.
    """
    if not scientific_name:
        raise ValueError("Empty scientific name")
    tokens = [t for t in re.split(r'[_\s]+', scientific_name.strip()) if t]
    if len(tokens) < 2:
        raise ValueError(f"Too few tokens in name: {scientific_name}")
    genus = tokens[0].capitalize()
    species = tokens[1].lower()
    return genus, species


def normalize_image_url(url: str) -> str:
    """
    Normalizes image URL to use the secure HTTPS static server.
    """
    url = url.strip()
    # Replace http://www.antweb.org/images/ or http://antweb.org/images/ with https://static.antweb.org/images/
    url = re.sub(r'https?://(?:www\.)?antweb\.org/images/', 'https://static.antweb.org/images/', url)
    return url


def map_shot_to_view_type(shot_type: str) -> str:
    """
    Maps legacy shot_type code ('d', 'h', 'p') to standardized view_type ('dorsal', 'head', 'profile').
    """
    code = shot_type.strip().lower()
    if code == "d":
        return "dorsal"
    elif code == "h":
        return "head"
    elif code == "p":
        return "profile"
    return "unknown"


def parse_legacy_csv(csv_path: str) -> List[Dict]:
    """
    Reads the legacy CSV, validates schema and rows, and returns a list of cleaned dictionaries.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Legacy CSV file not found: {csv_path}")

    records = []
    skipped_count = 0

    with open(path, mode="r", newline="", encoding="utf-8") as f:
        first_line = f.readline()
        f.seek(0)
        delimiter = ";" if ";" in first_line else ","
        reader = csv.DictReader(f, delimiter=delimiter)

        required_cols = ["catalog_number", "scientific_name", "shot_type", "image_url", "caste", "caste_big"]
        if reader.fieldnames:
            missing = [col for col in required_cols if col not in reader.fieldnames]
            if missing:
                raise ValueError(f"Missing required columns in legacy CSV: {missing}")

        for line_idx, row in enumerate(reader, start=2):
            catalog_number = row.get("catalog_number", "").strip()
            scientific_name = row.get("scientific_name", "").strip()
            shot_type = row.get("shot_type", "").strip()
            image_url = row.get("image_url", "").strip()
            caste = row.get("caste", "").strip()
            caste_big = row.get("caste_big", "").strip()

            # Skip malformed/incomplete rows
            if not catalog_number or not scientific_name or not image_url:
                logger.warning(f"Line {line_idx}: Skipped due to missing essential field(s).")
                skipped_count += 1
                continue

            try:
                genus, species = parse_scientific_name(scientific_name)
            except ValueError as e:
                logger.warning(f"Line {line_idx}: Failed to parse binomial name '{scientific_name}': {e}")
                skipped_count += 1
                continue

            # Standardized fields
            view_type = map_shot_to_view_type(shot_type)
            norm_url = normalize_image_url(image_url)

            # Local path representation if it were downloaded
            shot_code = shot_type.strip().lower() if shot_type else "unknown"
            image_path = f"data/raw/images/{genus.lower()}_{species.lower()}/{catalog_number.lower()}_{shot_code}.jpg"

            records.append({
                "catalog_number": catalog_number,
                "specimen_id": catalog_number,
                "scientific_name": f"{genus} {species}",
                "genus": genus,
                "species": species,
                "view_type": view_type,
                "caste": caste_big if caste_big else (caste if caste else "unknown"),
                "caste_raw": caste,
                "caste_big_raw": caste_big,
                "source_url": norm_url,
                "image_url": norm_url,
                "image_path": image_path,
                "image_quality_flag": "unchecked"
            })

    logger.info(f"Parsed {len(records)} valid records from legacy CSV. Skipped {skipped_count} malformed rows.")
    return records


def compute_ids_and_write(records: List[Dict], output_path: str) -> None:
    """
    Computes label_genus_id and label_species_id based on sorted alphabetical unique classes
    for this specific manifest, then writes to CSV.
    """
    # Build alphabetical class list
    unique_genera = sorted(list(set(r["genus"] for r in records)))
    genus_to_id = {g: idx for idx, g in enumerate(unique_genera)}

    unique_species = sorted(list(set(r["scientific_name"] for r in records)))
    species_to_id = {sp: idx for idx, sp in enumerate(unique_species)}

    # Apply IDs to records
    for r in records:
        r["label_genus_id"] = genus_to_id[r["genus"]]
        r["label_species_id"] = species_to_id[r["scientific_name"]]

    columns = [
        "image_path",
        "genus",
        "species",
        "label_genus_id",
        "label_species_id",
        "view_type",
        "caste",
        "source_url",
        "image_url",
        "specimen_id",
        "catalog_number",
        "image_quality_flag",
    ]

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with open(out_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for r in records:
            # Only write standard columns
            writer.writerow({col: r[col] for col in columns})

    logger.info(f"Wrote manifest to {out_file} (Records: {len(records)}, Genus count: {len(unique_genera)}, Species count: {len(unique_species)})")


def filter_and_curate_v2(records: List[Dict], seed: int = 42) -> List[Dict]:
    """
    Crates Dataset v2-curated:
    - Worker caste only
    - Complete tri-view (d, h, p) specimens only (exactly 1 dorsal, 1 head, 1 profile per specimen)
    - Cap each species at 30 complete specimens (sorted alphabetically, deterministically shuffled and sliced)
    """
    rng = random.Random(seed)

    # 1. Worker caste filtering
    workers_only = [r for r in records if r["caste"].strip().lower() == "worker"]
    logger.info(f"v2 curation: Worker-only filter retained {len(workers_only)} rows.")

    # 2. Group by physical specimen (catalog_number)
    specimen_groups = defaultdict(list)
    for r in workers_only:
        specimen_groups[r["catalog_number"]].append(r)

    # 3. Identify and build complete tri-view specimens
    complete_specimens = []
    for cat_num, rows in specimen_groups.items():
        # Partition rows by view_type
        by_view = defaultdict(list)
        for row in rows:
            by_view[row["view_type"]].append(row)

        if "dorsal" in by_view and "head" in by_view and "profile" in by_view:
            # Exactly one of each (select the first one)
            d_row = by_view["dorsal"][0]
            h_row = by_view["head"][0]
            p_row = by_view["profile"][0]
            complete_specimens.append((cat_num, d_row["scientific_name"], [d_row, h_row, p_row]))

    logger.info(f"v2 curation: Found {len(complete_specimens)} complete tri-view physical specimens.")

    # Group complete specimens by species
    species_to_specimens = defaultdict(list)
    for cat_num, sci_name, rows in complete_specimens:
        species_to_specimens[sci_name].append((cat_num, rows))

    final_records = []

    # 4. Cap species at 30 complete specimens
    for sci_name, spec_list in sorted(species_to_specimens.items()):
        # Sort alphabetically by catalog number first to ensure deterministic baseline
        sorted_spec_list = sorted(spec_list, key=lambda x: x[0])
        # Deterministically shuffle
        rng.shuffle(sorted_spec_list)
        # Cap at 30
        capped_spec_list = sorted_spec_list[:30]

        # Extend final records with all 3 views of the selected specimens
        for cat_num, rows in capped_spec_list:
            final_records.extend(rows)

    logger.info(f"v2 curation: Capping at 30 specimens yielded {len(final_records)} images from {len(final_records) // 3} specimens.")
    return final_records


def validate_manifest(manifest_path: str, is_v2: bool = False) -> bool:
    """
    Validates manifest structure and constraints.
    Returns True if valid, False otherwise.
    """
    path = Path(manifest_path)
    if not path.exists():
        logger.error(f"Validation failed: Manifest {manifest_path} does not exist.")
        return False

    with open(path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames if reader.fieldnames else []

        required = ["image_path", "genus", "species", "label_genus_id", "label_species_id", "view_type", "caste", "source_url", "image_url", "specimen_id", "catalog_number"]
        missing = [c for col in required if (c := col) not in headers]
        if missing:
            logger.error(f"Validation failed: Missing columns {missing} in {manifest_path}")
            return False

        rows = list(reader)

    if not rows:
        logger.error(f"Validation failed: Manifest {manifest_path} is empty.")
        return False

    valid_views = {"dorsal", "head", "profile", "unknown"}
    is_valid = True

    # 1. Non-empty check and view_type validation
    for idx, row in enumerate(rows, start=2):
        img_url = row.get("image_url", "").strip()
        sci_name = f"{row.get('genus', '').strip()} {row.get('species', '').strip()}".strip()
        spec_id = row.get("specimen_id", "").strip()
        view_type = row.get("view_type", "").strip()
        caste = row.get("caste", "").strip()

        if not img_url:
            logger.error(f"Row {idx}: Missing image_url")
            is_valid = False
        if not sci_name or len(sci_name.split()) < 2:
            logger.error(f"Row {idx}: Missing or invalid scientific_name")
            is_valid = False
        if not spec_id:
            logger.error(f"Row {idx}: Missing specimen_id")
            is_valid = False
        if view_type not in valid_views:
            logger.error(f"Row {idx}: Invalid view_type '{view_type}'")
            is_valid = False

        if is_v2:
            if caste.lower() != "worker":
                logger.error(f"Row {idx}: Non-worker caste '{caste}' found in v2")
                is_valid = False

    if is_v2:
        # Group by specimen
        specimen_to_rows = defaultdict(list)
        for row in rows:
            specimen_to_rows[row["specimen_id"]].append(row)

        species_to_spec_counts = defaultdict(set)

        for spec_id, s_rows in specimen_to_rows.items():
            species = f"{s_rows[0]['genus']} {s_rows[0]['species']}"
            species_to_spec_counts[species].add(spec_id)

            # Check tri-view completeness
            views = [r["view_type"] for r in s_rows]
            if len(views) != 3 or set(views) != {"dorsal", "head", "profile"}:
                logger.error(f"Specimen {spec_id} has invalid or incomplete views: {views}")
                is_valid = False

        # Check capping at 30
        for species, specs in species_to_spec_counts.items():
            if len(specs) > 30:
                logger.error(f"Species {species} exceeds 30 specimen cap: {len(specs)} unique specimens")
                is_valid = False

    return is_valid


def check_split_leakage(split_dir: str) -> bool:
    """
    Checks for specimen ID leakage across train, val, and test splits.
    Returns True if no leakage, False if leaks are found.
    """
    s_dir = Path(split_dir)
    train_path = s_dir / "train.csv"
    val_path = s_dir / "val.csv"
    test_path = s_dir / "test.csv"

    if not train_path.exists() or not val_path.exists() or not test_path.exists():
        logger.warning(f"Split files not found in {split_dir}, skipping leakage check.")
        return True

    def get_specimens(path: Path) -> Set[str]:
        specs = set()
        with open(path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                spec_id = row.get("specimen_id", "").strip()
                if spec_id:
                    specs.add(spec_id)
        return specs

    train_specs = get_specimens(train_path)
    val_specs = get_specimens(val_path)
    test_specs = get_specimens(test_path)

    leak_train_val = train_specs & val_specs
    leak_train_test = train_specs & test_specs
    leak_val_test = val_specs & test_specs

    is_clean = True
    if leak_train_val:
        logger.error(f"LEAKAGE found between train and val splits in {split_dir}: {leak_train_val}")
        is_clean = False
    if leak_train_test:
        logger.error(f"LEAKAGE found between train and test splits in {split_dir}: {leak_train_test}")
        is_clean = False
    if leak_val_test:
        logger.error(f"LEAKAGE found between val and test splits in {split_dir}: {leak_val_test}")
        is_clean = False

    if is_clean:
        logger.info(f"Leakage Check PASSED for {split_dir}: no overlapping physical specimens detected.")
    return is_clean


def build_dataset_variants(csv_path: str, output_dir: str, seed: int = 42) -> Tuple[str, str, str]:
    """
    Main library function to parse the legacy CSV and generate the three dataset variant manifests.
    """
    logger.info(f"Parsing legacy CSV: {csv_path}")
    all_records = parse_legacy_csv(csv_path)

    # 1. Build v1-original
    logger.info("Building Dataset v1-original...")
    v1_orig_path = os.path.join(output_dir, "v1_original_manifest.csv")
    compute_ids_and_write(all_records, v1_orig_path)

    # 2. Build v1-specimen-aware (exact same rows)
    logger.info("Building Dataset v1-specimen-aware...")
    v1_spec_path = os.path.join(output_dir, "v1_specimen_aware_manifest.csv")
    compute_ids_and_write(all_records, v1_spec_path)

    # 3. Build v2-curated
    logger.info("Building Dataset v2-curated...")
    v2_records = filter_and_curate_v2(all_records, seed=seed)
    v2_curated_path = os.path.join(output_dir, "v2_curated_manifest.csv")
    compute_ids_and_write(v2_records, v2_curated_path)

    return v1_orig_path, v1_spec_path, v2_curated_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate dataset variants and validate splits.")
    parser.add_argument("--csv", default="downloader/Sup_top97species_Qmed_def_info.csv", help="Path to legacy CSV file.")
    parser.add_argument("--output-dir", default="data/processed", help="Directory where generated manifests will be saved.")
    parser.add_argument("--seed", type=int, default=42, help="Seed for reproducible specimen selection in v2.")
    parser.add_argument("--run-splits", action="store_true", help="Automatically generate the splits after manifests are created.")

    args = parser.parse_args()

    try:
        v1_orig_path, v1_spec_path, v2_curated_path = build_dataset_variants(
            csv_path=args.csv,
            output_dir=args.output_dir,
            seed=args.seed
        )

        # Validation Checks
        logger.info("\nValidating generated manifests...")
        v1_orig_ok = validate_manifest(v1_orig_path, is_v2=False)
        v1_spec_ok = validate_manifest(v1_spec_path, is_v2=False)
        v2_cur_ok = validate_manifest(v2_curated_path, is_v2=True)

        if not (v1_orig_ok and v1_spec_ok and v2_cur_ok):
            logger.error("Manifest validation FAILED.")
            sys.exit(1)
        else:
            logger.info("Manifest validation PASSED for all three variants.")

        if args.run_splits:
            # We import and call build_splits dynamically
            from antid.data.build_splits import build_splits
            logger.info("\nGenerating splits for Dataset v1-original (image-level)...")
            build_splits(
                manifest_path=v1_orig_path,
                output_dir="data/splits/v1_original",
                target="species",
                train_ratio=0.70,
                val_ratio=0.15,
                test_ratio=0.15,
                seed=42,
                allow_unstratified=True
            )

            logger.info("\nGenerating splits for Dataset v1-specimen-aware (specimen-level grouped)...")
            build_splits(
                manifest_path=v1_spec_path,
                output_dir="data/splits/v1_specimen_aware",
                target="species",
                train_ratio=0.70,
                val_ratio=0.15,
                test_ratio=0.15,
                seed=42,
                allow_unstratified=True,
                specimen_aware=True
            )

            logger.info("\nGenerating splits for Dataset v2-curated (specimen-level grouped)...")
            build_splits(
                manifest_path=v2_curated_path,
                output_dir="data/splits/v2_curated",
                target="species",
                train_ratio=0.70,
                val_ratio=0.15,
                test_ratio=0.15,
                seed=42,
                allow_unstratified=True,
                specimen_aware=True
            )

            # Leakage checks
            logger.info("\nPerforming specimen leakage checks across splits...")
            leak_v1_orig = check_split_leakage("data/splits/v1_original") # should expect leakage if random split
            leak_v1_spec = check_split_leakage("data/splits/v1_specimen_aware")
            leak_v2_cur = check_split_leakage("data/splits/v2_curated")

            if not (leak_v1_spec and leak_v2_cur):
                logger.error("Specimen-aware splits failed leakage validation!")
                sys.exit(1)
            else:
                logger.info("All specimen-aware splits successfully passed leakage checks!")

        logger.info("\nDataset variant generation and validation completed successfully!")

    except Exception as e:
        logger.error(f"Failed to execute variant builder: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
