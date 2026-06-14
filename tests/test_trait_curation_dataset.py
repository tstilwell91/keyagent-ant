import csv
import json
import os
import pytest
from pathlib import Path
from antid.keys.trait_curation_dataset import select_trait_curation_specimens, row_matches_taxon, choose_representative_image
from antid.keys.cli import main

KB_DIR = "data/kb/poc_myrmicinae_mem"


def test_row_matches_taxon_logic():
    """Verifies taxon case-insensitive and binomial matching logic."""
    taxon_genus = {"taxon_id": "crematogaster", "scientific_name": "Crematogaster", "rank": "genus"}
    taxon_species = {"taxon_id": "wasmannia_auropunctata", "scientific_name": "Wasmannia auropunctata", "rank": "species"}

    # Genus rank matching
    assert row_matches_taxon({"genus": "Crematogaster", "species": ""}, taxon_genus)
    assert row_matches_taxon({"genus": "crematogaster", "species": ""}, taxon_genus)
    assert not row_matches_taxon({"genus": "Solenopsis", "species": ""}, taxon_genus)

    # Species rank matching
    assert row_matches_taxon({"genus": "Wasmannia", "species": "auropunctata"}, taxon_species)
    assert row_matches_taxon({"genus": "wasmannia", "species": "auropunctata"}, taxon_species)
    assert row_matches_taxon({"genus": "", "species": "wasmannia_auropunctata"}, taxon_species)
    assert not row_matches_taxon({"genus": "Wasmannia", "species": "robusta"}, taxon_species)


def test_choose_representative_image():
    """Verifies deterministic choice of representative image based on quality flag and path."""
    rows = [
        {"image_path": "path/c.jpg", "image_quality_flag": "poor"},     # rank 3
        {"image_path": "path/a.jpg", "image_quality_flag": "high"},     # rank 0
        {"image_path": "path/b.jpg", "image_quality_flag": ""},         # rank 1
        {"image_path": "path/d.jpg", "image_quality_flag": "checked"},  # rank 0
    ]
    # 'path/a.jpg' (rank 0, alphabetical 'a' < 'd') should be selected
    selected = choose_representative_image(rows)
    assert selected["image_path"] == "path/a.jpg"

    # Test alphabetical tie-breaker with same quality rank
    rows_equal_q = [
        {"image_path": "path/y.jpg", "image_quality_flag": ""},
        {"image_path": "path/x.jpg", "image_quality_flag": ""},
    ]
    selected_eq = choose_representative_image(rows_equal_q)
    assert selected_eq["image_path"] == "path/x.jpg"


def test_missing_split_files_raises_error(tmp_path):
    """Verifies select_trait_curation_specimens raises FileNotFoundError if split CSVs are missing."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    
    with pytest.raises(FileNotFoundError) as exc_info:
        select_trait_curation_specimens(
            split_dir=str(empty_dir),
            kb_dir=KB_DIR,
            output_selection=str(tmp_path / "sel.csv"),
            output_template=str(tmp_path / "temp.jsonl")
        )
    assert "not found" in str(exc_info.value)


def create_mock_splits(split_dir: Path):
    """Helper to write mock split files with controlled specimen information."""
    split_dir.mkdir(parents=True, exist_ok=True)
    
    headers = [
        "specimen_id", "catalog_number", "genus", "species",
        "view_type", "image_path", "image_quality_flag"
    ]
    
    # 1. Specimen 1 (Crematogaster): tri-view complete, specimen_id is set
    # 2. Specimen 2 (Crematogaster): tri-view complete, specimen_id is empty, catalog_number fallback
    # 3. Specimen 3 (Solenopsis): incomplete views (missing head)
    # 4. Specimen 4 (Wasmannia): tri-view complete, multiple dorsal views
    # 5. Specimen 5 (Crematogaster): tri-view complete, has poor quality flag on one dorsal and unchecked on other
    
    test_rows = [
        # Specimen 1
        {"specimen_id": "spec1", "catalog_number": "cat1", "genus": "Crematogaster", "species": "ashmeadi", "view_type": "dorsal", "image_path": "images/spec1_d.jpg", "image_quality_flag": "high"},
        {"specimen_id": "spec1", "catalog_number": "cat1", "genus": "Crematogaster", "species": "ashmeadi", "view_type": "head", "image_path": "images/spec1_h.jpg", "image_quality_flag": "checked"},
        {"specimen_id": "spec1", "catalog_number": "cat1", "genus": "Crematogaster", "species": "ashmeadi", "view_type": "profile", "image_path": "images/spec1_p.jpg", "image_quality_flag": "unchecked"},
        
        # Specimen 2 (fallback key)
        {"specimen_id": "", "catalog_number": "cat2", "genus": "Crematogaster", "species": "ashmeadi", "view_type": "dorsal", "image_path": "images/cat2_d.jpg", "image_quality_flag": "good"},
        {"specimen_id": "", "catalog_number": "cat2", "genus": "Crematogaster", "species": "ashmeadi", "view_type": "head", "image_path": "images/cat2_h.jpg", "image_quality_flag": ""},
        {"specimen_id": "", "catalog_number": "cat2", "genus": "Crematogaster", "species": "ashmeadi", "view_type": "profile", "image_path": "images/cat2_p.jpg", "image_quality_flag": ""},
        
        # Specimen 3 (incomplete, missing head)
        {"specimen_id": "spec3", "catalog_number": "cat3", "genus": "Solenopsis", "species": "invicta", "view_type": "dorsal", "image_path": "images/spec3_d.jpg", "image_quality_flag": ""},
        {"specimen_id": "spec3", "catalog_number": "cat3", "genus": "Solenopsis", "species": "invicta", "view_type": "profile", "image_path": "images/spec3_p.jpg", "image_quality_flag": ""},
    ]
    
    val_rows = [
        # Specimen 4 (Wasmannia) - has multi-images for dorsal
        {"specimen_id": "spec4", "catalog_number": "cat4", "genus": "Wasmannia", "species": "auropunctata", "view_type": "dorsal", "image_path": "images/spec4_d1.jpg", "image_quality_flag": "unchecked"},
        {"specimen_id": "spec4", "catalog_number": "cat4", "genus": "Wasmannia", "species": "auropunctata", "view_type": "dorsal", "image_path": "images/spec4_d2.jpg", "image_quality_flag": "high"}, # High quality preferred
        {"specimen_id": "spec4", "catalog_number": "cat4", "genus": "Wasmannia", "species": "auropunctata", "view_type": "head", "image_path": "images/spec4_h.jpg", "image_quality_flag": ""},
        {"specimen_id": "spec4", "catalog_number": "cat4", "genus": "Wasmannia", "species": "auropunctata", "view_type": "profile", "image_path": "images/spec4_p.jpg", "image_quality_flag": ""},
    ]
    
    train_rows = [
        # Specimen 5 (Crematogaster)
        {"specimen_id": "spec5", "catalog_number": "cat5", "genus": "Crematogaster", "species": "coarctata", "view_type": "dorsal", "image_path": "images/spec5_d.jpg", "image_quality_flag": "unchecked"},
        {"specimen_id": "spec5", "catalog_number": "cat5", "genus": "Crematogaster", "species": "coarctata", "view_type": "head", "image_path": "images/spec5_h.jpg", "image_quality_flag": ""},
        {"specimen_id": "spec5", "catalog_number": "cat5", "genus": "Crematogaster", "species": "coarctata", "view_type": "profile", "image_path": "images/spec5_p.jpg", "image_quality_flag": ""},
    ]

    for name, rows in [("test", test_rows), ("val", val_rows), ("train", train_rows)]:
        with open(split_dir / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)


def test_select_trait_curation_specimens_workflow(tmp_path):
    """Full workflow verification of deterministic subset selection."""
    split_dir = tmp_path / "splits"
    create_mock_splits(split_dir)

    out_csv = tmp_path / "selected_specimens.csv"
    out_jsonl = tmp_path / "blank_template.jsonl"

    # Select specimens
    summary = select_trait_curation_specimens(
        split_dir=str(split_dir),
        kb_dir=KB_DIR,
        output_selection=str(out_csv),
        output_template=str(out_jsonl),
        specimens_per_taxon=5,
        preferred_split="test",
        seed=123,
        allow_split_fallback=True
    )

    # 1. Assert summary stats
    assert summary["status"] == "success"
    # Valid selected specimens should be:
    # Crematogaster: spec1 (test), cat2 (test), spec5 (train fallback) -> 3 specimens
    # Wasmannia (wasmannia_auropunctata): spec4 (val fallback) -> 1 specimen
    # Solenopsis: incomplete, so 0 specimens
    assert summary["selected_specimens"] == 4
    assert summary["taxon_counts"]["crematogaster"] == 3
    assert summary["taxon_counts"]["wasmannia_auropunctata"] == 1
    assert "solenopsis" not in summary["taxon_counts"]

    # 2. Check output CSV rows and headers
    assert out_csv.exists()
    with open(out_csv, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
    
    assert len(reader) == 4
    
    # Verify fallback specimen key selection (cat2 has empty specimen_id)
    cat2_row = [r for r in reader if r["catalog_number"] == "cat2"][0]
    assert cat2_row["specimen_id"] == ""
    assert cat2_row["kb_taxon_id"] == "crematogaster"

    # Verify duplicate tracking column and quality flag selection for spec4
    spec4_row = [r for r in reader if r["specimen_id"] == "spec4"][0]
    assert spec4_row["duplicate_view_counts"] == "dorsal:2,head:1,profile:1"
    # dorsal_image_path should be spec4_d2 because of high quality flag preferred over unchecked
    assert spec4_row["dorsal_image_path"] == "images/spec4_d2.jpg"

    # 3. Check output JSONL template
    assert out_jsonl.exists()
    with open(out_jsonl, "r", encoding="utf-8") as f:
        jsonl_lines = [json.loads(line) for line in f]

    assert len(jsonl_lines) == 4
    
    for record in jsonl_lines:
        assert record["observed_traits"] == {}
        assert record["source_evidence"] == []
        
        # Verify metadata is strictly non-evidentiary
        meta = record["annotation_metadata"]
        assert meta["annotation_round"] == "trait_curated_v0"
        assert meta["annotation_status"] == "not_started"
        assert meta["trait_values_verified"] is False
        assert meta["trait_source_policy"] == "blank_template_no_traits_inferred"
        assert meta["review_status"] == "needs_expert_or_source_review"
        assert meta["annotator"] is None


def test_seed_and_split_determinism(tmp_path):
    """Verifies deterministic output across runs and fallback split behavior."""
    split_dir = tmp_path / "splits"
    create_mock_splits(split_dir)

    out_csv_1 = tmp_path / "sel1.csv"
    out_jsonl_1 = tmp_path / "temp1.jsonl"
    out_csv_2 = tmp_path / "sel2.csv"
    out_jsonl_2 = tmp_path / "temp2.jsonl"

    # Run 1
    select_trait_curation_specimens(
        split_dir=str(split_dir),
        kb_dir=KB_DIR,
        output_selection=str(out_csv_1),
        output_template=str(out_jsonl_1),
        specimens_per_taxon=1,  # Select only 1 specimen per taxon
        preferred_split="test",
        seed=42
    )

    # Run 2 with same seed
    select_trait_curation_specimens(
        split_dir=str(split_dir),
        kb_dir=KB_DIR,
        output_selection=str(out_csv_2),
        output_template=str(out_jsonl_2),
        specimens_per_taxon=1,
        preferred_split="test",
        seed=42
    )

    # Assert CSVs match exactly
    with open(out_csv_1, "r", encoding="utf-8") as f1, open(out_csv_2, "r", encoding="utf-8") as f2:
        assert f1.read() == f2.read()

    # Assert JSONLs match exactly
    with open(out_jsonl_1, "r", encoding="utf-8") as f1, open(out_jsonl_2, "r", encoding="utf-8") as f2:
        assert f1.read() == f2.read()


def test_cli_integration_select_trait_curation_specimens(tmp_path, monkeypatch):
    """Verifies select-trait-curation-specimens CLI subcommand executes cleanly."""
    split_dir = tmp_path / "splits"
    create_mock_splits(split_dir)

    out_csv = tmp_path / "cli_selected.csv"
    out_jsonl = tmp_path / "cli_template.jsonl"

    args = [
        "cli.py",
        "select-trait-curation-specimens",
        "--split-dir", str(split_dir),
        "--kb-dir", KB_DIR,
        "--output-selection", str(out_csv),
        "--output-template", str(out_jsonl),
        "--specimens-per-taxon", "2",
        "--preferred-split", "test",
        "--seed", "99"
    ]

    monkeypatch.setattr("sys.argv", args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    assert out_csv.exists()
    assert out_jsonl.exists()
