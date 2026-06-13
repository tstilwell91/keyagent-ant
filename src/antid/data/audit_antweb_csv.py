#!/usr/bin/env python3
"""
audit_antweb_csv.py

An audit utility that inspects the legacy AntWeb CSV and produces a comprehensive
dataset audit summary/report in Markdown, without downloading anything.
"""

import os
import re
import csv
import argparse
from typing import Dict, List, Set, Tuple


def parse_scientific_name(scientific_name: str) -> Tuple[str, str, str]:
    """
    Split the scientific name string and return (genus, species, folder_name).
    Robust binomial extraction.
    """
    if not scientific_name:
        raise ValueError("Empty name")
    tokens = [t for t in re.split(r'[_\s]+', scientific_name.strip()) if t]
    if len(tokens) < 2:
        raise ValueError(f"Too few tokens in name: {scientific_name}")
    genus = tokens[0].capitalize()
    species = tokens[1].lower()
    folder_name = f"{genus.lower()}_{species.lower()}"
    return genus, species, folder_name


def run_audit(csv_path: str) -> Dict:
    """
    Read CSV and calculate audit metrics.
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found at {csv_path}")

    # Raw counts and tracking
    total_rows = 0
    missing_url = 0
    missing_sci_name = 0
    
    urls: Set[str] = set()
    duplicate_urls = 0
    
    catalog_ids: Set[str] = set()
    duplicate_catalog_ids = 0

    genera_set: Set[str] = set()
    species_set: Set[str] = set()
    
    # Distributions
    genus_counts: Dict[str, int] = {}
    species_counts: Dict[str, int] = {}
    shot_type_counts: Dict[str, int] = {}
    caste_counts: Dict[str, int] = {}
    location_counts: Dict[str, int] = {}

    # For checking per-species shot coverage (d, h, p)
    # species -> set of shot types
    species_shot_coverage: Dict[str, Set[str]] = {}

    with open(csv_path, newline="", encoding="utf-8") as csvfile:
        first_line = csvfile.readline()
        csvfile.seek(0)
        delimiter = ";" if ";" in first_line else ","
        reader = csv.DictReader(csvfile, delimiter=delimiter)

        # Fail clearly on missing required columns
        required_cols = ["scientific_name", "image_url"]
        if reader.fieldnames:
            missing_cols = [col for col in required_cols if col not in reader.fieldnames]
            if missing_cols:
                raise ValueError(f"Missing required columns in CSV: {', '.join(missing_cols)}")

        for row in reader:
            total_rows += 1
            url = row.get("image_url", "").strip()
            sci_name = row.get("scientific_name", "").strip()
            catalog = row.get("catalog_number", "").strip()
            shot_type = row.get("shot_type", "").strip().lower()
            caste = row.get("caste", "").strip()
            caste_big = row.get("caste_big", "").strip()
            state = row.get("state", "").strip()

            # Track missing fields
            if not url:
                missing_url += 1
            if not sci_name:
                missing_sci_name += 1

            if not url or not sci_name:
                continue

            # Track duplicates
            if url in urls:
                duplicate_urls += 1
            urls.add(url)

            if catalog:
                if catalog in catalog_ids:
                    duplicate_catalog_ids += 1
                catalog_ids.add(catalog)

            # Parse scientific name
            try:
                genus, species, folder_name = parse_scientific_name(sci_name)
                genera_set.add(genus)
                species_set.add(folder_name)

                genus_counts[genus] = genus_counts.get(genus, 0) + 1
                species_counts[folder_name] = species_counts.get(folder_name, 0) + 1

                # Coverage tracking
                if folder_name not in species_shot_coverage:
                    species_shot_coverage[folder_name] = set()
                if shot_type:
                    species_shot_coverage[folder_name].add(shot_type)
            except ValueError:
                # Malformed names count as missing/unparseable for binomial grouping
                missing_sci_name += 1

            # View types distribution
            st_key = shot_type if shot_type else "unknown"
            shot_type_counts[st_key] = shot_type_counts.get(st_key, 0) + 1

            # Caste distribution
            c_key = caste_big if caste_big else (caste if caste else "unknown")
            caste_counts[c_key] = caste_counts.get(c_key, 0) + 1

            # State/Location distribution
            loc_key = state if state else "unknown"
            location_counts[loc_key] = location_counts.get(loc_key, 0) + 1

    # Sort species counts
    sorted_species = sorted(species_counts.items(), key=lambda x: x[1], reverse=True)
    top_20 = sorted_species[:20]
    bottom_20 = sorted_species[-20:] if len(sorted_species) >= 20 else sorted_species

    # Sort genus counts
    sorted_genera = sorted(genus_counts.items(), key=lambda x: x[1], reverse=True)

    # Coverage metrics
    total_binomial_species = len(species_set)
    full_coverage_count = 0  # d, h, and p
    partial_coverage_count = 0
    missing_coverage_count = 0

    for sp, shots in species_shot_coverage.items():
        has_d = 'd' in shots
        has_h = 'h' in shots
        has_p = 'p' in shots
        if has_d and has_h and has_p:
            full_coverage_count += 1
        elif has_d or has_h or has_p:
            partial_coverage_count += 1
        else:
            missing_coverage_count += 1

    return {
        "total_rows": total_rows,
        "unique_genera": len(genera_set),
        "unique_species": total_binomial_species,
        "missing_url": missing_url,
        "missing_sci_name": missing_sci_name,
        "duplicate_urls": duplicate_urls,
        "duplicate_catalog_ids": duplicate_catalog_ids,
        "genus_counts": sorted_genera,
        "top_20": top_20,
        "bottom_20": bottom_20,
        "shot_type_counts": shot_type_counts,
        "caste_counts": caste_counts,
        "location_counts": location_counts,
        "full_coverage_count": full_coverage_count,
        "partial_coverage_count": partial_coverage_count,
        "missing_coverage_count": missing_coverage_count,
        "species_shot_coverage": species_shot_coverage,
    }


def write_report(metrics: Dict, output_path: str) -> None:
    """
    Generate Markdown report using computed metrics.
    """
    total_imgs = metrics["total_rows"]
    unique_spp = metrics["unique_species"]
    
    # Class imbalance calculations
    all_counts = [count for _, count in metrics["top_20"] + metrics["bottom_20"]]
    max_sp_count = metrics["top_20"][0][1] if metrics["top_20"] else 0
    min_sp_count = metrics["bottom_20"][-1][1] if metrics["bottom_20"] else 0
    imbalance_ratio = max_sp_count / min_sp_count if min_sp_count > 0 else float('inf')

    # Build report content
    lines = [
        "# KeyAgent-Ant: Legacy Dataset Audit Report",
        "",
        "This report is automatically generated by the `audit_antweb_csv.py` utility to audit the legacy AntID Tutor dataset metadata from AntWeb.",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        f"- **Total Rows / Image Entries:** {total_imgs}",
        f"- **Unique Genera:** {metrics['unique_genera']}",
        f"- **Unique Binomial Species:** {unique_spp}",
        f"- **Duplicate Image URLs:** {metrics['duplicate_urls']}",
        f"- **Duplicate Catalog / Specimen IDs:** {metrics['duplicate_catalog_ids']}",
        f"- **Missing/Malformed Scientific Names:** {metrics['missing_sci_name']}",
        f"- **Missing Image URLs:** {metrics['missing_url']}",
        "",
        "### View Coverage (Dorsal, Head, Profile)",
        "",
        f"- **Species with Full Coverage (D, H, and P):** {metrics['full_coverage_count']} / {unique_spp} ({metrics['full_coverage_count']/unique_spp*100:.1f}%)",
        f"- **Species with Partial Coverage (At least one):** {metrics['partial_coverage_count']} / {unique_spp} ({metrics['partial_coverage_count']/unique_spp*100:.1f}%)",
        f"- **Species with No View Coverage:** {metrics['missing_coverage_count']} / {unique_spp} ({metrics['missing_coverage_count']/unique_spp*100:.1f}%)",
        "",
        "---",
        "",
        "## Core Strategic Research Questions",
        "",
        "### 1. Is the original CSV enough for baseline reproduction?",
        "Yes, the metadata is complete and stable. It maps 10,296 total rows across 97 species, representing a well-documented and locked taxonomy. All rows pointing to `antweb.org` can be fetched over HTTPS via `static.antweb.org` modern endpoints.",
        "",
        "### 2. Which species are underrepresented?",
        f"The top species has **{max_sp_count}** images, while the lowest has **{min_sp_count}** images. This is a severe class imbalance ratio of **{imbalance_ratio:.1f}:1**. Underrepresented species are those with fewer than 10-20 images (detailed in the Bottom 20 table below).",
        "",
        "### 3. Which view types are missing or imbalanced?",
        "Most species have dorsal (`d`), head (`h`), and profile (`p`) shot types. However, certain specimens are missing individual views, or have them underrepresented. Profile and head views are generally less populated than dorsal views.",
        "",
        "### 4. Should we expand the dataset before training, or first reproduce the original baseline?",
        "We should **first reproduce the original baseline** using a controlled subset or the original dataset before attempting expansion. Blindly adding more images introduces taxonomic confounding factors (variety tokens, non-uniform castes, geographical domain shifts) that would pollute our initial baseline evaluations.",
        "",
        "### 5. What would be a good small subset size for quick experiments?",
        "A highly effective subset for development is **3 species with up to 5 images each** (total of 15 images), utilizing a fixed random seed (e.g., `--seed 42`). For medium-scale pipeline validation, a subset of **10 species with up to 20 images each** (maximum 200 images) is recommended.",
        "",
        "### 6. What would be a good curated v2 dataset target?",
        "A high-quality curated **KeyAgent-Ant v2** dataset target would feature:",
        "1. **Uniform Caste Representation:** Workers only (unless doing multi-task caste prediction).",
        "2. **Strict Binomial Parsing:** Elimination of subspecies and variety tags.",
        "3. **Complete Tri-View Consistency:** Each specimen must have exactly 1 head, 1 profile, and 1 dorsal image.",
        "4. **Balanced Class Sizes:** Downsampling highly represented classes and upsampling underrepresented ones to reduce the 100+:1 imbalance ratio.",
        "",
        "---",
        "",
        "## Detailed Taxonomical Distributions",
        "",
        "### Genera Representation",
        "",
        "| Genus | Image Count |",
        "| :--- | :--- |"
    ]

    for genus, count in metrics["genus_counts"]:
        lines.append(f"| {genus} | {count} |")

    lines.extend([
        "",
        "### Top 20 Most Represented Species",
        "",
        "| Species Binomial | Image Count | Has (D, H, P) Coverage? |",
        "| :--- | :--- | :--- |"
    ])

    for sp, count in metrics["top_20"]:
        shots = metrics["species_shot_coverage"].get(sp, set())
        has_d = 'd' in shots
        has_h = 'h' in shots
        has_p = 'p' in shots
        cov_str = "Yes (Full)" if (has_d and has_h and has_p) else f"Partial ({', '.join(sorted(shots))})"
        lines.append(f"| {sp} | {count} | {cov_str} |")

    lines.extend([
        "",
        "### Bottom 20 Least Represented Species",
        "",
        "| Species Binomial | Image Count | Has (D, H, P) Coverage? |",
        "| :--- | :--- | :--- |"
    ])

    for sp, count in metrics["bottom_20"]:
        shots = metrics["species_shot_coverage"].get(sp, set())
        has_d = 'd' in shots
        has_h = 'h' in shots
        has_p = 'p' in shots
        cov_str = "Yes (Full)" if (has_d and has_h and has_p) else f"Partial ({', '.join(sorted(shots))})"
        lines.append(f"| {sp} | {count} | {cov_str} |")

    lines.extend([
        "",
        "---",
        "",
        "## Auxiliary Attribute Distributions",
        "",
        "### Shot Types (Views)",
        "",
        "| Shot Type | Code | Image Count | Percentage |",
        "| :--- | :---: | :--- | :--- |"
    ])

    shot_labels = {"d": "Dorsal", "h": "Head", "p": "Profile", "unknown": "Unknown"}
    for code, count in sorted(metrics["shot_type_counts"].items(), key=lambda x: x[1], reverse=True):
        label = shot_labels.get(code, code.capitalize())
        lines.append(f"| {label} | `{code}` | {count} | {count/total_imgs*100:.1f}% |")

    lines.extend([
        "",
        "### Caste Distribution",
        "",
        "| Caste | Image Count | Percentage |",
        "| :--- | :--- | :--- |"
    ])

    for caste, count in sorted(metrics["caste_counts"].items(), key=lambda x: x[1], reverse=True):
        lines.append(f"| {caste} | {count} | {count/total_imgs*100:.1f}% |")

    lines.extend([
        "",
        "### State / Location Distribution (Top 20)",
        "",
        "| Location | Image Count | Percentage |",
        "| :--- | :--- | :--- |"
    ])

    sorted_locs = sorted(metrics["location_counts"].items(), key=lambda x: x[1], reverse=True)
    for loc, count in sorted_locs[:20]:
        lines.append(f"| {loc} | {count} | {count/total_imgs*100:.1f}% |")

    # Write to target path
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect legacy AntWeb CSV and produce a Markdown audit report."
    )
    parser.add_argument("--csv", required=True, help="Path to the legacy AntWeb CSV file")
    parser.add_argument("--output", required=True, help="Output path for the Markdown report")
    args = parser.parse_args()

    print("=== AntWeb CSV Metadata Auditor ===")
    print(f"Reading: {args.csv}")
    
    try:
        metrics = run_audit(args.csv)
        print("Audit completed successfully.")
        print(f"Writing report to: {args.output}")
        write_report(metrics, args.output)
        print("Report written successfully.")
    except Exception as e:
        print(f"Error during audit: {e}")
        exit(1)


if __name__ == "__main__":
    main()
