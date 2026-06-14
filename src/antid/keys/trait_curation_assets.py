"""Trait curation assets materialization module.

This module provides offline, deterministic retrieval and verification of image assets
for selected curation specimens by matching them against split datasets and downloading
them securely from original repositories.
"""

import os
import csv
import json
from pathlib import Path
import requests

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def update_url(url: str) -> str:
    """Ensures the URL uses HTTPS and points to static.antweb.org."""
    if not url:
        return ""
    new_url = url.replace("http://www.antweb.org/images/", "https://static.antweb.org/images/")
    new_url = new_url.replace("https://www.antweb.org/images/", "https://static.antweb.org/images/")
    return new_url


def materialize_trait_curation_images(
    selection_csv,
    split_dir,
    image_root=".",
    dry_run=True,
    overwrite=False,
    timeout_seconds=30
):
    """Downloads/materializes only the selected curation specimens' images.

    Matches each selected tri-view image against original split datasets to resolve
    their AntWeb URLs, and saves them locally under the correct image paths.

    Args:
        selection_csv: Path to the selected specimens CSV file.
        split_dir: Directory containing train.csv, val.csv, test.csv.
        image_root: The root directory for saving image files.
        dry_run: If True, do not download files; only report actions.
        overwrite: If True, overwrite existing files on disk.
        timeout_seconds: Request timeout in seconds.

    Returns:
        A dictionary containing JSON-serializable execution statistics and records.
    """
    summary = {
        "status": "success",
        "selected_specimens": 0,
        "requested_images": 0,
        "matched_images": 0,
        "downloaded_images": 0,
        "existing_images": 0,
        "skipped_images": 0,
        "unresolved_images": 0,
        "failed_downloads": 0,
        "records": []
    }

    # 1. Load selected specimens
    if not os.path.exists(selection_csv):
        summary["status"] = "error"
        raise FileNotFoundError(f"Selection CSV file not found: {selection_csv}")

    selected_rows = []
    with open(selection_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            selected_rows.append(row)

    summary["selected_specimens"] = len(selected_rows)

    # 2. Load split files
    split_rows = []
    split_files = ["train.csv", "val.csv", "test.csv"]
    for filename in split_files:
        filepath = os.path.join(split_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    split_rows.append(row)

    # 3. Index split rows for fast lookup
    split_by_path = {}
    split_by_spec_view = {}
    split_by_cat_view = {}

    for s_row in split_rows:
        path = s_row.get("image_path", "").strip()
        if path:
            split_by_path[path] = s_row

        spec_id = s_row.get("specimen_id", "").strip()
        cat_num = s_row.get("catalog_number", "").strip()
        view = s_row.get("view_type", "").strip().lower()

        if spec_id and view:
            split_by_spec_view[(spec_id, view)] = s_row
        if cat_num and view:
            split_by_cat_view[(cat_num, view)] = s_row

    # 4. Match and process each selected specimen's views
    views_to_process = ["dorsal", "head", "profile"]
    headers = {"User-Agent": "KeyAgent-Ant/1.0 (Asset Materializer)"}

    for spec in selected_rows:
        spec_id = spec.get("specimen_id", "").strip()
        cat_num = spec.get("catalog_number", "").strip()
        kb_taxon_id = spec.get("kb_taxon_id", "").strip()

        for view in views_to_process:
            image_path = spec.get(f"{view}_image_path", "").strip()
            image_id = spec.get(f"{view}_image_id", "").strip()

            if not image_path:
                continue

            summary["requested_images"] += 1

            # Match against split rows
            matched_row = None
            if image_path in split_by_path:
                matched_row = split_by_path[image_path]
            elif spec_id and (spec_id, view) in split_by_spec_view:
                matched_row = split_by_spec_view[(spec_id, view)]
            elif cat_num and (cat_num, view) in split_by_cat_view:
                matched_row = split_by_cat_view[(cat_num, view)]

            # Build initial record
            record = {
                "specimen_id": spec_id,
                "catalog_number": cat_num,
                "kb_taxon_id": kb_taxon_id,
                "view_type": view,
                "image_id": image_id,
                "image_path": image_path,
                "source_url": None,
                "destination_path": os.path.join(image_root, image_path),
                "action": "unresolved",
                "status": "unresolved",
                "width": None,
                "height": None,
                "error": None
            }

            if not matched_row:
                summary["unresolved_images"] += 1
                record["error"] = "No matching split dataset record found."
                summary["records"].append(record)
                continue

            summary["matched_images"] += 1

            # Resolve URL
            raw_url = matched_row.get("image_url", "").strip() or matched_row.get("source_url", "").strip()
            if not raw_url or not raw_url.startswith("http"):
                summary["unresolved_images"] += 1
                record["error"] = "Matching split record contains no downloadable URL."
                summary["records"].append(record)
                continue

            resolved_url = update_url(raw_url)
            record["source_url"] = resolved_url

            # Destination check
            dest_full_path = record["destination_path"]
            file_exists = os.path.exists(dest_full_path)

            if file_exists:
                summary["existing_images"] += 1

            if file_exists and not overwrite:
                record["action"] = "skip_existing"
                record["status"] = "skipped"
                summary["skipped_images"] += 1

                # If image exists and Pillow is available, check dimensions
                if HAS_PIL:
                    try:
                        with Image.open(dest_full_path) as img:
                            record["width"], record["height"] = img.size
                    except Exception as e:
                        record["error"] = f"Failed to read existing image dimensions: {e}"
                
                summary["records"].append(record)
                continue

            # Handle Dry-Run Mode
            if dry_run:
                record["action"] = "dry_run_download"
                record["status"] = "success"
                summary["records"].append(record)
                continue

            # Real Run Download
            dest_dir = os.path.dirname(dest_full_path)
            if dest_dir:
                os.makedirs(dest_dir, exist_ok=True)

            try:
                response = requests.get(resolved_url, headers=headers, timeout=timeout_seconds, allow_redirects=True)
                if response.status_code == 200:
                    with open(dest_full_path, "wb") as f:
                        f.write(response.content)

                    record["action"] = "download"
                    record["status"] = "success"
                    summary["downloaded_images"] += 1

                    # Verify image and record dimensions
                    if HAS_PIL:
                        try:
                            with Image.open(dest_full_path) as img:
                                record["width"], record["height"] = img.size
                        except Exception as e:
                            record["error"] = f"Saved file is unreadable by PIL: {e}"
                else:
                    record["action"] = "download"
                    record["status"] = "failed"
                    record["error"] = f"HTTP Error {response.status_code}"
                    summary["failed_downloads"] += 1
            except Exception as e:
                record["action"] = "download"
                record["status"] = "failed"
                record["error"] = str(e)
                summary["failed_downloads"] += 1

            summary["records"].append(record)

    return summary
