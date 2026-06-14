"""Unit and integration tests for the batch key-consistency evaluator."""

import os
import json
import tempfile
import pytest
from antid.keys.kb_loader import load_kb
from antid.keys.key_consistency_evaluator import (
    load_observed_traits_sidecar,
    evaluate_predictions_csv_with_kb,
)
from antid.keys.cli import run_evaluate_key_consistency


@pytest.fixture
def temp_sidecar_json():
    """Fixture creating a temporary JSON sidecar file."""
    data = {
        "casent0123456_profile": {
            "postpetiole_attachment": "dorsal_surface_first_gastral_segment",
            "gaster_shape_dorsal": "heart_shaped",
            "petiole_node_state": "no_node_dorsoventrally_flattened"
        },
        "casent0789101_profile": {
            "postpetiole_attachment": "dorsal_surface_first_gastral_segment",
            "gaster_shape_dorsal": "heart_shaped",
            "petiole_node_state": "no_node_dorsoventrally_flattened"
        }
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        json.dump(data, tmp, indent=2)
        tmp_name = tmp.name
    yield tmp_name
    if os.path.exists(tmp_name):
        os.remove(tmp_name)


@pytest.fixture
def temp_sidecar_jsonl():
    """Fixture creating a temporary JSONL sidecar file."""
    lines = [
        {"image_id": "casent0123456_profile", "observed_traits": {"postpetiole_attachment": "dorsal_surface_first_gastral_segment"}},
        {"image_id": "casent0789101_profile", "observed_traits": {"postpetiole_attachment": "dorsal_surface_first_gastral_segment"}}
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as tmp:
        for item in lines:
            tmp.write(json.dumps(item) + "\n")
        tmp_name = tmp.name
    yield tmp_name
    if os.path.exists(tmp_name):
        os.remove(tmp_name)


def test_load_observed_traits_sidecar_json(temp_sidecar_json):
    """Verifies that loading a JSON observed traits sidecar works correctly."""
    traits_map = load_observed_traits_sidecar(temp_sidecar_json)
    assert len(traits_map) == 2
    assert traits_map["casent0123456_profile"]["gaster_shape_dorsal"] == "heart_shaped"
    assert traits_map["casent0789101_profile"]["postpetiole_attachment"] == "dorsal_surface_first_gastral_segment"


def test_load_observed_traits_sidecar_jsonl(temp_sidecar_jsonl):
    """Verifies that loading a JSONL observed traits sidecar works correctly."""
    traits_map = load_observed_traits_sidecar(temp_sidecar_jsonl)
    assert len(traits_map) == 2
    assert traits_map["casent0123456_profile"]["postpetiole_attachment"] == "dorsal_surface_first_gastral_segment"
    assert traits_map["casent0789101_profile"]["postpetiole_attachment"] == "dorsal_surface_first_gastral_segment"


def test_load_observed_traits_sidecar_exceptions():
    """Verifies error handling for sidecars with missing paths, invalid syntax, or invalid keys."""
    # 1. Path is None -> returns empty dict
    assert load_observed_traits_sidecar(None) == {}

    # 2. File does not exist -> FileNotFoundError
    with pytest.raises(FileNotFoundError):
        load_observed_traits_sidecar("nonexistent_file_path.json")

    # 3. Invalid JSONL record (missing observed_traits) -> ValueError
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as tmp:
        tmp.write('{"image_id": "img1"}\n')
        tmp_name = tmp.name
    try:
        with pytest.raises(ValueError, match="observed_traits"):
            load_observed_traits_sidecar(tmp_name)
    finally:
        os.remove(tmp_name)


def test_evaluate_predictions_csv_no_observed_traits():
    """Verifies evaluation with no physical traits results in general insufficient evidence statuses."""
    kb_dir = "data/kb/poc_myrmicinae_mem"
    predictions_csv = "examples/kb/mock_predictions.csv"

    res = evaluate_predictions_csv_with_kb(
        kb_dir=kb_dir,
        predictions_csv=predictions_csv,
        top_k=3,
        observed_traits_path=None
    )

    assert "summary" in res
    assert "evidence_packets" in res
    
    summary = res["summary"]
    assert summary["total_records"] == 3
    assert summary["status_counts"]["insufficient_trait_evidence"] == 3
    assert summary["insufficient_trait_evidence_rate"] == 1.0
    assert summary["support_rate"] == 0.0
    assert summary["conflict_rate"] == 0.0
    
    # Check that it's JSON serializable
    dumped = json.dumps(res)
    assert isinstance(dumped, str)


def test_evaluate_predictions_csv_with_mock_sidecar(temp_sidecar_json):
    """Verifies that evaluator loads mock predictions, integrates sidecar traits, and aggregates correct statuses."""
    kb_dir = "data/kb/poc_myrmicinae_mem"
    predictions_csv = "examples/kb/mock_predictions.csv"

    res = evaluate_predictions_csv_with_kb(
        kb_dir=kb_dir,
        predictions_csv=predictions_csv,
        top_k=3,
        observed_traits_path=temp_sidecar_json
    )

    summary = res["summary"]
    assert summary["total_records"] == 3

    # Check status distribution:
    # 1. casent0123456_profile is supported (Crematogaster traits match Crematogaster) -> visual_top_supported_by_key
    # 2. casent0789101_profile is conflicted (Crematogaster traits conflict with Solenopsis) -> visual_top_conflicts_with_key
    # 3. casent0999999_profile is missing in sidecar -> insufficient_trait_evidence
    counts = summary["status_counts"]
    assert counts["visual_top_supported_by_key"] == 1
    assert counts["visual_top_conflicts_with_key"] == 1
    assert counts["insufficient_trait_evidence"] == 1

    assert summary["support_rate"] == pytest.approx(0.3333333333333333)
    assert summary["conflict_rate"] == pytest.approx(0.3333333333333333)
    assert summary["insufficient_trait_evidence_rate"] == pytest.approx(0.3333333333333333)

    # 4. Check missing trait aggregation. casent0999999_profile has missing traits.
    # It has some missing traits. Let's make sure the traits are counted.
    assert len(summary["most_common_missing_traits"]) > 0
    # First entry should be a dictionary with keys trait_id and count
    assert "trait_id" in summary["most_common_missing_traits"][0]
    assert "count" in summary["most_common_missing_traits"][0]

    # 5. Check conflicting rules aggregation. casent0789101_profile has conflicting rules with Solenopsis.
    # The rules 'mem_myrmicinae_001b' and 'mem_myrmicinae_006b' conflict.
    rules = [item["rule_id"] for item in summary["most_common_conflicting_rules"]]
    assert "mem_myrmicinae_001b" in rules
    assert "mem_myrmicinae_006b" in rules


def test_cli_evaluate_key_consistency(temp_sidecar_json):
    """Verifies that the cli evaluate-key-consistency subcommand runs successfully."""
    kb_dir = "data/kb/poc_myrmicinae_mem"
    predictions_csv = "examples/kb/mock_predictions.csv"

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as out_tmp:
        out_name = out_tmp.name

    try:
        class Args:
            def __init__(self):
                self.kb_dir = kb_dir
                self.predictions_csv = predictions_csv
                self.observed_traits = temp_sidecar_json
                self.output_json = out_name
                self.top_k = 3
                self.no_candidate_filter = False

        args = Args()
        code = run_evaluate_key_consistency(args)
        assert code == 0

        # Output JSON should exist and be parsable
        assert os.path.exists(out_name)
        with open(out_name, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "summary" in data
        assert "evidence_packets" in data
        assert len(data["evidence_packets"]) == 3
        # Check that the new fields are also in the JSON summary
        assert "meaningful_evidence_records" in data["summary"]
        assert "out_of_scope_candidate_records" in data["summary"]
    finally:
        if os.path.exists(out_name):
            os.remove(out_name)


def test_evaluate_predictions_refinements(temp_sidecar_json):
    """Verifies the refined key-consistency evaluator features:
    1. meaningful_evidence_records and meaningful_evidence_rate are correct.
    2. visual_key_top_agreement excludes insufficient_trait_evidence records.
    3. out_of_scope_candidate_records and out_of_scope_candidate_rate are correct.
    4. fallback evidence packets include evaluator_warning.
    """
    kb_dir = "data/kb/poc_myrmicinae_mem"
    predictions_csv = "examples/kb/mock_predictions.csv"

    res = evaluate_predictions_csv_with_kb(
        kb_dir=kb_dir,
        predictions_csv=predictions_csv,
        top_k=3,
        observed_traits_path=temp_sidecar_json
    )

    summary = res["summary"]
    packets = res["evidence_packets"]

    # 1. Verify meaningful evidence records and rates:
    # casent0123456_profile is supported (meaningful evidence)
    # casent0789101_profile is conflicted (meaningful evidence)
    # casent0999999_profile is unregistered candidate (fallback, has traits but handled as fallback)
    # Wait, does the unregistered candidate have traits? Yes, in temp_sidecar_json it is NOT included,
    # so its status is insufficient_trait_evidence.
    # Therefore, status counts has insufficient_trait_evidence = 1.
    # Total records = 3. So meaningful_evidence_records should be 3 - 1 = 2.
    assert summary["meaningful_evidence_records"] == 2
    assert summary["meaningful_evidence_rate"] == pytest.approx(2.0 / 3.0)

    # 2. Verify visual_key_top_agreement counting:
    # It should be 1 (casent0123456_profile where visual_top is Crematogaster, and key_top is Crematogaster)
    # casent0789101_profile has conflict (different top/conflicts)
    # casent0999999_profile has status insufficient_trait_evidence, so it is excluded.
    assert summary["visual_key_top_agreement_count"] == 1
    assert summary["visual_key_top_agreement_rate"] == pytest.approx(1.0 / 3.0)

    # 3. Verify out_of_scope_candidate_records:
    # casent0999999_profile predicts pheidole_dentata which is out-of-scope/unregistered.
    assert summary["out_of_scope_candidate_records"] == 1
    assert summary["out_of_scope_candidate_rate"] == pytest.approx(1.0 / 3.0)

    # 4. Verify evaluator_warning is present:
    # First packet (successful) should have evaluator_warning as None
    assert packets[0]["evaluator_warning"] is None
    # Third packet (fallback) should have evaluator_warning with proper fields
    fallback_pkt = packets[2]
    assert fallback_pkt["evaluator_warning"] is not None
    assert fallback_pkt["evaluator_warning"]["type"] == "out_of_scope_visual_candidate"
    assert "pheidole_dentata" in fallback_pkt["evaluator_warning"]["message"]

