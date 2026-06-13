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

---

## 7. Real-World & Legacy Dataset Integration

### Legacy Downloader Output Format
The legacy project downloader scripts (`downloader/download-medium.py` and `download-high.py`) fetch images from AntWeb according to `downloader/Sup_top97species_Qmed_def_info.csv` and write them into:
`training_data/<genus>_<species>/`

Because these folders are named as `<genus>_<species>`, they are 100% compatible with this manifest pipeline. To index them, you can point `--image-root` directly to the `training_data` folder on disk:
```bash
PYTHONPATH=src python3 -m antid.data.build_manifest \
    --image-root training_data \
    --output data/processed/manifest.csv
```

### Note on `specimen-imaging/` Sample Folder
The `specimen-imaging/` directory contains sample images organized in a flat structure (`specimen-imaging/<genus>-<species>.<ext>`) rather than taxonomic subdirectories. This flat layout is **not** suitable for direct automatic scanning by `build_manifest.py`. 

To process these files with the manifest pipeline, you must copy or soft-link them into taxonomic subdirectories (e.g. `scratch/smoke_images/Camponotus_pennsylvanicus/`) or use the `--fallback-genus` and `--fallback-species` flags if indexing single-species subsets.


---

## 8. Controlled Real-Data Subset Download

### Why We Do Not Run the Full Legacy Downloader by Default
The legacy downloader scripts (`download-medium.py` and `download-high.py`) do not support limit constraints, dry runs, filtering, or deterministic seeding. By default, they attempt to download **all 10,296 images** sequentially. This can easily get your IP address rate-limited or blocked by AntWeb's servers, consumes substantial bandwidth/disk storage, and leads to messy, untracked directory populations.

### Why Ctrl+C Cancellation Is Not Reproducible
A legacy workflow recommendation suggested manually starting the full downloader script and terminating it via `Ctrl+C` after 20–30 images. This is **strongly discouraged** because:
1. **Lack of Reproducibility:** The set of downloaded images will depend purely on network latency, connection speeds, and manual timing, making subsequent experiments completely non-reproducible.
2. **Incomplete Transactions:** Interrupting active file streams can leave corrupted, partially downloaded images on disk.
3. **Imbalanced Representation:** Since the CSV is sorted alphabetically, a partial download will only contain species starting with "A" (such as `Amblyopone australis`), completely failing to test multiclass split and validation layers on other genera.

### How to Audit the Legacy CSV Before Downloading
Always inspect the metadata characteristics first to understand the data distribution. The audit utility aggregates taxonomical and attribute counts without performing any live network downloads:
```bash
PYTHONPATH=src python -m antid.data.audit_antweb_csv \
    --csv downloader/Sup_top97species_Qmed_def_info.csv \
    --output docs/dataset_audit_antweb.md
```

### How to Run Dry-Run Mode
A dry run allows you to plan the subset, review target file paths, and inspect sampling statistics without writing files to disk:
```bash
PYTHONPATH=src python -m antid.data.download_antweb_subset \
    --csv downloader/Sup_top97species_Qmed_def_info.csv \
    --output-dir data/raw/antweb_subset \
    --species-limit 3 \
    --per-species-limit 5 \
    --seed 42 \
    --dry-run
```

### How to Download a Tiny Subset
Once verified, run the script without `--dry-run` to execute a fast, safe, and fully reproducible download:
```bash
PYTHONPATH=src python -m antid.data.download_antweb_subset \
    --csv downloader/Sup_top97species_Qmed_def_info.csv \
    --output-dir data/raw/antweb_subset \
    --species-limit 3 \
    --per-species-limit 5 \
    --seed 42
```

### How to Build a Manifest from a Subset
Index the subset using our manifest tool:
```bash
PYTHONPATH=src python -m antid.data.build_manifest \
    --image-root data/raw/antweb_subset \
    --output data/processed/antweb_subset_manifest.csv
```

### How to Validate It
Validate the integrity and layout of your subset manifest:
```bash
PYTHONPATH=src python -m antid.data.validate_dataset \
    --manifest data/processed/antweb_subset_manifest.csv \
    --image-root data/raw/antweb_subset
```

### How to Build Splits
Construct train/val/test splits using our stratified splitter. Because our subset has small class sizes, we add `--allow-unstratified` to fallback safely:
```bash
PYTHONPATH=src python -m antid.data.build_splits \
    --manifest data/processed/antweb_subset_manifest.csv \
    --output-dir data/splits/antweb_subset \
    --target species \
    --seed 42 \
    --allow-unstratified
```


---

## 9. Dataset Variants & Specimen-Aware Splitting

To support reproducible training and robust evaluation, KeyAgent-Ant implements three dataset variant manifests and specimen-aware split configurations.

### The Dataset Variants

1. **Dataset v1-original** (`v1_original_manifest.csv`):
   - **Scope:** All 97 species, 10,211 valid rows.
   - **Properties:** Unfiltered caste (workers, queens, males) and uncapped.
   - **Purpose:** Establishing baseline reproduction performance matching the legacy unstructured training designs.

2. **Dataset v1-specimen-aware** (`v1_specimen_aware_manifest.csv`):
   - **Scope:** Identical to v1-original (10,211 rows).
   - **Properties:** Same images and labels as v1-original, but explicitly formatted for specimen-level grouped partitioning.
   - **Purpose:** Used to benchmark and isolate the exact "specimen leakage generalization gap" under identical legacy data scope.

3. **Dataset v2-curated** (`v2_curated_manifest.csv`):
   - **Scope:** 97 species, exactly **2,331 physical specimens** (yielding **6,993 images**).
   - **Properties:** Workers caste only, strict tri-view complete specimens (exactly 1 dorsal, 1 head, 1 profile per specimen), capped at a maximum of 30 complete specimens per species.
   - **Purpose:** Eliminates caste-level morphological noise, balances classes (reduces class imbalance from 12.44:1 to 2.50:1), and serves as the core training dataset for generalization tests.

---

### Why Specimen-Aware Splitting Matters

Standard image-level random splits (e.g., placing images of the same physical specimen across both train and test splits) cause severe **specimen leakage**. 

#### The Memorization Overestimation Risk
Because multiple high-resolution images are taken of the same unique physical specimen, they share identical background dust, mounting pin shapes, illumination angles, and camera-sensor noise. When an image-level split is used, the neural network easily "memorizes" these non-biological specimen tokens, achieving artificial 95%+ validation accuracy. 

However, when tested in the field on *unseen* specimens, the model's accuracy dramatically collapses. Specimen-aware splitting prevents this leakage by ensuring **no unique physical specimen ID appears in more than one partition** (i.e., all three views—dorsal, head, profile—of specimen `CASENT0102148` are strictly grouped together and placed in a single split).

---

### How to Run the Dataset Variant Builder & Splits

To generate all three manifests, validate their schemas, build the train/val/test partitions, and run split specimen leakage validation:

```bash
PYTHONPATH=src .venv/bin/python -m antid.data.build_dataset_variants \
    --csv downloader/Sup_top97species_Qmed_def_info.csv \
    --run-splits
```

This command automatically outputs:

- **Manifests:**
  - `data/processed/v1_original_manifest.csv`
  - `data/processed/v1_specimen_aware_manifest.csv`
  - `data/processed/v2_curated_manifest.csv`
- **Partitions:**
  - `data/splits/v1_original/` (image-level random split)
  - `data/splits/v1_specimen_aware/` (specimen-level grouped split)
  - `data/splits/v2_curated/` (specimen-level grouped split)

All generated partitions automatically undergo strict specimen leakage validation checks to guarantee zero specimen overlap between train, validation, and test splits.



