import os
import csv
import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from antid.keys.trait_curation_assets import materialize_trait_curation_images
from antid.keys.cli import main


@pytest.fixture
def synthetic_selection_and_splits(tmp_path):
    """Sets up synthetic curation selection and split CSV files."""
    split_dir = tmp_path / "splits"
    split_dir.mkdir()

    # 1. Create a synthetic test.csv split
    # Rows contain image_path, specimen_id, catalog_number, image_url, source_url, split, etc.
    with open(split_dir / "test.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "image_path", "genus", "species", "label_genus_id", "label_species_id",
            "view_type", "caste", "source_url", "image_url", "specimen_id", "catalog_number",
            "image_quality_flag", "split"
        ])
        # Specimen 1 (all views present in splits)
        writer.writerow([
            "spec_1/d.jpg", "Mock", "a", "0", "0", "dorsal", "worker",
            "http://www.antweb.org/images/spec_1_d.jpg", "http://www.antweb.org/images/spec_1_d.jpg",
            "spec_1", "spec_1", "checked", "test"
        ])
        writer.writerow([
            "spec_1/h.jpg", "Mock", "a", "0", "0", "head", "worker",
            "http://www.antweb.org/images/spec_1_h.jpg", "http://www.antweb.org/images/spec_1_h.jpg",
            "spec_1", "spec_1", "checked", "test"
        ])
        writer.writerow([
            "spec_1/p.jpg", "Mock", "a", "0", "0", "profile", "worker",
            "http://www.antweb.org/images/spec_1_p.jpg", "http://www.antweb.org/images/spec_1_p.jpg",
            "spec_1", "spec_1", "checked", "test"
        ])
        # Specimen 2 (one view missing or unresolved)
        writer.writerow([
            "spec_2/d.jpg", "Mock", "b", "0", "0", "dorsal", "worker",
            "http://www.antweb.org/images/spec_2_d.jpg", "http://www.antweb.org/images/spec_2_d.jpg",
            "spec_2", "spec_2", "checked", "test"
        ])
        writer.writerow([
            "spec_2/h.jpg", "Mock", "b", "0", "0", "head", "worker",
            "", "",  # missing url
            "spec_2", "spec_2", "checked", "test"
        ])

    # 2. Create a synthetic selection.csv
    selection_csv = tmp_path / "selection.csv"
    with open(selection_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "specimen_id", "catalog_number", "kb_taxon_id", "kb_scientific_name",
            "dataset_genus", "dataset_species", "source_split",
            "dorsal_image_path", "head_image_path", "profile_image_path",
            "dorsal_image_id", "head_image_id", "profile_image_id"
        ])
        # spec_1 has all tri-views
        writer.writerow([
            "spec_1", "spec_1", "mock_taxon_a", "Mock taxon A",
            "Mock", "a", "test",
            "spec_1/d.jpg", "spec_1/h.jpg", "spec_1/p.jpg",
            "spec1_d", "spec1_h", "spec1_p"
        ])
        # spec_2 has dorsal and head, but head URL is empty, and profile path is empty
        writer.writerow([
            "spec_2", "spec_2", "mock_taxon_b", "Mock taxon B",
            "Mock", "b", "test",
            "spec_2/d.jpg", "spec_2/h.jpg", "",
            "spec2_d", "spec2_h", ""
        ])

    image_root = tmp_path / "image_root"
    image_root.mkdir()

    return {
        "selection_csv": str(selection_csv),
        "split_dir": str(split_dir),
        "image_root": str(image_root)
    }


def test_materialize_images_dry_run(synthetic_selection_and_splits):
    """Verifies that dry-run performs matching, URL resolution, but writes no files."""
    result = materialize_trait_curation_images(
        selection_csv=synthetic_selection_and_splits["selection_csv"],
        split_dir=synthetic_selection_and_splits["split_dir"],
        image_root=synthetic_selection_and_splits["image_root"],
        dry_run=True,
        overwrite=False
    )

    assert result["status"] == "success"
    assert result["selected_specimens"] == 2
    assert result["requested_images"] == 5  # spec_1 (3) + spec_2 (2)
    assert result["matched_images"] == 5    # all paths are found in splits
    assert result["downloaded_images"] == 0
    assert result["unresolved_images"] == 1  # spec_2 head has empty URL
    assert result["existing_images"] == 0

    # Ensure no files are actually written
    img_root_path = Path(synthetic_selection_and_splits["image_root"])
    files = list(img_root_path.glob("**/*"))
    # Only the directory itself (which was created in the fixture)
    assert len([f for f in files if f.is_file()]) == 0

    # Inspect records
    records = {f"{r['specimen_id']}_{r['view_type']}": r for r in result["records"]}
    assert len(records) == 5

    # spec_1 dorsal should have resolved URL pointing to static.antweb.org (HTTPS)
    r1 = records["spec_1_dorsal"]
    assert r1["source_url"] == "https://static.antweb.org/images/spec_1_d.jpg"
    assert r1["action"] == "dry_run_download"
    assert r1["status"] == "success"

    # spec_2 head should be unresolved because of empty URL
    r2 = records["spec_2_head"]
    assert r2["source_url"] is None
    assert r2["status"] == "unresolved"
    assert "no downloadable URL" in r2["error"]


@patch("requests.get")
def test_materialize_images_real_download(mock_get, synthetic_selection_and_splits):
    """Verifies real download writes files to disk, handles exceptions and skipped/overwrite options."""
    # Tiny 1x1 valid GIF bytes
    gif_bytes = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = gif_bytes
    mock_get.return_value = mock_response

    # Execute first download
    result = materialize_trait_curation_images(
        selection_csv=synthetic_selection_and_splits["selection_csv"],
        split_dir=synthetic_selection_and_splits["split_dir"],
        image_root=synthetic_selection_and_splits["image_root"],
        dry_run=False,
        overwrite=False
    )

    assert result["downloaded_images"] == 4  # 3 for spec_1 + 1 for spec_2 (dorsal)
    assert result["unresolved_images"] == 1  # 1 for spec_2 (head)
    assert result["failed_downloads"] == 0

    # Check that 4 files are written to disk
    img_root_path = Path(synthetic_selection_and_splits["image_root"])
    files_on_disk = [f for f in img_root_path.glob("**/*") if f.is_file()]
    assert len(files_on_disk) == 4

    # Ensure Pillow recorded dimensions for downloaded files
    records = {f"{r['specimen_id']}_{r['view_type']}": r for r in result["records"]}
    assert records["spec_1_dorsal"]["width"] == 1
    assert records["spec_1_dorsal"]["height"] == 1

    # Second download (overwrite=False) -> should skip existing files
    mock_get.reset_mock()
    result_second = materialize_trait_curation_images(
        selection_csv=synthetic_selection_and_splits["selection_csv"],
        split_dir=synthetic_selection_and_splits["split_dir"],
        image_root=synthetic_selection_and_splits["image_root"],
        dry_run=False,
        overwrite=False
    )
    assert result_second["downloaded_images"] == 0
    assert result_second["skipped_images"] == 4
    assert result_second["existing_images"] == 4
    mock_get.assert_not_called()

    # Third download (overwrite=True) -> should overwrite/replace existing files
    result_third = materialize_trait_curation_images(
        selection_csv=synthetic_selection_and_splits["selection_csv"],
        split_dir=synthetic_selection_and_splits["split_dir"],
        image_root=synthetic_selection_and_splits["image_root"],
        dry_run=False,
        overwrite=True
    )
    assert result_third["downloaded_images"] == 4
    assert result_third["skipped_images"] == 0
    assert mock_get.call_count == 4


@patch("requests.get")
def test_materialize_images_download_failures(mock_get, synthetic_selection_and_splits):
    """Verifies that failed downloads are reported cleanly without terminating execution."""
    # Mock requests throwing exception or HTTP errors
    def side_effect(url, **kwargs):
        if "spec_1_d" in url:
            # Raise connection error
            raise ConnectionError("Mock network drop")
        else:
            # Return HTTP 404
            resp = MagicMock()
            resp.status_code = 404
            return resp

    mock_get.side_effect = side_effect

    result = materialize_trait_curation_images(
        selection_csv=synthetic_selection_and_splits["selection_csv"],
        split_dir=synthetic_selection_and_splits["split_dir"],
        image_root=synthetic_selection_and_splits["image_root"],
        dry_run=False,
        overwrite=False
    )

    assert result["downloaded_images"] == 0
    assert result["unresolved_images"] == 1  # spec_2 head
    assert result["failed_downloads"] == 4   # 3 (spec_1 dorsal/head/profile) + 1 (spec_2 dorsal)

    # Inspect records for failure reasons
    records = {f"{r['specimen_id']}_{r['view_type']}": r for r in result["records"]}
    assert records["spec_1_dorsal"]["status"] == "failed"
    assert "Mock network drop" in records["spec_1_dorsal"]["error"]
    assert "HTTP Error 404" in records["spec_1_head"]["error"]


def test_cli_materialize_dry_run(synthetic_selection_and_splits, capsys, monkeypatch):
    """Verifies the CLI command triggers successfully and outputs correct summary metrics."""
    cli_args = [
        "cli.py", "materialize-trait-curation-images",
        "--selection-csv", synthetic_selection_and_splits["selection_csv"],
        "--split-dir", synthetic_selection_and_splits["split_dir"],
        "--image-root", synthetic_selection_and_splits["image_root"],
        "--dry-run"
    ]

    monkeypatch.setattr("sys.argv", cli_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary["status"] == "success"
    assert summary["selected_specimens"] == 2
    assert summary["requested_images"] == 5
    assert summary["matched_images"] == 5
    assert summary["downloaded_images"] == 0
    assert summary["unresolved_images"] == 1
