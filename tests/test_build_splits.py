import csv
import pytest
from pathlib import Path

from antid.data.build_splits import build_splits, split_indices_stratified


def write_synthetic_manifest(path: Path, data: list) -> None:
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
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in data:
            writer.writerow(row)


def test_build_splits_preserves_columns_and_reproducible(tmp_path):
    manifest_csv = tmp_path / "manifest.csv"
    output_dir = tmp_path / "splits"

    # Write two classes with exactly 6 samples each to test reproducibility
    data = []
    for i in range(12):
        genus = "Camponotus" if i < 6 else "Formica"
        species = "pennsylvanicus" if i < 6 else "rufa"
        gid = "0" if i < 6 else "1"
        sid = "0" if i < 6 else "1"
        data.append({
            "image_path": f"/fake/path/img_{i}.jpg",
            "genus": genus,
            "species": species,
            "label_genus_id": gid,
            "label_species_id": sid,
            "view_type": "dorsal",
            "source_url": "",
            "specimen_id": f"CASENT{i:03d}",
            "image_quality_flag": "unchecked",
        })

    write_synthetic_manifest(manifest_csv, data)

    # Perform splits
    build_splits(
        manifest_path=str(manifest_csv),
        output_dir=str(output_dir),
        target="species",
        train_ratio=0.50,
        val_ratio=0.25,
        test_ratio=0.25,
        seed=42,
        allow_unstratified=False,
    )

    train_file = output_dir / "train.csv"
    val_file = output_dir / "val.csv"
    test_file = output_dir / "test.csv"
    combined_file = output_dir / "manifest_with_splits.csv"

    for f in [train_file, val_file, test_file, combined_file]:
        assert f.exists()

    # Read train file
    train_rows = []
    with open(train_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert "split" in reader.fieldnames
        for r in reader:
            train_rows.append(r)

    # Verify column structure is preserved
    expected_cols = {
        "image_path",
        "genus",
        "species",
        "label_genus_id",
        "label_species_id",
        "view_type",
        "source_url",
        "specimen_id",
        "image_quality_flag",
        "split",
    }
    assert set(train_rows[0].keys()) == expected_cols

    # Verify reproducibility by splitting again with same seed
    output_dir_2 = tmp_path / "splits_2"
    build_splits(
        manifest_path=str(manifest_csv),
        output_dir=str(output_dir_2),
        target="species",
        train_ratio=0.50,
        val_ratio=0.25,
        test_ratio=0.25,
        seed=42,
        allow_unstratified=False,
    )

    train_rows_2 = []
    with open(output_dir_2 / "train.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            train_rows_2.append(r)

    # Shuffling with the same seed must produce identical allocations
    assert [r["specimen_id"] for r in train_rows] == [r["specimen_id"] for r in train_rows_2]


def test_build_splits_raises_value_error_on_small_classes(tmp_path):
    manifest_csv = tmp_path / "manifest.csv"
    output_dir = tmp_path / "splits"

    # Write a dataset of 5 rows total where one class has only 1 sample
    data = []
    for i in range(5):
        genus = "Camponotus" if i < 4 else "Raregenus"
        species = "pennsylvanicus" if i < 4 else "rarespecies"
        gid = "0" if i < 4 else "1"
        sid = "0" if i < 4 else "1"
        data.append({
            "image_path": f"/fake/path/img_{i}.jpg",
            "genus": genus,
            "species": species,
            "label_genus_id": gid,
            "label_species_id": sid,
            "view_type": "dorsal",
            "source_url": "",
            "specimen_id": f"CASENT{i:03d}",
            "image_quality_flag": "unchecked",
        })

    write_synthetic_manifest(manifest_csv, data)

    # Calling as library should raise ValueError, not SystemExit, when allow_unstratified=False
    with pytest.raises(ValueError) as excinfo:
        build_splits(
            manifest_path=str(manifest_csv),
            output_dir=str(output_dir),
            target="species",
            train_ratio=0.70,
            val_ratio=0.15,
            test_ratio=0.15,
            seed=42,
            allow_unstratified=False,
        )
    assert "Cannot stratify small classes" in str(excinfo.value)

    # Running WITH allow_unstratified=True should succeed
    build_splits(
        manifest_path=str(manifest_csv),
        output_dir=str(output_dir),
        target="species",
        train_ratio=0.70,
        val_ratio=0.15,
        test_ratio=0.15,
        seed=42,
        allow_unstratified=True,
    )

    assert (output_dir / "train.csv").exists()
    assert (output_dir / "val.csv").exists()
    assert (output_dir / "test.csv").exists()


def test_binomial_species_stratification(tmp_path):
    manifest_csv = tmp_path / "manifest.csv"
    output_dir = tmp_path / "splits"

    # Create distinct genera sharing the exact same species epithet "testus"
    # Camponotus testus (3 samples) and Formica testus (3 samples)
    data = []
    for i in range(3):
        data.append({
            "image_path": f"/fake/path/camp_{i}.jpg",
            "genus": "Camponotus",
            "species": "testus",
            "label_genus_id": "0",
            "label_species_id": "0",
            "view_type": "dorsal",
            "source_url": "",
            "specimen_id": f"CAMP{i}",
            "image_quality_flag": "unchecked",
        })
    for i in range(3):
        data.append({
            "image_path": f"/fake/path/form_{i}.jpg",
            "genus": "Formica",
            "species": "testus",
            "label_genus_id": "1",
            "label_species_id": "1",
            "view_type": "head",
            "source_url": "",
            "specimen_id": f"FORM{i}",
            "image_quality_flag": "unchecked",
        })

    write_synthetic_manifest(manifest_csv, data)

    # If target="species" collapsed them, "testus" would have N=6 samples, which is easy to partition.
    # Because target="species" preserves full binomial, they are treated as two separate groups of N=3.
    # When stratified with N=3 and strict stratification, they both allocate 1/1/1 to train/val/test.
    build_splits(
        manifest_path=str(manifest_csv),
        output_dir=str(output_dir),
        target="species",
        train_ratio=0.70,
        val_ratio=0.15,
        test_ratio=0.15,
        seed=42,
        allow_unstratified=False,  # This would raise ValueError if they were collapsed incorrectly or failed strict N>=3 check
    )

    # Verify that each split has exactly 2 rows (1 from Camponotus testus, 1 from Formica testus)
    for name in ["train", "val", "test"]:
        file_path = output_dir / f"{name}.csv"
        rows = []
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(r)
        assert len(rows) == 2
        # Check both binomial species exist in each split
        genera = [r["genus"] for r in rows]
        assert "Camponotus" in genera
        assert "Formica" in genera


def test_split_allocation_counts():
    # Test N == 3 produces 1/1/1
    rows_3 = [{"genus": "Camponotus", "species": "pennsylvanicus"} for _ in range(3)]
    tr_idx, val_idx, te_idx = split_indices_stratified(
        rows_3, "species", 0.70, 0.15, 0.15, 42, allow_unstratified=False
    )
    assert len(tr_idx) == 1
    assert len(val_idx) == 1
    assert len(te_idx) == 1

    # Test N == 4 produces 2/1/1
    rows_4 = [{"genus": "Camponotus", "species": "pennsylvanicus"} for _ in range(4)]
    tr_idx, val_idx, te_idx = split_indices_stratified(
        rows_4, "species", 0.70, 0.15, 0.15, 42, allow_unstratified=False
    )
    assert len(tr_idx) == 2
    assert len(val_idx) == 1
    assert len(te_idx) == 1

    # Test larger N allocation while preserving at least one item per split
    # For example, N=5 with ratios 0.70, 0.15, 0.15 -> produces 3/1/1
    rows_5 = [{"genus": "Camponotus", "species": "pennsylvanicus"} for _ in range(5)]
    tr_idx, val_idx, te_idx = split_indices_stratified(
        rows_5, "species", 0.70, 0.15, 0.15, 42, allow_unstratified=False
    )
    assert len(tr_idx) == 3
    assert len(val_idx) == 1
    assert len(te_idx) == 1
