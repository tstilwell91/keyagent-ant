# KeyAgent-Ant Dataset Preparation Pipeline

This document describes the design, execution, and structure of the dataset preparation pipeline for **KeyAgent-Ant**.

---

## 1. Purpose of the Manifest

The dataset manifest serves as a clean, unified, and research-ready registry of all available images and their metadata. By compiling all images into a single manifest CSV, we:
- Decouple model training and data loading from specific filesystem structures.
- Map taxonomic textual identifiers (`genus` and `species`) to deterministic, zero-indexed numerical labels (`label_genus_id` and `label_species_id`).
- Enable global, repeatable dataset validation, filtering, and splitting.

---

## 2. Expected CSV Columns

The generated manifest (`data/processed/manifest.csv` by default) contains the following schema:

| Column Name | Type | Description |
| :--- | :--- | :--- |
| `image_path` | `str` | Path to the image file on the local disk (relative to `image_root` by default, or absolute resolved path if `--absolute-paths` is specified). |
| `genus` | `str` | Cleaned, capitalized genus name (e.g. `Camponotus`). |
| `species` | `str` | Cleaned, lowercased species epithet (e.g. `pennsylvanicus`). |
| `label_genus_id` | `int` | Deterministic, zero-indexed unique ID assigned alphabetically to the genus. |
| `label_species_id` | `int` | Deterministic, zero-indexed unique ID assigned alphabetically to the species binomial. |
| `view_type` | `str` | Detected specimen camera view: `dorsal`, `head`, `profile`, or `unknown`. |
| `source_url` | `str` | Source URL of the image, if available (defaults to empty string `""`). |
| `specimen_id` | `str` | Unique specimen identifier (e.g. `CASENT0123456`) parsed from the filename. |
| `image_quality_flag`| `str` | Quality assessment flag. Defaults to `unchecked`. |

---

## 3. Expected Image Folder Assumptions

The pipeline is highly flexible and recursively scans directories. It automatically infers the `genus` and `species` of an image from its folder structure:
1. **Combined Folder Name Delimiters:** If the direct parent directory contains delimiters like `_` or `-` (e.g. `/path/to/images/Camponotus_pennsylvanicus/img.jpg`), it splits by the first delimiter to extract `genus` (`Camponotus`) and `species` (`pennsylvanicus`).
2. **Nested Directories:** If the folder structure is organized hierarchically as `genus/species` (e.g. `/path/to/images/Camponotus/pennsylvanicus/img.jpg`), it extracts the grandparent directory as `genus` and the parent directory as `species`.
3. **Optional Fallbacks:** If the folder structure does not yield both genus and species, you can specify default/fallback tags using CLI flags.

### Supported Image Formats
The pipeline scans for and processes files with the following extensions (case-insensitive):
- `.jpg` / `.jpeg`
- `.png`
- `.tif` / `.tiff`
- `.webp`

---

## 4. How View Detection Works

AntWeb-style images typically contain view indicators within their filenames. The `detect_view_type` function checks the lowercased filename for specific deterministic patterns and returns:
- **`dorsal`**: if the name contains `_d_`, `-d-`, `_d.`, or `"dorsal"`.
- **`head`**: if the name contains `_h_`, `-h-`, `_h.`, or `"head"`.
- **`profile`**: if the name contains `_p_`, `-p-`, `_p.`, `"profile"`, or `"lateral"`.
- **`unknown`**: if none of the above are matched.

---

## 5. Usage Guide & Example Commands

All commands should be executed from the repository root with the `PYTHONPATH=src` prefix, or after adding `src/` to your environment path.

### Step A: Build the Manifest
Scan your raw image directory and generate the main manifest CSV. By default, paths are written relative to the specified `--image-root`.
```bash
PYTHONPATH=src python3 -m antid.data.build_manifest \
    --image-root /path/to/images \
    --output data/processed/manifest.csv
```
*Optional Absolute Paths:* To write absolute resolved paths into the CSV instead of relative paths:
```bash
PYTHONPATH=src python3 -m antid.data.build_manifest \
    --image-root /path/to/images \
    --output data/processed/manifest.csv \
    --absolute-paths
```
*Optional Fallbacks:* If some folders cannot be resolved automatically:
```bash
PYTHONPATH=src python3 -m antid.data.build_manifest \
    --image-root /path/to/images \
    --output data/processed/manifest.csv \
    --fallback-genus UnknownGenus \
    --fallback-species unknown
```

### Step B: Validate the Dataset
Run structural and logical validation checks to verify that the manifest matches the files on disk and is completely consistent:
```bash
PYTHONPATH=src python3 -m antid.data.validate_dataset \
    --manifest data/processed/manifest.csv
```
If your manifest stores relative image paths, provide the image root to resolve them:
```bash
PYTHONPATH=src python3 -m antid.data.validate_dataset \
    --manifest data/processed/manifest.csv \
    --image-root /path/to/images
```

### Step C: Build Train/Val/Test Splits
Partition your dataset into reproducible splits (Train 70%, Val 15%, Test 15% by default) using stratified splitting:
```bash
PYTHONPATH=src python3 -m antid.data.build_splits \
    --manifest data/processed/manifest.csv \
    --output-dir data/splits \
    --target species \
    --seed 42
```
*Small Class Fallback:* If some species have fewer than 3 samples, standard stratification is mathematically impossible. Add the `--allow-unstratified` flag to perform best-effort split assignments for those small classes:
```bash
PYTHONPATH=src python3 -m antid.data.build_splits \
    --manifest data/processed/manifest.csv \
    --output-dir data/splits \
    --target species \
    --seed 42 \
    --allow-unstratified
```

---

## 6. Known Limitations

- **Strict Path Validation:** The validator requires that every image listed in `image_path` exists on disk. Moving the dataset or mounting it to a different path will require rebuilding the manifest or specifying the correct `--image-root`.
- **Stratification Minimums:** Stratified splitting on a target requires at least 3 samples per class to ensure representation across all three sets (train, val, test).
