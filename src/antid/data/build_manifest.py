import argparse
import csv
import logging
import os
import re
import sys
from pathlib import Path
from typing import Tuple

from antid.data.detect_view import detect_view_type

# Set up logger
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}


def split_folder_name(folder: str) -> Tuple[str, str]:
    """Splits folder name into genus and species using standard delimiters."""
    for sep in ["_", "-", " "]:
        if sep in folder:
            parts = folder.split(sep, 1)
            genus = parts[0].strip()
            species = parts[1].strip()
            if genus and species:
                return genus, species
    return "", ""


def parse_genus_species(path: Path, image_root: Path) -> Tuple[str, str]:
    """
    Infers genus and species binomial components from the folder structure.
    Tries nested structure (genus/species/) first, then combined folder name.
    """
    try:
        rel_path = path.relative_to(image_root)
    except ValueError:
        rel_path = path

    parts = rel_path.parts[:-1]  # exclude filename
    if not parts:
        return "", ""

    # Check the immediate parent directory
    parent = parts[-1]

    # Try split-based parent (e.g. genus_species or genus-species)
    genus, species = split_folder_name(parent)
    if genus and species:
        return genus, species

    # Try nested structure: genus/species
    if len(parts) >= 2:
        genus = parts[-2].strip()
        species = parts[-1].strip()
        # Ensure it's not a root directory or empty
        if genus and species:
            return genus, species

    # If it's a single folder but has no delimiter, treat it as a genus only (or fail)
    if len(parts) == 1 and parts[0]:
        return parts[0].strip(), ""

    return "", ""


def parse_specimen_id(filename: str) -> str:
    """Parses standard specimen ID codes (e.g. CASENT0123456) from filename."""
    # Find sequence of 2-10 letters followed by 1 or more digits
    match = re.search(r"([a-zA-Z]{2,10}\d+)", filename)
    if match:
        return match.group(1).upper()
    return "unknown"


def build_manifest(
    image_root: str,
    output_path: str,
    fallback_genus: str = None,
    fallback_species: str = None,
    absolute_paths: bool = False,
) -> None:
    """Scans the image root and builds a clean dataset manifest CSV."""
    image_root_path = Path(image_root)
    if not image_root_path.exists() or not image_root_path.is_dir():
        raise FileNotFoundError(f"Image root directory does not exist: {image_root}")

    logger.info(f"Scanning images under: {image_root_path}")

    records = []
    skipped_count = 0

    # Collect all image files
    for root, _, files in os.walk(image_root_path):
        for file in files:
            file_path = Path(root) / file
            if file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                # Ensure the file exists (redundant but robust)
                if not file_path.exists():
                    raise FileNotFoundError(f"Missing image file found during scan: {file_path}")

                # Infer genus and species
                genus, species = parse_genus_species(file_path, image_root_path)

                # Fallback behavior
                if not genus and fallback_genus:
                    genus = fallback_genus
                if not species and fallback_species:
                    species = fallback_species

                # Clean binomial values
                genus = genus.capitalize() if genus else ""
                species = species.lower() if species else ""

                # Fail loudly if required labels are missing
                if not genus or not species:
                    logger.warning(
                        f"Could not infer genus/species for {file_path}. "
                        f"Parsed: genus='{genus}', species='{species}'."
                    )
                    raise ValueError(
                        f"Missing required taxonomic label for file: {file_path}. "
                        "Ensure the folder structure contains 'genus_species' or "
                        "provide fallback CLI arguments."
                    )

                # Detect view type
                view_type = detect_view_type(file_path)

                # Parse specimen_id
                specimen_id = parse_specimen_id(file_path.name)

                # Determine path representation
                if absolute_paths:
                    image_path_value = str(file_path.resolve())
                else:
                    image_path_value = str(file_path.relative_to(image_root_path))

                # Store record info
                records.append({
                    "image_path": image_path_value,
                    "genus": genus,
                    "species": species,
                    "view_type": view_type,
                    "source_url": "",
                    "specimen_id": specimen_id,
                    "image_quality_flag": "unchecked",
                })
            else:
                if not file.startswith("."):
                    skipped_count += 1

    if not records:
        logger.warning("No images with supported extensions found.")
        raise ValueError(f"No valid images found in root directory: {image_root}")

    # Build deterministic ID mappings based on alphabetical order
    unique_genera = sorted(list(set(r["genus"] for r in records)))
    genus_to_id = {genus: idx for idx, genus in enumerate(unique_genera)}

    # Species is identified by its binomial representation to prevent sharing species epithets
    unique_species_binomials = sorted(list(set(f"{r['genus']} {r['species']}" for r in records)))
    species_to_id = {binomial: idx for idx, binomial in enumerate(unique_species_binomials)}

    # Map the IDs to our records
    for r in records:
        r["label_genus_id"] = genus_to_id[r["genus"]]
        binomial = f"{r['genus']} {r['species']}"
        r["label_species_id"] = species_to_id[binomial]

    # Reorder columns to match output requirements
    columns = [
        "image_path",
        "genus",
        "species",
        "label_genus_id",
        "label_species_id",
        "view_type",
        "source_url",
        "specimen_id",
        "image_quality_flag",
    ]

    # Write manifest CSV
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for r in records:
            writer.writerow({col: r[col] for col in columns})

    logger.info(f"Successfully wrote manifest to {out_path}")
    logger.info(f"Total records: {len(records)}")
    logger.info(f"Unique genera count: {len(unique_genera)}")
    logger.info(f"Unique species count: {len(unique_species_binomials)}")
    if skipped_count > 0:
        logger.info(f"Skipped {skipped_count} non-image files.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan image directory and write manifest CSV.")
    parser.add_argument("--image-root", required=True, help="Root directory containing ant images.")
    parser.add_argument(
        "--output", default="data/processed/manifest.csv", help="Output path for the manifest CSV."
    )
    parser.add_argument(
        "--fallback-genus",
        help="Fallback genus name to use if it cannot be inferred from path.",
    )
    parser.add_argument(
        "--fallback-species",
        help="Fallback species name to use if it cannot be inferred from path.",
    )
    parser.add_argument(
        "--absolute-paths",
        action="store_true",
        help="Write absolute resolved paths into manifest instead of relative paths from image-root.",
    )

    args = parser.parse_args()

    try:
        build_manifest(
            args.image_root,
            args.output,
            fallback_genus=args.fallback_genus,
            fallback_species=args.fallback_species,
            absolute_paths=args.absolute_paths,
        )
    except Exception as e:
        logger.error(f"Failed to build manifest: {e}")
        sys.exit(1)
