import argparse
import csv
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Set up logger
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = [
    "image_path",
    "genus",
    "species",
    "label_genus_id",
    "label_species_id",
    "view_type",
]
VALID_VIEW_TYPES = {"dorsal", "head", "profile", "unknown"}


def validate_dataset(manifest_path: str, image_root: str = None) -> bool:
    """
    Validates a dataset manifest CSV and verifies image files on disk.

    Returns:
        bool: True if dataset is completely valid, False otherwise.
    """
    path = Path(manifest_path)
    if not path.exists():
        logger.error(f"Manifest file does not exist: {manifest_path}")
        return False

    logger.info(f"Validating manifest: {manifest_path}")

    # Read rows
    rows = []
    with open(path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames if reader.fieldnames else []

        # Check required columns
        missing_cols = [col for col in REQUIRED_COLUMNS if col not in headers]
        if missing_cols:
            logger.error(f"Missing required columns in manifest: {missing_cols}")
            return False

        for row in reader:
            rows.append(row)

    if not rows:
        logger.error("Manifest is empty (contains no rows of data).")
        return False

    is_valid = True
    seen_paths = set()
    errors = []

    # Map tracking for consistency checks
    # Genus mappings: genus_str -> set of genus_ids, and genus_id -> set of genus_strs
    genus_to_ids = defaultdict(set)
    id_to_genera = defaultdict(set)

    # Species mappings: (genus, species) -> set of species_ids, and species_id -> set of (genus, species)
    species_to_ids = defaultdict(set)
    id_to_species = defaultdict(set)

    # Count accumulators
    genus_counts = Counter()
    species_counts = Counter()
    view_counts = Counter()

    for idx, row in enumerate(rows, start=1):
        line_num = idx + 1  # 1-indexed header + row index
        image_path_str = row["image_path"]
        genus = row["genus"].strip()
        species = row["species"].strip()
        genus_id_str = row["label_genus_id"].strip()
        species_id_str = row["label_species_id"].strip()
        view_type = row["view_type"].strip()

        # 1. Non-empty required labels
        if not genus:
            errors.append(f"Row {line_num}: 'genus' is empty.")
            is_valid = False
        if not species:
            errors.append(f"Row {line_num}: 'species' is empty.")
            is_valid = False

        # 2. Check view_type is valid
        if view_type not in VALID_VIEW_TYPES:
            errors.append(f"Row {line_num}: Invalid view_type '{view_type}'. Must be one of {list(VALID_VIEW_TYPES)}")
            is_valid = False

        # 3. Check duplicate image_path
        if image_path_str in seen_paths:
            errors.append(f"Row {line_num}: Duplicate 'image_path' found: {image_path_str}")
            is_valid = False
        else:
            seen_paths.add(image_path_str)

        # 4. Check image file existence on disk
        img_file_path = Path(image_path_str)
        if not img_file_path.is_absolute() and image_root:
            img_file_path = Path(image_root) / img_file_path

        if not img_file_path.exists() or not img_file_path.is_file():
            errors.append(f"Row {line_num}: Image file does not exist: {img_file_path}")
            is_valid = False

        # Parse ID strings as ints
        try:
            genus_id = int(genus_id_str)
        except ValueError:
            errors.append(f"Row {line_num}: 'label_genus_id' is not a valid integer: '{genus_id_str}'")
            is_valid = False
            genus_id = None

        try:
            species_id = int(species_id_str)
        except ValueError:
            errors.append(f"Row {line_num}: 'label_species_id' is not a valid integer: '{species_id_str}'")
            is_valid = False
            species_id = None

        # 5. ID Consistency maps
        if genus and genus_id is not None:
            genus_to_ids[genus].add(genus_id)
            id_to_genera[genus_id].add(genus)

        if genus and species and species_id is not None:
            binomial = f"{genus} {species}"
            species_to_ids[binomial].add(species_id)
            id_to_species[species_id].add(binomial)

        # Increment counts if basic tags exist
        if genus:
            genus_counts[genus] += 1
        if genus and species:
            species_counts[f"{genus} {species}"] += 1
        if view_type:
            view_counts[view_type] += 1

    # 6. Evaluate ID consistency
    for g, ids in genus_to_ids.items():
        if len(ids) > 1:
            errors.append(f"Inconsistency: Genus '{g}' mapped to multiple IDs: {sorted(list(ids))}")
            is_valid = False

    for gid, genera in id_to_genera.items():
        if len(genera) > 1:
            errors.append(f"Inconsistency: Genus ID {gid} mapped to multiple genera: {sorted(list(genera))}")
            is_valid = False

    for sp, ids in species_to_ids.items():
        if len(ids) > 1:
            errors.append(f"Inconsistency: Species '{sp}' mapped to multiple IDs: {sorted(list(ids))}")
            is_valid = False

    for sid, species_list in id_to_species.items():
        if len(species_list) > 1:
            errors.append(f"Inconsistency: Species ID {sid} mapped to multiple species: {sorted(list(species_list))}")
            is_valid = False

    # Report errors
    if errors:
        logger.error(f"Validation failed with {len(errors)} error(s):")
        # limit error printing to avoid flooding CLI
        for err in errors[:50]:
            logger.error(f"  - {err}")
        if len(errors) > 50:
            logger.error(f"  - ... and {len(errors) - 50} more errors")
    else:
        logger.info("Manifest CSV syntax, fields, and file existence checks are 100% valid.")

    # Always report counts
    print("\n" + "=" * 40)
    print(" DATASET DISTRIBUTION SUMMARY ")
    print("=" * 40)

    print(f"\nTotal Records: {len(rows)}")

    print("\n--- Counts by Genus ---")
    for g, count in sorted(genus_counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {g:<20} : {count}")

    print("\n--- Counts by Species ---")
    for s, count in sorted(species_counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {s:<30} : {count}")

    print("\n--- Counts by View Type ---")
    for vt, count in sorted(view_counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {vt:<20} : {count}")
    print("=" * 40 + "\n")

    return is_valid


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate dataset manifest and images.")
    parser.add_argument("--manifest", required=True, help="Path to manifest CSV file.")
    parser.add_argument(
        "--image-root",
        help="Optional root directory to resolve relative image paths on disk.",
    )

    args = parser.parse_args()

    success = validate_dataset(args.manifest, args.image_root)
    if not success:
        logger.error("Dataset validation FAILED.")
        sys.exit(1)
    else:
        logger.info("Dataset validation PASSED.")
        sys.exit(0)
