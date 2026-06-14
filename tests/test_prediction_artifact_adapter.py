"""Unit and integration tests for the taxonomic predictions CSV artifact adapter."""

import os
import json
import tempfile
import pytest
from antid.keys.kb_loader import load_kb
from antid.keys.reasoning_adapter import build_reasoning_evidence_packet
from antid.keys.prediction_artifact_adapter import (
    classify_label_formatting,
    prediction_row_to_model_output,
    load_predictions_csv,
    convert_predictions_csv_to_model_outputs,
)
from antid.keys.cli import run_convert_predictions


def test_classify_label_formatting_heuristic():
    """Verifies correctness of the formatting-based label classification heuristic."""
    # 1. Contains space -> scientific_name
    assert classify_label_formatting("Solenopsis invicta") is True
    assert classify_label_formatting("crematogaster ashmeadi") is True

    # 2. Contains "_" and is lowercase -> taxon_id
    assert classify_label_formatting("solenopsis_invicta") is False
    assert classify_label_formatting("crematogaster_ashmeadi") is False

    # 3. Fully lowercase -> taxon_id
    assert classify_label_formatting("crematogaster") is False
    assert classify_label_formatting("solenopsis") is False

    # 4. Else -> scientific_name
    assert classify_label_formatting("Crematogaster") is True
    assert classify_label_formatting("Solenopsis") is True
    assert classify_label_formatting("Pheidole") is True


def test_prediction_row_to_model_output_scenarios():
    """Tests various prediction row conversion scenarios and fallback parsing logic."""
    # Scenario A: Standard columns
    row_standard = {
        "image_id": "img_a",
        "view_type": "dorsal",
        "top1_label": "Crematogaster",
        "top1_prob": "0.95",
        "top2_label": "solenopsis",
        "top2_prob": "0.05",
        "true_label": "crematogaster",
        "split": "test",
        "source": "antweb"
    }
    out = prediction_row_to_model_output(row_standard, top_k=2)
    assert out["image_id"] == "img_a"
    assert out["view_type"] == "dorsal"
    assert len(out["visual_candidates"]) == 2
    
    # Candidate 1: scientific_name
    assert out["visual_candidates"][0]["taxon_id"] is None
    assert out["visual_candidates"][0]["scientific_name"] == "Crematogaster"
    assert out["visual_candidates"][0]["score"] == 0.95
    assert out["visual_candidates"][0]["rank"] == 1

    # Candidate 2: taxon_id
    assert out["visual_candidates"][1]["taxon_id"] == "solenopsis"
    assert out["visual_candidates"][1]["scientific_name"] is None
    assert out["visual_candidates"][1]["score"] == 0.05
    assert out["visual_candidates"][1]["rank"] == 2

    assert out["observed_traits"] == {}
    assert out["metadata"]["true_label"] == "crematogaster"
    assert out["metadata"]["split"] == "test"
    assert out["metadata"]["top1_prob"] == 0.95

    # Scenario B: Image path fallback and view type inference
    row_fallback = {
        "image_path": "data/raw/images/crematogaster_ashmeadi/casent0123456_profile.jpg",
        "pred_label": "crematogaster_ashmeadi",
        "confidence": "0.88"
    }
    out_f = prediction_row_to_model_output(row_fallback, top_k=1)
    assert out_f["image_id"] == "casent0123456_profile"
    assert out_f["view_type"] == "profile"  # Inferred from filename keyword
    assert len(out_f["visual_candidates"]) == 1
    assert out_f["visual_candidates"][0]["taxon_id"] == "crematogaster_ashmeadi"
    assert out_f["visual_candidates"][0]["score"] == 0.88
    assert out_f["visual_candidates"][0]["rank"] == 1


def test_load_predictions_csv():
    """Verifies that loading the mock predictions CSV parses rows correctly."""
    csv_path = "examples/kb/mock_predictions.csv"
    assert os.path.exists(csv_path)

    rows = load_predictions_csv(csv_path)
    assert len(rows) == 3
    assert rows[0]["top1_label"] == "Crematogaster"
    assert rows[1]["top1_label"] == "solenopsis"
    assert rows[2]["pred_label"] == "pheidole_dentata"


def test_convert_predictions_csv_to_model_outputs():
    """Verifies bulk CSV-to-JSON-serializable-dict conversions."""
    csv_path = "examples/kb/mock_predictions.csv"
    converted = convert_predictions_csv_to_model_outputs(csv_path, top_k=3)
    assert len(converted) == 3

    # Check JSON serializability
    serialized = json.dumps(converted)
    deserialized = json.loads(serialized)
    assert len(deserialized) == 3


def test_cli_convert_predictions_subcommand():
    """Tests the convert-predictions subcommand CLI runner with a temp output file."""
    csv_path = "examples/kb/mock_predictions.csv"
    
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        output_json_path = f.name

    try:
        class Args:
            predictions_csv = csv_path
            output_json = output_json_path
            top_k = 3

        args = Args()
        assert run_convert_predictions(args) == 0

        # Load back and verify
        with open(output_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 3
        assert data[0]["image_id"] == "casent0123456_profile"
        assert data[0]["view_type"] == "profile"
    finally:
        if os.path.exists(output_json_path):
            os.remove(output_json_path)


def test_predictions_to_reasoning_integration():
    """Directly verifies the deterministic integration of prediction rows with the KB reasoner.

    Loads examples/kb/mock_predictions.csv, converts to model outputs, loads the actual POC KB,
    passes records to build_reasoning_evidence_packet(), and verifies correct validation/scoring.
    """
    csv_path = "examples/kb/mock_predictions.csv"
    kb_path = "data/kb/poc_myrmicinae_mem"
    assert os.path.exists(csv_path)
    assert os.path.exists(kb_path)

    converted_records = convert_predictions_csv_to_model_outputs(csv_path, top_k=5)
    assert len(converted_records) == 3

    # Load KB to verify load works
    kb = load_kb(kb_path)
    assert kb is not None

    # Integration Run 1: Row 1 (Crematogaster top prediction) with empty observed traits
    # Expected status: "insufficient_trait_evidence"
    rec_1 = converted_records[0]
    assert rec_1["image_id"] == "casent0123456_profile"
    assert rec_1["view_type"] == "profile"
    assert rec_1["observed_traits"] == {}

    packet_empty = build_reasoning_evidence_packet(kb_path, rec_1)
    assert packet_empty["agreement_summary"]["status"] == "insufficient_trait_evidence"
    assert packet_empty["agreement_summary"]["visual_top_taxon_id"] == "crematogaster"
    assert packet_empty["agreement_summary"]["key_top_taxon_id"] is None
    assert packet_empty["final_identification"] is None
    assert packet_empty["identification_decision_policy"] == "not_applied"

    # Integration Run 2: Pair Row 1 with supporting traits
    # Expected status: "visual_top_supported_by_key"
    rec_1_supported = dict(rec_1)
    rec_1_supported["observed_traits"] = {
        "postpetiole_attachment": "dorsal_surface_first_gastral_segment",
        "gaster_shape_dorsal": "heart_shaped",
        "petiole_node_state": "no_node_dorsoventrally_flattened"
    }
    packet_supported = build_reasoning_evidence_packet(kb_path, rec_1_supported)
    assert packet_supported["agreement_summary"]["status"] == "visual_top_supported_by_key"
    assert packet_supported["agreement_summary"]["visual_top_taxon_id"] == "crematogaster"
    assert packet_supported["agreement_summary"]["key_top_taxon_id"] == "crematogaster"
    assert packet_supported["agreement_summary"]["visual_top_raw_key_score"] == 1
    assert packet_supported["agreement_summary"]["visual_top_normalized_key_score"] == 1.0

    # Integration Run 3: Pair Row 2 (Solenopsis top prediction) with Crematogaster traits
    # Expected status: "visual_top_conflicts_with_key" (since Solenopsis conflicts with Crematogaster-specific rules)
    rec_2 = converted_records[1]
    assert rec_2["image_id"] == "casent0789101_profile"
    rec_2_conflicted = dict(rec_2)
    rec_2_conflicted["observed_traits"] = {
        "postpetiole_attachment": "dorsal_surface_first_gastral_segment",
        "gaster_shape_dorsal": "heart_shaped",
        "petiole_node_state": "no_node_dorsoventrally_flattened"
    }
    packet_conflicted = build_reasoning_evidence_packet(kb_path, rec_2_conflicted)
    assert packet_conflicted["agreement_summary"]["status"] == "visual_top_conflicts_with_key"
    assert packet_conflicted["agreement_summary"]["visual_top_taxon_id"] == "solenopsis"
    assert packet_conflicted["agreement_summary"]["key_top_taxon_id"] == "crematogaster"
    assert packet_conflicted["agreement_summary"]["visual_top_raw_key_score"] == -2
    assert len(packet_conflicted["conflict_summary"]) == 1
    assert packet_conflicted["conflict_summary"][0]["taxon_id"] == "solenopsis"
