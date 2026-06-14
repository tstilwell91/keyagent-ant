import json
import os
import pytest
from pathlib import Path
from antid.keys.trait_sidecar_tools import (
    validate_observed_traits_sidecar,
    summarize_trait_sidecar_coverage,
    generate_trait_annotation_template
)
from antid.keys.cli import main

# Standard paths
KB_DIR = "data/kb/poc_myrmicinae_mem"
PREDICTIONS_CSV = "examples/kb/mock_predictions.csv"
MOCK_OBS_TRAITS = "examples/kb/mock_observed_traits.json"


def test_valid_observed_traits_validation():
    """Verifies that a valid observed traits sidecar passes validation."""
    report = validate_observed_traits_sidecar(KB_DIR, MOCK_OBS_TRAITS)
    assert report["status"] == "success"
    assert report["records_count"] == 2
    assert len(report["invalid_records"]) == 0
    # Both records in mock_observed_traits.json have three traits, so counts should match
    assert report["trait_counts"]["postpetiole_attachment"] == 2
    assert report["trait_counts"]["gaster_shape_dorsal"] == 2
    assert report["trait_counts"]["petiole_node_state"] == 2


def test_invalid_trait_id_caught(tmp_path):
    """Verifies that an unknown trait_id is caught and reported during validation."""
    invalid_data = {
        "casent0123456_profile": {
            "unknown_trait_id_xyz": "some_value"
        }
    }
    invalid_file = tmp_path / "invalid_traits.json"
    with open(invalid_file, "w") as f:
        json.dump(invalid_data, f)

    report = validate_observed_traits_sidecar(KB_DIR, str(invalid_file))
    assert report["status"] == "error"
    assert report["records_count"] == 1
    assert len(report["invalid_records"]) == 1
    assert report["invalid_records"][0]["trait_id"] == "unknown_trait_id_xyz"
    assert "not defined" in report["invalid_records"][0]["error"]


def test_invalid_trait_value_caught(tmp_path):
    """Verifies that an unallowed trait value is caught and reported."""
    invalid_data = {
        "casent0123456_profile": {
            "gaster_shape_dorsal": "invalid_unallowed_shape"
        }
    }
    invalid_file = tmp_path / "invalid_traits.json"
    with open(invalid_file, "w") as f:
        json.dump(invalid_data, f)

    report = validate_observed_traits_sidecar(KB_DIR, str(invalid_file))
    assert report["status"] == "error"
    assert report["records_count"] == 1
    assert len(report["invalid_records"]) == 1
    assert report["invalid_records"][0]["trait_id"] == "gaster_shape_dorsal"
    assert report["invalid_records"][0]["value"] == "invalid_unallowed_shape"
    assert "not allowed" in report["invalid_records"][0]["error"]


def test_jsonl_sidecar_format_supported(tmp_path):
    """Verifies that both JSON and JSONL sidecar formats are supported by validation."""
    jsonl_lines = [
        '{"image_id": "img1", "observed_traits": {"postpetiole_attachment": "dorsal_surface_first_gastral_segment"}}',
        '{"image_id": "img2", "observed_traits": {"gaster_shape_dorsal": "heart_shaped"}}'
    ]
    jsonl_file = tmp_path / "traits.jsonl"
    with open(jsonl_file, "w") as f:
        f.write("\n".join(jsonl_lines) + "\n")

    report = validate_observed_traits_sidecar(KB_DIR, str(jsonl_file))
    assert report["status"] == "success"
    assert report["records_count"] == 2
    assert len(report["invalid_records"]) == 0
    assert report["trait_counts"]["postpetiole_attachment"] == 1
    assert report["trait_counts"]["gaster_shape_dorsal"] == 1


def test_coverage_summary_computations():
    """Verifies that the coverage summary reports expected counts, frequencies, and rates."""
    summary = summarize_trait_sidecar_coverage(KB_DIR, MOCK_OBS_TRAITS)
    
    assert summary["records_count"] == 2
    assert summary["total_trait_observations"] == 6
    assert summary["records_with_no_traits"] == 0
    assert summary["trait_frequency"]["postpetiole_attachment"] == 2
    assert summary["value_frequency_by_trait"]["postpetiole_attachment"]["dorsal_surface_first_gastral_segment"] == 2
    
    # Assert missing/observed traits lists
    assert "postpetiole_attachment" in summary["observed_schema_traits"]
    assert "antenna_segment_count" in summary["missing_schema_traits"]
    
    # Assert coverage rate
    assert summary["coverage_rate_by_schema_trait"]["postpetiole_attachment"] == 1.0
    assert summary["coverage_rate_by_schema_trait"]["antenna_segment_count"] == 0.0

    # Assert new refined metrics
    assert summary["schema_trait_count"] == 11
    assert summary["covered_schema_trait_count"] == 3


def test_template_generation_scaffold(tmp_path):
    """Verifies that template generation creates parent directories and writes blank observed_traits."""
    out_file = tmp_path / "new_traits_dir" / "scaffold.jsonl"
    
    # Run template generator with max_records limit
    generate_trait_annotation_template(PREDICTIONS_CSV, str(out_file), max_records=2)
    
    assert out_file.exists()
    
    records = []
    with open(out_file, "r") as f:
        for line in f:
            records.append(json.loads(line))
            
    assert len(records) == 2
    for r in records:
        assert "image_id" in r
        assert "view_type" in r
        assert r["observed_traits"] == {}
        assert "metadata" in r
        assert r["metadata"]["adapter_source"] == "prediction_artifact_adapter"


def test_cli_validate_traits(capsys):
    """Verifies that CLI validate-traits runs successfully on valid input."""
    import sys
    # Mock argv
    sys.argv = [
        "cli.py",
        "validate-traits",
        "--kb-dir", KB_DIR,
        "--observed-traits", MOCK_OBS_TRAITS
    ]
    
    with pytest.raises(SystemExit) as exc_info:
        main()
        
    assert exc_info.value.code == 0
    
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["status"] == "success"
    assert report["records_count"] == 2


def test_cli_summarize_traits(capsys):
    """Verifies that CLI summarize-traits runs successfully on valid input."""
    import sys
    sys.argv = [
        "cli.py",
        "summarize-traits",
        "--kb-dir", KB_DIR,
        "--observed-traits", MOCK_OBS_TRAITS
    ]
    
    with pytest.raises(SystemExit) as exc_info:
        main()
        
    assert exc_info.value.code == 0
    
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["records_count"] == 2
    assert report["total_trait_observations"] == 6


def test_cli_generate_trait_template(tmp_path, capsys):
    """Verifies that CLI generate-trait-template runs successfully."""
    import sys
    out_file = tmp_path / "cli_scaffold.jsonl"
    sys.argv = [
        "cli.py",
        "generate-trait-template",
        "--predictions-csv", PREDICTIONS_CSV,
        "--output-jsonl", str(out_file),
        "--max-records", "1"
    ]
    
    with pytest.raises(SystemExit) as exc_info:
        main()
        
    assert exc_info.value.code == 0
    
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["status"] == "success"
    assert report["records_count"] == 1
    assert report["output_file"] == str(out_file)
    assert out_file.exists()
