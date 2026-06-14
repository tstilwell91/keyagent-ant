"""Unit tests for the taxonomic reasoning integration adapter (reasoning_adapter.py)."""

import os
import json
import tempfile
import pytest
from unittest.mock import MagicMock
from antid.keys.kb_loader import load_kb
from antid.keys.key_reasoner import KeyReasoner
from antid.keys.evidence_schema import VisualCandidate, ModelEvidenceInput, ReasoningEvidencePacket
from antid.keys.reasoning_adapter import build_reasoning_evidence_packet
from antid.keys.cli import run_integrate
from test_kb_loader import create_mock_kb_files, valid_kb_data


@pytest.fixture
def loaded_kb_adapter(valid_kb_data):
    """Loads a mock KB inside a temporary directory."""
    manifest, traits, taxa, rules = valid_kb_data
    with tempfile.TemporaryDirectory() as temp_dir:
        create_mock_kb_files(temp_dir, manifest, traits, taxa, rules)
        yield temp_dir


def test_schema_validations():
    """Tests the defensive validation logic in evidence schemas."""
    # 1. VisualCandidate validation
    vc = VisualCandidate(taxon_id="crematogaster", scientific_name="Crematogaster", score=0.85, rank=1)
    vc.validate()  # Should pass

    # Score out of bounds
    with pytest.raises(ValueError, match="score '1.5' must be in the range"):
        VisualCandidate(taxon_id="crematogaster", scientific_name="Crematogaster", score=1.5, rank=1).validate()

    # Rank out of bounds
    with pytest.raises(ValueError, match="rank '0' must be >= 1"):
        VisualCandidate(taxon_id="crematogaster", scientific_name="Crematogaster", score=0.85, rank=0).validate()

    # Empty taxon representation
    with pytest.raises(ValueError, match="must specify either taxon_id or scientific_name"):
        VisualCandidate(taxon_id=None, scientific_name=None, score=0.5, rank=1).validate()

    # 2. ModelEvidenceInput validation
    valid_candidates = [VisualCandidate(taxon_id="crematogaster", scientific_name="Crematogaster", score=0.8, rank=1)]
    mei = ModelEvidenceInput(
        image_id="img_123",
        view_type="profile",
        visual_candidates=valid_candidates,
        observed_traits={},
        metadata={}
    )
    mei.validate()  # Should pass

    # Empty image_id
    with pytest.raises(ValueError, match="image_id is required"):
        ModelEvidenceInput(
            image_id="",
            view_type="profile",
            visual_candidates=valid_candidates,
            observed_traits={},
            metadata={}
        ).validate()

    # Invalid visual candidates list
    with pytest.raises(ValueError, match="visual_candidates must be a non-empty list"):
        ModelEvidenceInput(
            image_id="img_123",
            view_type="profile",
            visual_candidates=[],
            observed_traits={},
            metadata={}
        ).validate()


def test_adapter_missing_required_fields(loaded_kb_adapter):
    """Verifies build_reasoning_evidence_packet checks required fields in input dict."""
    with pytest.raises(ValueError, match="missing required field 'visual_candidates'"):
        build_reasoning_evidence_packet(loaded_kb_adapter, {"image_id": "img", "observed_traits": {}, "metadata": {}})


def test_adapter_insufficient_evidence(loaded_kb_adapter):
    """Verifies classification as insufficient_trait_evidence if traits are empty or no rules trigger."""
    model_output = {
        "image_id": "img_123",
        "view_type": "profile",
        "visual_candidates": [
            {"taxon_id": "crematogaster", "scientific_name": "Crematogaster", "score": 0.9, "rank": 1}
        ],
        "observed_traits": {},
        "metadata": {}
    }

    result = build_reasoning_evidence_packet(loaded_kb_adapter, model_output)
    
    assert result["agreement_summary"]["status"] == "insufficient_trait_evidence"
    assert result["agreement_summary"]["visual_top_taxon_id"] == "crematogaster"
    assert result["agreement_summary"]["key_top_taxon_id"] is None
    assert result["final_identification"] is None
    assert result["identification_decision_policy"] == "not_applied"


def test_adapter_visual_top_supported(loaded_kb_adapter):
    """Verifies visual_top_supported_by_key scenario."""
    model_output = {
        "image_id": "img_123",
        "view_type": "dorsal",
        "visual_candidates": [
            {"taxon_id": "crematogaster", "scientific_name": "Crematogaster", "score": 0.9, "rank": 1},
            {"taxon_id": "solenopsis", "scientific_name": "Solenopsis", "score": 0.1, "rank": 2}
        ],
        "observed_traits": {
            "gaster_shape": "heart_shaped"
        },
        "metadata": {}
    }

    result = build_reasoning_evidence_packet(loaded_kb_adapter, model_output)
    
    assert result["agreement_summary"]["status"] == "visual_top_supported_by_key"
    assert result["agreement_summary"]["visual_top_taxon_id"] == "crematogaster"
    assert result["agreement_summary"]["key_top_taxon_id"] == "crematogaster"
    assert result["agreement_summary"]["visual_top_raw_key_score"] == 1
    assert result["agreement_summary"]["visual_top_normalized_key_score"] == 1.0
    assert result["recommended_next_action"]["action_type"] == "none"


def test_adapter_visual_top_conflicts(loaded_kb_adapter):
    """Verifies visual_top_conflicts_with_key scenario."""
    model_output = {
        "image_id": "img_123",
        "view_type": "dorsal",
        "visual_candidates": [
            {"taxon_id": "crematogaster", "scientific_name": "Crematogaster", "score": 0.9, "rank": 1},
            {"taxon_id": "solenopsis", "scientific_name": "Solenopsis", "score": 0.1, "rank": 2}
        ],
        "observed_traits": {
            "gaster_shape": "oval"  # Conflicts with Crematogaster (rule_1a), supports Solenopsis path (rule_1b)
        },
        "metadata": {}
    }

    result = build_reasoning_evidence_packet(loaded_kb_adapter, model_output)
    
    assert result["agreement_summary"]["status"] == "visual_top_conflicts_with_key"
    assert result["agreement_summary"]["visual_top_taxon_id"] == "crematogaster"
    assert result["agreement_summary"]["key_top_taxon_id"] == "solenopsis"  # Since rule_1b matched
    
    # Conflict summary should include Crematogaster since its score is < 0
    assert len(result["conflict_summary"]) == 1
    assert result["conflict_summary"][0]["taxon_id"] == "crematogaster"
    assert "rule_1a" in result["conflict_summary"][0]["conflicting_rules"]


def test_adapter_key_prefers_different(loaded_kb_adapter):
    """Verifies key_prefers_different_taxon scenario."""
    model_output = {
        "image_id": "img_123",
        "view_type": "head",
        "visual_candidates": [
            {"taxon_id": "crematogaster", "scientific_name": "Crematogaster", "score": 0.9, "rank": 1},
            {"taxon_id": "solenopsis", "scientific_name": "Solenopsis", "score": 0.1, "rank": 2}
        ],
        "observed_traits": {
            "antenna_segments": "10"  # Solenopsis is supported, Crematogaster is unresolved but not conflicted
        },
        "metadata": {}
    }

    result = build_reasoning_evidence_packet(loaded_kb_adapter, model_output)
    
    assert result["agreement_summary"]["status"] == "key_prefers_different_taxon"
    assert result["agreement_summary"]["visual_top_taxon_id"] == "crematogaster"
    assert result["agreement_summary"]["key_top_taxon_id"] == "solenopsis"


def test_deterministic_tie_breaking(loaded_kb_adapter):
    """Verifies that ties are broken deterministically by taxon_id (alphabetical) and status is visual_top_tied_for_key_top."""
    model_output = {
        "image_id": "img_123",
        "view_type": "head",
        "visual_candidates": [
            {"taxon_id": "solenopsis", "scientific_name": "Solenopsis", "score": 0.7, "rank": 1},
            {"taxon_id": "crematogaster", "scientific_name": "Crematogaster", "score": 0.3, "rank": 2}
        ],
        "observed_traits": {
            # Neither rule_1a nor rule_1b is supported (unobserved 'gaster_shape').
            # Both crematogaster and solenopsis have raw_score=0, normalized_score=0.
            # This is a tie!
            # Since observed_traits is not empty, and we have unresolved rules (wait, but we need has_any_resolution to be True for it not to be insufficient_evidence).
            # Wait, let's look at has_any_resolution logic:
            # any(len(supporting_rules) > 0 or len(conflicting_rules) > 0)
            # Let's add a trait that resolves some other rule, or let's check.
            # Let's supply antenna_segments = "10". This supports rule_2a (Solenopsis) but rule_1b is unobserved.
            # Wait, let's look at rule_1b. If gaster_shape is unobserved, rule_1b has state 0 (unresolved).
            # But rule_2a has state 1 (supported).
            # If so, solenopsis score is +1 (rule_2a) and 0 (rule_1b) -> total 1.
            # Crematogaster has rule_1a (unresolved) -> total 0.
            # What if we want a tie where both have scores > 0?
            # Let's add another trait, or let's make sure has_any_resolution is True.
            # If we pass gaster_shape = "heart_shaped" (supports crematogaster) AND antenna_segments = "10" (supports solenopsis, but solenopsis path rule_1b is conflicted).
            # If solenopsis path rule_1b is conflicted, its score is -1 + 1 = 0.
            # Let's see. If we have a rule rule_3a terminal taxon A, rule_3b terminal taxon B, both triggered by the same trait?
            # Yes! Let's mock a simple KB where both taxa have the same scores.
        },
        "metadata": {}
    }
    
    # Let's construct a custom simple KB with two taxa having identical scores.
    manifest = {
        "source_id": "tie_source",
        "name": "Tie Source",
        "geographic_scope": "Global",
    }
    traits = {
        "traits": [
            {
                "trait_id": "some_trait",
                "name": "Some Trait",
                "body_region": "gaster",
                "allowed_values": ["yes", "no"],
                "visible_in_views": ["dorsal"],
            }
        ]
    }
    taxa = {
        "taxa": [
            {"taxon_id": "z_taxon", "scientific_name": "Z Taxon", "rank": "genus"},
            {"taxon_id": "a_taxon", "scientific_name": "A Taxon", "rank": "genus"}
        ]
    }
    rules = {
        "source_id": "tie_source",
        "rules": [
            {
                "rule_id": "rule_z",
                "couplet": "1a",
                "conditions": [{"trait_id": "some_trait", "operator": "equals", "value": "yes"}],
                "terminal_taxon_id": "z_taxon",
                "next_couplet": None,
            },
            {
                "rule_id": "rule_a",
                "couplet": "1b",
                "conditions": [{"trait_id": "some_trait", "operator": "equals", "value": "yes"}],
                "terminal_taxon_id": "a_taxon",
                "next_couplet": None,
            }
        ]
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        create_mock_kb_files(temp_dir, manifest, traits, taxa, rules)
        
        # Scenario 1: visual top is z_taxon. Z and A have identical scores of +1.
        # Alphabetically, a_taxon must be sorted first, so key_top_taxon_id is a_taxon.
        # But z_taxon is tied for the top score, so status must be visual_top_tied_for_key_top.
        model_output = {
            "image_id": "img_123",
            "view_type": "dorsal",
            "visual_candidates": [
                {"taxon_id": "z_taxon", "scientific_name": "Z Taxon", "score": 0.8, "rank": 1},
                {"taxon_id": "a_taxon", "scientific_name": "A Taxon", "score": 0.2, "rank": 2}
            ],
            "observed_traits": {"some_trait": "yes"},
            "metadata": {}
        }
        
        result = build_reasoning_evidence_packet(temp_dir, model_output)
        
        # Verify sorted list of ranked_taxa
        ranked_taxa = result["key_reasoning"]["ranked_taxa"]
        # a_taxon has ID "a_taxon", z_taxon has ID "z_taxon".
        # Due to tie-breaking, a_taxon must be rank 1 in ranked_taxa.
        assert ranked_taxa[0]["taxon_id"] == "a_taxon"
        assert ranked_taxa[1]["taxon_id"] == "z_taxon"
        
        assert result["agreement_summary"]["status"] == "visual_top_tied_for_key_top"
        assert result["agreement_summary"]["visual_top_taxon_id"] == "z_taxon"
        assert result["agreement_summary"]["key_top_taxon_id"] == "a_taxon"


def test_cli_integration_subcommand(loaded_kb_adapter):
    """Tests running the integrate subcommand via the CLI module helper."""
    # Write a mock model output to temp file
    model_output = {
        "image_id": "img_cli_test",
        "view_type": "dorsal",
        "visual_candidates": [
            {"taxon_id": "crematogaster", "scientific_name": "Crematogaster", "score": 0.95, "rank": 1}
        ],
        "observed_traits": {
            "gaster_shape": "heart_shaped"
        },
        "metadata": {"test": "cli"}
    }
    
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(model_output, f)
        model_file_path = f.name

    try:
        class Args:
            kb_dir = loaded_kb_adapter
            model_output = model_file_path
            no_candidate_filter = False

        args = Args()
        # Verify run_integrate succeeds (returns 0)
        assert run_integrate(args) == 0
    finally:
        os.remove(model_file_path)
