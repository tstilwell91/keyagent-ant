import csv
import pytest
from pathlib import Path

from antid.data.build_manifest import build_manifest
from antid.data.validate_dataset import validate_dataset


def create_fake_image(path: Path) -> None:
    """Helper to create a tiny fake image file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fake image data")


def test_build_manifest_synthetic_structure(tmp_path):
    # Create a small synthetic directory structure
    image_root = tmp_path / "images"

    # Structure 1: genus/species subdirs
    create_fake_image(image_root / "Camponotus" / "pennsylvanicus" / "casent0123456_d.jpg")
    create_fake_image(image_root / "Camponotus" / "pennsylvanicus" / "casent0123456_h.png")

    # Structure 2: genus_species combined subdirs
    create_fake_image(image_root / "Formica_rufa" / "casent0789012_p.webp")
    create_fake_image(image_root / "Lasius_niger" / "casent0456123.tiff")

    output_csv = tmp_path / "manifest.csv"

    # Build manifest
    build_manifest(str(image_root), str(output_csv))

    assert output_csv.exists()

    # Read manifest contents
    rows = []
    with open(output_csv, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    # 4 images should have been found
    assert len(rows) == 4

    # Verify expected columns
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
    }
    assert set(rows[0].keys()) == expected_cols

    # Verify specific details of parsed rows
    by_path = {Path(r["image_path"]).as_posix(): r for r in rows}
    assert "Camponotus/pennsylvanicus/casent0123456_d.jpg" in by_path
    assert "Camponotus/pennsylvanicus/casent0123456_h.png" in by_path
    assert "Formica_rufa/casent0789012_p.webp" in by_path
    assert "Lasius_niger/casent0456123.tiff" in by_path

    # Check view types and labels
    row_d = by_path["Camponotus/pennsylvanicus/casent0123456_d.jpg"]
    assert row_d["genus"] == "Camponotus"
    assert row_d["species"] == "pennsylvanicus"
    assert row_d["view_type"] == "dorsal"

    row_p = by_path["Formica_rufa/casent0789012_p.webp"]
    assert row_p["genus"] == "Formica"
    assert row_p["species"] == "rufa"
    assert row_p["view_type"] == "profile"

    # Verify that the generated IDs are deterministic and consistent
    # For Camponotus (both rows), label_genus_id must be the same
    camponotus_rows = [r for r in rows if r["genus"] == "Camponotus"]
    assert len(camponotus_rows) == 2
    assert camponotus_rows[0]["label_genus_id"] == camponotus_rows[1]["label_genus_id"]


def test_validate_dataset_success(tmp_path):
    image_root = tmp_path / "images"
    img1 = image_root / "Camponotus_pennsylvanicus" / "casent01_d.jpg"
    img2 = image_root / "Camponotus_pennsylvanicus" / "casent02_h.jpg"
    create_fake_image(img1)
    create_fake_image(img2)

    manifest_csv = tmp_path / "manifest.csv"
    build_manifest(str(image_root), str(manifest_csv))

    # Validate dataset (should pass)
    assert validate_dataset(str(manifest_csv), image_root=str(image_root))


def test_validate_dataset_catches_missing_files(tmp_path):
    manifest_csv = tmp_path / "manifest.csv"
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

    # image_path points to non-existent file
    with open(manifest_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerow({
            "image_path": str(tmp_path / "does_not_exist.jpg"),
            "genus": "Camponotus",
            "species": "pennsylvanicus",
            "label_genus_id": "0",
            "label_species_id": "0",
            "view_type": "dorsal",
            "source_url": "",
            "specimen_id": "CASENT01",
            "image_quality_flag": "unchecked",
        })

    # Should fail validation because file is missing
    assert not validate_dataset(str(manifest_csv))


def test_validate_dataset_catches_empty_genus_species(tmp_path):
    image_root = tmp_path / "images"
    img = image_root / "img.jpg"
    create_fake_image(img)

    manifest_csv = tmp_path / "manifest.csv"
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

    # empty genus or species
    with open(manifest_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerow({
            "image_path": str(img),
            "genus": "",
            "species": "pennsylvanicus",
            "label_genus_id": "0",
            "label_species_id": "0",
            "view_type": "dorsal",
            "source_url": "",
            "specimen_id": "CASENT01",
            "image_quality_flag": "unchecked",
        })

    assert not validate_dataset(str(manifest_csv))


def test_validate_dataset_catches_duplicate_image_path(tmp_path):
    image_root = tmp_path / "images"
    img = image_root / "img.jpg"
    create_fake_image(img)

    manifest_csv = tmp_path / "manifest.csv"
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

    # Two rows with identical image_path
    with open(manifest_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        row_data = {
            "image_path": str(img),
            "genus": "Camponotus",
            "species": "pennsylvanicus",
            "label_genus_id": "0",
            "label_species_id": "0",
            "view_type": "dorsal",
            "source_url": "",
            "specimen_id": "CASENT01",
            "image_quality_flag": "unchecked",
        }
        writer.writerow(row_data)
        writer.writerow(row_data)

    assert not validate_dataset(str(manifest_csv))


def test_validate_dataset_catches_invalid_view_type(tmp_path):
    image_root = tmp_path / "images"
    img = image_root / "img.jpg"
    create_fake_image(img)

    manifest_csv = tmp_path / "manifest.csv"
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

    # Invalid view_type 'underwater'
    with open(manifest_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerow({
            "image_path": str(img),
            "genus": "Camponotus",
            "species": "pennsylvanicus",
            "label_genus_id": "0",
            "label_species_id": "0",
            "view_type": "underwater",
            "source_url": "",
            "specimen_id": "CASENT01",
            "image_quality_flag": "unchecked",
        })

    assert not validate_dataset(str(manifest_csv))


def test_validate_dataset_catches_inconsistent_label_ids(tmp_path):
    image_root = tmp_path / "images"
    img1 = image_root / "img1.jpg"
    img2 = image_root / "img2.jpg"
    create_fake_image(img1)
    create_fake_image(img2)

    manifest_csv = tmp_path / "manifest.csv"
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

    # Same genus, but different label_genus_id
    with open(manifest_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerow({
            "image_path": str(img1),
            "genus": "Camponotus",
            "species": "pennsylvanicus",
            "label_genus_id": "0",
            "label_species_id": "0",
            "view_type": "dorsal",
            "source_url": "",
            "specimen_id": "CASENT01",
            "image_quality_flag": "unchecked",
        })
        writer.writerow({
            "image_path": str(img2),
            "genus": "Camponotus",
            "species": "castaneus",
            "label_genus_id": "1",  # Same genus 'Camponotus' must not have different ID, wait!
            # Wait, Camponotus has ID 0 in row 1, and ID 1 in row 2. This is inconsistent!
            # Let's verify that validate_dataset catches this.
            "label_species_id": "1",
            "view_type": "head",
            "source_url": "",
            "specimen_id": "CASENT02",
            "image_quality_flag": "unchecked",
        })

    assert not validate_dataset(str(manifest_csv))
