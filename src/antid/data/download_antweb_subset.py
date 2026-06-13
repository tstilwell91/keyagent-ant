#!/usr/bin/env python3
"""
download_antweb_subset.py

A safe, configurable, limited downloader workflow that reads the legacy AntWeb CSV,
optionally performs a dry run, and downloads a small reproducible subset of images.
"""

import os
import re
import csv
import random
import hashlib
import argparse
import requests
from typing import List, Dict, Tuple, Optional

# Constants
DEFAULT_TIMEOUT = 10.0
DEFAULT_USER_AGENT = "KeyAgent-Ant/1.0 (Subset Downloader)"

def parse_scientific_name(scientific_name: str) -> Tuple[str, str, str]:
    """
    Parse a scientific name into genus, species, and folder name.
    
    Inputs may include values like:
    - Camponotus pennsylvanicus
    - amblyopone_australis
    - Solenopsis invicta
    
    If the name contains variety, authorship, or subspecies descriptors, only the
    first two binomial tokens are preserved.
    
    Output produces:
    - genus (Capitalized)
    - species (lowercased)
    - folder_name (genus_species in lowercase)
    """
    if not scientific_name:
        raise ValueError("Scientific name cannot be empty")
        
    # Split by whitespace or underscores
    tokens = [t for t in re.split(r'[_\s]+', scientific_name.strip()) if t]
    if len(tokens) < 2:
        raise ValueError(
            f"Scientific name '{scientific_name}' must have at least two tokens (genus and species)"
        )
        
    genus = tokens[0].capitalize()
    species = tokens[1].lower()
    folder_name = f"{genus.lower()}_{species.lower()}"
    return genus, species, folder_name


def generate_filename(url: str, catalog_number: Optional[str], shot_type: Optional[str], index: int) -> str:
    """
    Generate a formatted image filename preserving useful metadata.
    
    Preferred pattern:
    <catalog_number>*<shot_type>*<index>.<ext>
    
    If catalog_number is unavailable, use a deterministic SHA-256 hash prefix.
    If shot_type is unavailable, use 'unknown'.
    Infer image extension from URL path, defaulting to .jpg.
    """
    # 1. Catalog number
    cat_num = catalog_number.strip() if catalog_number else ""
    if not cat_num:
        # Fallback to deterministic SHA-256 hash of URL
        url_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()[:10]
        cat_num = f"hash{url_hash}"
        
    # 2. Shot type
    s_type = shot_type.strip().lower() if shot_type else ""
    if not s_type:
        s_type = "unknown"
        
    # 3. Extension
    parsed_path = url.split("?")[0]
    ext = os.path.splitext(parsed_path)[1].lower()
    if not ext or ext not in ['.jpg', '.jpeg', '.png', '.gif']:
        ext = ".jpg"
        
    return f"{cat_num}*{s_type}*{index}{ext}"


def update_url(url: str) -> str:
    """
    Ensure the URL uses HTTPS and points to static.antweb.org modern static server.
    """
    if not url:
        return ""
    new_url = url.replace("http://www.antweb.org/images/", "https://static.antweb.org/images/")
    new_url = new_url.replace("https://www.antweb.org/images/", "https://static.antweb.org/images/")
    return new_url


def filter_and_sample_rows(
    rows: List[Dict[str, str]],
    seed: int,
    species_limit: Optional[int] = None,
    per_species_limit: Optional[int] = None,
    limit: Optional[int] = None,
    shot_type_filter: Optional[str] = None,
    caste_filter: Optional[str] = None
) -> List[Tuple[Dict[str, str], str, str, str]]:
    """
    Filter and sample rows deterministically based on seed and limits.
    
    Returns a list of tuples: (row_dict, genus, species, folder_name)
    """
    # Step 1: Pre-filter and parse names
    candidates = []
    for row in rows:
        url = row.get("image_url", "").strip()
        sci_name = row.get("scientific_name", "").strip()
        if not url or not sci_name:
            continue
            
        # Optional filters
        if shot_type_filter:
            row_shot = row.get("shot_type", "").strip().lower()
            if row_shot != shot_type_filter.strip().lower():
                continue
                
        if caste_filter:
            row_caste = row.get("caste", "").strip().lower()
            row_caste_big = row.get("caste_big", "").strip().lower()
            target_caste = caste_filter.strip().lower()
            if target_caste != row_caste and target_caste != row_caste_big:
                continue
                
        try:
            genus, species, folder_name = parse_scientific_name(sci_name)
            candidates.append((row, genus, species, folder_name))
        except ValueError:
            # Skip rows with malformed scientific names
            continue

    if not candidates:
        return []

    # Step 2: Group by species folder name
    by_species = {}
    for item in candidates:
        folder_name = item[3]
        if folder_name not in by_species:
            by_species[folder_name] = []
        by_species[folder_name].append(item)

    # Step 3: Sample species list alphabetically + seed shuffle
    unique_species = sorted(list(by_species.keys()))
    
    rng = random.Random(seed)
    # Copy list before shuffling to avoid side effects
    shuffled_species = list(unique_species)
    rng.shuffle(shuffled_species)
    
    if species_limit is not None and species_limit > 0:
        selected_species = shuffled_species[:species_limit]
    else:
        selected_species = shuffled_species

    # Step 4: Sample rows within each selected species
    sampled_rows = []
    for sp_folder in selected_species:
        sp_items = by_species[sp_folder]
        # Sort by image_url to ensure stable alphabetical order before shuffling
        sp_items_sorted = sorted(sp_items, key=lambda x: x[0].get("image_url", ""))
        
        # Shuffle deterministically
        rng_sp = random.Random(seed)
        shuffled_items = list(sp_items_sorted)
        rng_sp.shuffle(shuffled_items)
        
        if per_species_limit is not None and per_species_limit > 0:
            sp_sampled = shuffled_items[:per_species_limit]
        else:
            sp_sampled = shuffled_items
            
        sampled_rows.extend(sp_sampled)

    # Step 5: Overall limit application
    # Sort combined rows to establish absolute baseline stability
    sampled_rows_sorted = sorted(sampled_rows, key=lambda x: (x[3], x[0].get("image_url", "")))
    
    rng_all = random.Random(seed)
    shuffled_all = list(sampled_rows_sorted)
    rng_all.shuffle(shuffled_all)
    
    if limit is not None and limit > 0:
        final_selection = shuffled_all[:limit]
    else:
        final_selection = shuffled_all

    return final_selection


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Controlled, deterministic downloader for AntWeb image subsets."
    )
    parser.add_argument("--csv", required=True, help="Path to the legacy AntWeb CSV file")
    parser.add_argument("--output-dir", required=True, help="Output directory to save downloaded images")
    parser.add_argument("--limit", type=int, help="Total maximum number of images to download")
    parser.add_argument("--species-limit", type=int, help="Maximum number of unique species to select")
    parser.add_argument("--per-species-limit", type=int, help="Maximum number of images per selected species")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without downloading files")
    parser.add_argument("--seed", type=int, default=42, help="Seed for deterministic sampling (default: 42)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing image files")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help=f"Timeout in seconds for HTTP requests (default: {DEFAULT_TIMEOUT})")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="User-Agent header for requests")
    parser.add_argument("--shot-type", help="Filter by shot type (e.g. 'h', 'p', 'd')")
    parser.add_argument("--caste", help="Filter by caste (e.g. 'worker', 'queen', 'male')")

    args = parser.parse_args()

    # Read the CSV file
    if not os.path.exists(args.csv):
        print(f"Error: CSV file not found at {args.csv}")
        exit(1)

    print("=== AntWeb Subset Downloader ===")
    print(f"Reading CSV: {args.csv}")
    
    rows = []
    # Open CSV file expecting semicolon delimiter
    try:
        with open(args.csv, newline="", encoding="utf-8") as csvfile:
            # We first verify that delimiter and headers are present
            first_line = csvfile.readline()
            csvfile.seek(0)
            
            # Simple check to see if semicolon is the delimiter
            delimiter = ";" if ";" in first_line else ","
            
            reader = csv.DictReader(csvfile, delimiter=delimiter)
            
            # Fail clearly on missing required columns
            required_cols = ["scientific_name", "image_url"]
            missing_cols = [col for col in required_cols if col not in reader.fieldnames] if reader.fieldnames else required_cols
            if missing_cols:
                raise ValueError(f"Missing required columns in CSV: {', '.join(missing_cols)}")
                
            for row in reader:
                rows.append(row)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        exit(1)

    print(f"Total rows in CSV: {len(rows)}")

    # Apply deterministic sampling
    selection = filter_and_sample_rows(
        rows=rows,
        seed=args.seed,
        species_limit=args.species_limit,
        per_species_limit=args.per_species_limit,
        limit=args.limit,
        shot_type_filter=args.shot_type,
        caste_filter=args.caste
    )

    if not selection:
        print("No matching rows found after applying filters and sampling.")
        return

    # Track indexes for naming
    species_counts = {}
    planned_downloads = []
    
    # Sort selection by species folder name to ensure alphabetical directory ordering during execution
    selection_ordered = sorted(selection, key=lambda x: (x[3], x[0].get("image_url", "")))

    for row_dict, genus, species, folder_name in selection_ordered:
        url = update_url(row_dict.get("image_url", ""))
        catalog_number = row_dict.get("catalog_number")
        shot_type = row_dict.get("shot_type")
        
        # 1-based index per species binomial
        species_counts[folder_name] = species_counts.get(folder_name, 0) + 1
        idx = species_counts[folder_name]
        
        filename = generate_filename(url, catalog_number, shot_type, idx)
        dest_path = os.path.join(args.output_dir, folder_name, filename)
        
        planned_downloads.append({
            "url": url,
            "dest_path": dest_path,
            "folder_name": folder_name,
            "filename": filename,
            "genus": genus,
            "species": species,
            "shot_type": shot_type or "unknown"
        })

    # Summary Statistics
    unique_planned_species = sorted(list(set(p["folder_name"] for p in planned_downloads)))
    unique_planned_genera = sorted(list(set(p["genus"] for p in planned_downloads)))
    
    shot_type_counts = {}
    for p in planned_downloads:
        st = p["shot_type"]
        shot_type_counts[st] = shot_type_counts.get(st, 0) + 1

    print("\n=== Planning Summary ===")
    print(f"Target directory: {args.output_dir}")
    print(f"Unique Genus Count: {len(unique_planned_genera)} ({', '.join(unique_planned_genera)})")
    print(f"Unique Species Count: {len(unique_planned_species)}")
    print("Counts by Shot Type:")
    for st, count in sorted(shot_type_counts.items()):
        print(f"  - {st}: {count}")
    print(f"Total planned downloads: {len(planned_downloads)}")
    print("========================\n")

    if args.dry_run:
        print("--- DRY RUN MODE (No downloads performed) ---")
        for i, p in enumerate(planned_downloads[:15], 1):
            print(f"[{i}] URL: {p['url']}")
            print(f"    Path: {p['dest_path']}")
        if len(planned_downloads) > 15:
            print(f"... and {len(planned_downloads) - 15} more planned downloads.")
        print("\nDry run completed successfully.")
        return

    # Real Run
    print("Starting download process...")
    headers = {"User-Agent": args.user_agent}
    success_count = 0
    skip_count = 0
    fail_count = 0

    for i, p in enumerate(planned_downloads, 1):
        target_path = p["dest_path"]
        target_dir = os.path.dirname(target_path)
        
        # Check overwrite
        if os.path.exists(target_path) and not args.overwrite:
            print(f"[{i}/{len(planned_downloads)}] Skipping existing file: {target_path}")
            skip_count += 1
            continue
            
        # Ensure parent folder exists
        os.makedirs(target_dir, exist_ok=True)
        
        print(f"[{i}/{len(planned_downloads)}] Downloading: {p['url']}")
        try:
            response = requests.get(p["url"], headers=headers, timeout=args.timeout, allow_redirects=True)
            if response.status_code == 200:
                with open(target_path, "wb") as f:
                    f.write(response.content)
                print(f"  ✓ Saved to: {target_path}")
                success_count += 1
            else:
                print(f"  ✗ Failed: HTTP {response.status_code}")
                fail_count += 1
        except Exception as e:
            print(f"  ✗ Error downloading {p['url']}: {e}")
            fail_count += 1

    print("\n=== Download Execution Summary ===")
    print(f"Successfully downloaded: {success_count}")
    print(f"Skipped (already existed): {skip_count}")
    print(f"Failed to download: {fail_count}")
    print("===================================\n")


if __name__ == "__main__":
    main()
