import csv
import os
import tempfile
import pytest
from pathlib import Path

from antid.data.build_splits import build_splits
from antid.data.build_dataset_variants import check_split_leakage

# Synthetic manifest file containing 5 species.
# Some species have multiple specimens.
# Each specimen has dorsal, head, and profile views.
SYNTHETIC_MANIFEST_CONTENT = """image_path,genus,species,label_genus_id,label_species_id,view_type,caste,source_url,image_url,specimen_id,catalog_number,image_quality_flag
data/raw/casent001_d.jpg,Camponotus,maculatus,0,0,dorsal,worker,http://url,http://url,casent001,casent001,unchecked
data/raw/casent001_h.jpg,Camponotus,maculatus,0,0,head,worker,http://url,http://url,casent001,casent001,unchecked
data/raw/casent001_p.jpg,Camponotus,maculatus,0,0,profile,worker,http://url,http://url,casent001,casent001,unchecked
data/raw/casent002_d.jpg,Camponotus,maculatus,0,0,dorsal,worker,http://url,http://url,casent002,casent002,unchecked
data/raw/casent002_h.jpg,Camponotus,maculatus,0,0,head,worker,http://url,http://url,casent002,casent002,unchecked
data/raw/casent002_p.jpg,Camponotus,maculatus,0,0,profile,worker,http://url,http://url,casent002,casent002,unchecked
data/raw/casent003_d.jpg,Camponotus,maculatus,0,0,dorsal,worker,http://url,http://url,casent003,casent003,unchecked
data/raw/casent003_h.jpg,Camponotus,maculatus,0,0,head,worker,http://url,http://url,casent003,casent003,unchecked
data/raw/casent003_p.jpg,Camponotus,maculatus,0,0,profile,worker,http://url,http://url,casent003,casent003,unchecked
data/raw/casent004_d.jpg,Pheidole,megacephala,1,1,dorsal,worker,http://url,http://url,casent004,casent004,unchecked
data/raw/casent004_h.jpg,Pheidole,megacephala,1,1,head,worker,http://url,http://url,casent004,casent004,unchecked
data/raw/casent004_p.jpg,Pheidole,megacephala,1,1,profile,worker,http://url,http://url,casent004,casent004,unchecked
data/raw/casent005_d.jpg,Pheidole,megacephala,1,1,dorsal,worker,http://url,http://url,casent005,casent005,unchecked
data/raw/casent005_h.jpg,Pheidole,megacephala,1,1,head,worker,http://url,http://url,casent005,casent005,unchecked
data/raw/casent005_p.jpg,Pheidole,megacephala,1,1,profile,worker,http://url,http://url,casent005,casent005,unchecked
data/raw/casent006_d.jpg,Pheidole,megacephala,1,1,dorsal,worker,http://url,http://url,casent006,casent006,unchecked
data/raw/casent006_h.jpg,Pheidole,megacephala,1,1,head,worker,http://url,http://url,casent006,casent006,unchecked
data/raw/casent006_p.jpg,Pheidole,megacephala,1,1,profile,worker,http://url,http://url,casent006,casent006,unchecked
data/raw/casent007_d.jpg,Linepithema,humile,2,2,dorsal,worker,http://url,http://url,casent007,casent007,unchecked
data/raw/casent007_h.jpg,Linepithema,humile,2,2,head,worker,http://url,http://url,casent007,casent007,unchecked
data/raw/casent007_p.jpg,Linepithema,humile,2,2,profile,worker,http://url,http://url,casent007,casent007,unchecked
data/raw/casent008_d.jpg,Linepithema,humile,2,2,dorsal,worker,http://url,http://url,casent008,casent008,unchecked
data/raw/casent008_h.jpg,Linepithema,humile,2,2,head,worker,http://url,http://url,casent008,casent008,unchecked
data/raw/casent008_p.jpg,Linepithema,humile,2,2,profile,worker,http://url,http://url,casent008,casent008,unchecked
data/raw/casent009_d.jpg,Linepithema,humile,2,2,dorsal,worker,http://url,http://url,casent009,casent009,unchecked
data/raw/casent009_h.jpg,Linepithema,humile,2,2,head,worker,http://url,http://url,casent009,casent009,unchecked
data/raw/casent009_p.jpg,Linepithema,humile,2,2,profile,worker,http://url,http://url,casent009,casent009,unchecked
"""


def test_build_specimen_splits_grouped():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as tmp_mani:
        tmp_manifest_name = tmp_mani.name
        tmp_mani.write(SYNTHETIC_MANIFEST_CONTENT)

    with tempfile.TemporaryDirectory() as tmp_out_dir:
        try:
            # Run grouped splitting
            build_splits(
                manifest_path=tmp_manifest_name,
                output_dir=tmp_out_dir,
                target="species",
                train_ratio=0.60,
                val_ratio=0.20,
                test_ratio=0.20,
                seed=42,
                allow_unstratified=True,
                specimen_aware=True,
            )

            train_path = Path(tmp_out_dir) / "train.csv"
            val_path = Path(tmp_out_dir) / "val.csv"
            test_path = Path(tmp_out_dir) / "test.csv"

            assert train_path.exists()
            assert val_path.exists()
            assert test_path.exists()

            # Read splits
            def load_split_rows(path):
                with open(path, mode="r", newline="", encoding="utf-8") as f:
                    return list(csv.DictReader(f))

            train_rows = load_split_rows(train_path)
            val_rows = load_split_rows(val_path)
            test_rows = load_split_rows(test_path)

            train_specs = set(r["specimen_id"] for r in train_rows)
            val_specs = set(r["specimen_id"] for r in val_rows)
            test_specs = set(r["specimen_id"] for r in test_rows)

            # Verification 1: Specimen IDs must not leak across partitions
            assert train_specs.isdisjoint(val_specs)
            assert train_specs.isdisjoint(test_specs)
            assert val_specs.isdisjoint(test_specs)

            # Verification 2: Check split leakage checker catches this if we fake a leakage
            # (Check leakage checker passes since clean)
            assert check_split_leakage(tmp_out_dir)

            # Verification 3: Preserves all three views in the same split
            # Every specimen in train/val/test should have exactly 3 rows
            for spec_id in train_specs:
                spec_rows = [r for r in train_rows if r["specimen_id"] == spec_id]
                assert len(spec_rows) == 3
                assert set(r["view_type"] for r in spec_rows) == {"dorsal", "head", "profile"}

            for spec_id in val_specs:
                spec_rows = [r for r in val_rows if r["specimen_id"] == spec_id]
                assert len(spec_rows) == 3
                assert set(r["view_type"] for r in spec_rows) == {"dorsal", "head", "profile"}

            for spec_id in test_specs:
                spec_rows = [r for r in test_rows if r["specimen_id"] == spec_id]
                assert len(spec_rows) == 3
                assert set(r["view_type"] for r in spec_rows) == {"dorsal", "head", "profile"}

        finally:
            if os.path.exists(tmp_manifest_name):
                os.remove(tmp_manifest_name)


def test_build_specimen_splits_leakage_detection():
    # Intentionally create leaking split files and verify check_split_leakage returns False
    with tempfile.TemporaryDirectory() as tmp_out_dir:
        train_path = Path(tmp_out_dir) / "train.csv"
        val_path = Path(tmp_out_dir) / "val.csv"
        test_path = Path(tmp_out_dir) / "test.csv"

        headers = ["specimen_id"]
        with open(train_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=headers)
            w.writeheader()
            w.writerow({"specimen_id": "casent001"})
            w.writerow({"specimen_id": "casent002"})

        with open(val_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=headers)
            w.writeheader()
            w.writerow({"specimen_id": "casent002"}) # LEAK!

        with open(test_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=headers)
            w.writeheader()
            w.writerow({"specimen_id": "casent003"})

        # Since casent002 leaks between train and val, it must fail leakage check
        assert not check_split_leakage(tmp_out_dir)


def test_build_splits_determinism():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as tmp_mani:
        tmp_manifest_name = tmp_mani.name
        tmp_mani.write(SYNTHETIC_MANIFEST_CONTENT)

    with tempfile.TemporaryDirectory() as tmp_dir1, tempfile.TemporaryDirectory() as tmp_dir2:
        try:
            # Split 1 (seed=42)
            build_splits(
                manifest_path=tmp_manifest_name,
                output_dir=tmp_dir1,
                target="species",
                train_ratio=0.60,
                val_ratio=0.20,
                test_ratio=0.20,
                seed=42,
                allow_unstratified=True,
                specimen_aware=True,
            )

            # Split 2 (seed=42)
            build_splits(
                manifest_path=tmp_manifest_name,
                output_dir=tmp_dir2,
                target="species",
                train_ratio=0.60,
                val_ratio=0.20,
                test_ratio=0.20,
                seed=42,
                allow_unstratified=True,
                specimen_aware=True,
            )

            # Verify identical output files
            for filename in ["train.csv", "val.csv", "test.csv"]:
                with open(Path(tmp_dir1) / filename, "r") as f1, open(Path(tmp_dir2) / filename, "r") as f2:
                    assert f1.read() == f2.read()

        finally:
            if os.path.exists(tmp_manifest_name):
                os.remove(tmp_manifest_name)
