import argparse
import csv
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

# Set up logger
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def split_indices_stratified(
    rows: List[Dict],
    target: str,
    train_ratio: float,
    val_ratio: float,
    test_ratio: float,
    seed: int,
    allow_unstratified: bool,
) -> Tuple[List[int], List[int], List[int]]:
    """
    Splits dataset indices into train, val, and test using stratified sampling.

    Args:
        rows: List of dictionary rows from manifest.
        target: Column to stratify on ('genus' or 'species').
        train_ratio: Ratio of train split.
        val_ratio: Ratio of val split.
        test_ratio: Ratio of test split.
        seed: Random seed for reproducibility.
        allow_unstratified: If True, permits small classes (<3) to skip strict stratification.

    Returns:
        Tuple of (train_indices, val_indices, test_indices)
    """
    import random

    rng = random.Random(seed)

    # Group row indices by target class
    class_to_indices = defaultdict(list)
    for idx, row in enumerate(rows):
        if target == "species":
            # Stratify by full binomial to prevent collapsing shared species epithets across different genera
            val = f"{row['genus'].strip()} {row['species'].strip()}"
        else:
            val = row[target].strip()
        class_to_indices[val].append(idx)

    train_indices = []
    val_indices = []
    test_indices = []

    # Validate that all classes have enough samples for stratification
    small_classes = {cls: len(indices) for cls, indices in class_to_indices.items() if len(indices) < 3}
    if small_classes and not allow_unstratified:
        raise ValueError(
            f"Cannot stratify small classes: {list(small_classes.keys())}. "
            "Please use --allow-unstratified to allow best-effort splitting for small classes."
        )

    for cls, indices in sorted(class_to_indices.items()):
        # Shuffle indices for this class deterministically
        shuffled = list(indices)
        rng.shuffle(shuffled)

        N = len(shuffled)

        if N == 1:
            # N == 1 can only go to train
            c_train = shuffled
            c_val = []
            c_test = []
            logger.warning(
                f"Class '{cls}' has only 1 sample. It was allocated to train only."
            )
        elif N == 2:
            # N == 2 goes to train and val (documented choice)
            c_train = [shuffled[0]]
            c_val = [shuffled[1]]
            c_test = []
            logger.warning(
                f"Class '{cls}' has only 2 samples. It was allocated to train and val splits, leaving test empty."
            )
        else:
            # N >= 3: allocate at least 1 to each split, then distribute the remainder using discrepancy minimization
            n_train = 1
            n_val = 1
            n_test = 1

            t_train = N * train_ratio
            t_val = N * val_ratio
            t_test = N * test_ratio

            for _ in range(N - 3):
                diff_train = t_train - n_train
                diff_val = t_val - n_val
                diff_test = t_test - n_test

                # Increment the split with the maximum discrepancy (target - current)
                max_diff = max(diff_train, diff_val, diff_test)
                if max_diff == diff_train:
                    n_train += 1
                elif max_diff == diff_val:
                    n_val += 1
                else:
                    n_test += 1

            c_train = shuffled[:n_train]
            c_val = shuffled[n_train:n_train + n_val]
            c_test = shuffled[n_train + n_val:]

        train_indices.extend(c_train)
        val_indices.extend(c_val)
        test_indices.extend(c_test)

    return train_indices, val_indices, test_indices


def build_splits(
    manifest_path: str,
    output_dir: str,
    target: str,
    train_ratio: float,
    val_ratio: float,
    test_ratio: float,
    seed: int,
    allow_unstratified: bool,
) -> None:
    """Reads manifest, partitions data, and writes split CSV files."""
    manifest_file = Path(manifest_path)
    if not manifest_file.exists():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

    # Check ratios sum to 1.0 (with small floating point tolerance)
    total_ratio = train_ratio + val_ratio + test_ratio
    if abs(total_ratio - 1.0) > 1e-5:
        raise ValueError(f"Split ratios must sum to 1.0 (currently sum to {total_ratio})")

    # Read manifest
    rows = []
    with open(manifest_file, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames if reader.fieldnames else []
        for row in reader:
            rows.append(row)

    if not rows:
        raise ValueError("Cannot split an empty manifest.")

    if target not in ["genus", "species"]:
        raise ValueError(f"Target column must be 'genus' or 'species' (got '{target}')")

    # Perform stratified split
    logger.info(f"Splitting dataset of {len(rows)} samples stratified by '{target}' with seed {seed}...")
    train_idx, val_idx, test_idx = split_indices_stratified(
        rows, target, train_ratio, val_ratio, test_ratio, seed, allow_unstratified
    )

    # Sort indices so output is organized
    train_idx.sort()
    val_idx.sort()
    test_idx.sort()

    # Prepare outputs
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    splits_data = [
        ("train", train_idx, out_dir / "train.csv"),
        ("val", val_idx, out_dir / "val.csv"),
        ("test", test_idx, out_dir / "test.csv"),
    ]

    new_fieldnames = fieldnames + ["split"]

    # Write each split file
    for name, indices, file_path in splits_data:
        with open(file_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=new_fieldnames)
            writer.writeheader()
            for idx in indices:
                row_copy = dict(rows[idx])
                row_copy["split"] = name
                writer.writerow(row_copy)
        logger.info(f"  - Wrote {len(indices)} rows to {file_path}")

    # Write combined manifest with split column for convenience
    combined_path = out_dir / "manifest_with_splits.csv"
    with open(combined_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=new_fieldnames)
        writer.writeheader()

        # Combine all indices back with their splits
        all_indices_with_split = []
        for name, indices, _ in splits_data:
            for idx in indices:
                all_indices_with_split.append((idx, name))

        # Sort by original index to keep original manifest ordering
        all_indices_with_split.sort(key=lambda x: x[0])

        for idx, name in all_indices_with_split:
            row_copy = dict(rows[idx])
            row_copy["split"] = name
            writer.writerow(row_copy)

    logger.info(f"  - Wrote combined manifest to {combined_path}")
    logger.info("Split building completed successfully!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build train/val/test splits from manifest.")
    parser.add_argument("--manifest", required=True, help="Path to manifest CSV file.")
    parser.add_argument(
        "--output-dir", default="data/splits", help="Directory where split CSVs will be saved."
    )
    parser.add_argument(
        "--target",
        default="species",
        choices=["genus", "species"],
        help="Column to stratify splits on (genus or species).",
    )
    parser.add_argument("--train-ratio", type=float, default=0.70, help="Train split ratio.")
    parser.add_argument("--val-ratio", type=float, default=0.15, help="Validation split ratio.")
    parser.add_argument("--test-ratio", type=float, default=0.15, help="Test split ratio.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for split generation.")
    parser.add_argument(
        "--allow-unstratified",
        action="store_true",
        help="Permit best-effort splitting for small classes (<3 samples) instead of raising error.",
    )

    args = parser.parse_args()

    try:
        build_splits(
            args.manifest,
            args.output_dir,
            args.target,
            args.train_ratio,
            args.val_ratio,
            args.test_ratio,
            args.seed,
            args.allow_unstratified,
        )
    except Exception as e:
        logger.error(f"Failed to build splits: {e}")
        sys.exit(1)
