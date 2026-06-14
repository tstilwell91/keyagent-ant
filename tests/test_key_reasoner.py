"""Unit tests for the taxonomic reasoning engine (key_reasoner.py)."""

import os
import tempfile
import pytest
from antid.keys.kb_loader import load_kb
from antid.keys.key_reasoner import KeyReasoner, reason_over_traits
from test_kb_loader import create_mock_kb_files, valid_kb_data


@pytest.fixture
def loaded_kb(valid_kb_data):
    """Loads a mock KB inside a temporary directory."""
    manifest, traits, taxa, rules = valid_kb_data
    with tempfile.TemporaryDirectory() as temp_dir:
        create_mock_kb_files(temp_dir, manifest, traits, taxa, rules)
        return load_kb(temp_dir)


def test_resolve_candidate_taxa(loaded_kb):
    """Verifies that candidate resolution handles taxon_ids and scientific names properly."""
    reasoner = KeyReasoner(loaded_kb)

    # 1. Direct taxon_id exact match (case-insensitive)
    assert reasoner.resolve_candidate_taxa(["crematogaster"]) == ["crematogaster"]
    assert reasoner.resolve_candidate_taxa(["Crematogaster"]) == ["crematogaster"]

    # 2. Scientific name match (case-insensitive alias)
    assert reasoner.resolve_candidate_taxa(["Crematogaster"]) == ["crematogaster"]

    # 3. Default (None) returns all registered taxon IDs
    assert reasoner.resolve_candidate_taxa(None) == ["crematogaster", "solenopsis"]

    # 4. Unknown raises ValueError
    with pytest.raises(ValueError, match="does not match any registered taxon_id"):
        reasoner.resolve_candidate_taxa(["non_existent_genus"])


def test_evaluate_rule_operators(loaded_kb):
    """Verifies correct evaluation of conditions using different operators."""
    reasoner = KeyReasoner(loaded_kb)

    # Rule structure to test
    rule_equals = {
        "conditions": [{"trait_id": "gaster_shape", "operator": "equals", "value": "heart_shaped"}]
    }
    rule_not_equals = {
        "conditions": [{"trait_id": "gaster_shape", "operator": "not_equals", "value": "heart_shaped"}]
    }
    rule_in = {
        "conditions": [{"trait_id": "antenna_segments", "operator": "in", "value": ["10", "11"]}]
    }
    rule_not_in = {
        "conditions": [{"trait_id": "antenna_segments", "operator": "not_in", "value": ["10", "11"]}]
    }

    # Test 'equals'
    assert reasoner.evaluate_rule(rule_equals, {"gaster_shape": "heart_shaped"}) == 1
    assert reasoner.evaluate_rule(rule_equals, {"gaster_shape": "oval"}) == -1
    assert reasoner.evaluate_rule(rule_equals, {}) == 0  # Unobserved

    # Test 'not_equals'
    assert reasoner.evaluate_rule(rule_not_equals, {"gaster_shape": "oval"}) == 1
    assert reasoner.evaluate_rule(rule_not_equals, {"gaster_shape": "heart_shaped"}) == -1
    assert reasoner.evaluate_rule(rule_not_equals, {}) == 0

    # Test 'in'
    assert reasoner.evaluate_rule(rule_in, {"antenna_segments": "10"}) == 1
    assert reasoner.evaluate_rule(rule_in, {"antenna_segments": "11"}) == 1
    assert reasoner.evaluate_rule(rule_in, {"antenna_segments": "12"}) == -1
    assert reasoner.evaluate_rule(rule_in, {}) == 0

    # Test 'not_in'
    assert reasoner.evaluate_rule(rule_not_in, {"antenna_segments": "12"}) == 1
    assert reasoner.evaluate_rule(rule_not_in, {"antenna_segments": "10"}) == -1
    assert reasoner.evaluate_rule(rule_not_in, {}) == 0


def test_deterministic_scoring_crematogaster(loaded_kb):
    """Verifies that reasoning calculates correct scores and rule categorizations for Crematogaster."""
    reasoner = KeyReasoner(loaded_kb)

    # Observed traits matching Crematogaster (Rule 1a)
    observed = {"gaster_shape": "heart_shaped"}

    result = reasoner.reason(observed)

    # Crematogaster has path: rule_1a
    # solenopsis has path: rule_1b -> rule_2a
    
    assert result["raw_scores"]["crematogaster"] == 1  # rule_1a matches (+1)
    assert result["normalized_scores"]["crematogaster"] == 1.0

    assert result["raw_scores"]["solenopsis"] == -1  # rule_1b fails (-1), rule_2a unobserved (0)
    assert result["normalized_scores"]["solenopsis"] == -0.5  # -1 / 2 rules

    assert "rule_1a" in result["supporting_rules"]["crematogaster"]
    assert "rule_1b" in result["conflicting_rules"]["solenopsis"]


def test_missing_and_unknown_traits(loaded_kb):
    """Verifies that missing and unknown traits are detected and categorized correctly."""
    reasoner = KeyReasoner(loaded_kb)

    # Partial observation with an unknown trait
    observed = {
        "gaster_shape": "oval",
        "extraneous_trait": "blue"
    }

    result = reasoner.reason(observed, view_type="head")

    # 1. Unknown trait check
    assert "extraneous_trait" in result["unknown_traits"]

    # 2. Missing trait is antenna_segments (needed by unresolved rule_2a on Solenopsis path)
    missing_list = result["missing_traits"]["all_missing"]
    assert len(missing_list) == 1
    assert missing_list[0]["trait_id"] == "antenna_segments"

    # 3. Categorized by view_type='head'
    # 'antenna_segments' is visible in head view
    assert len(result["missing_traits"]["relevant_to_current_view"]) == 1
    assert result["missing_traits"]["relevant_to_current_view"][0]["trait_id"] == "antenna_segments"
    assert len(result["missing_traits"]["other_views"]) == 0


def test_recommended_next_action_and_limitations(loaded_kb):
    """Verifies correct next action text and limitations formatting."""
    reasoner = KeyReasoner(loaded_kb)

    # All unobserved
    result = reasoner.reason({})
    
    # Highest scoring (tie) is crematogaster/solenopsis (score 0)
    # Crematogaster path has first unresolved rule_1a, which needs 'gaster_shape'
    assert "gaster shape" in result["recommended_next_action"].lower()

    # Verify limitations match source manifest
    assert result["limitations"]["geographic_scope"] == "Global"
