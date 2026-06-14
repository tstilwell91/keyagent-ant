"""Unit tests for the knowledge base loader and validator (kb_loader.py)."""

import os
import json
import tempfile
import pytest
import yaml
from antid.keys.kb_loader import load_kb, get_couplet_base_id


def create_mock_kb_files(
    temp_dir: str,
    manifest: dict,
    traits: dict,
    taxa: dict,
    rules: dict,
):
    """Helper to write mock KB files to a temporary directory."""
    with open(os.path.join(temp_dir, "source_manifest.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(manifest, f)
    with open(os.path.join(temp_dir, "trait_schema.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(traits, f)
    with open(os.path.join(temp_dir, "taxon_registry.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(taxa, f)
    with open(os.path.join(temp_dir, "key_rules.json"), "w", encoding="utf-8") as f:
        json.dump(rules, f)


@pytest.fixture
def valid_kb_data():
    """Generates standard valid KB structures for testing."""
    manifest = {
        "source_id": "test_source",
        "name": "Test Source",
        "geographic_scope": "Global",
    }
    traits = {
        "traits": [
            {
                "trait_id": "antenna_segments",
                "name": "Antenna segments",
                "body_region": "antenna",
                "allowed_values": ["10", "11", "12"],
                "visible_in_views": ["head"],
            },
            {
                "trait_id": "gaster_shape",
                "name": "Gaster shape",
                "body_region": "gaster",
                "allowed_values": ["heart_shaped", "oval"],
                "visible_in_views": ["dorsal"],
            }
        ]
    }
    taxa = {
        "taxa": [
            {
                "taxon_id": "crematogaster",
                "scientific_name": "Crematogaster",
                "rank": "genus",
            },
            {
                "taxon_id": "solenopsis",
                "scientific_name": "Solenopsis",
                "rank": "genus",
            }
        ]
    }
    rules = {
        "source_id": "test_source",
        "rules": [
            {
                "rule_id": "rule_1a",
                "couplet": "1a",
                "conditions": [
                    {"trait_id": "gaster_shape", "operator": "equals", "value": "heart_shaped"}
                ],
                "terminal_taxon_id": "crematogaster",
                "next_couplet": None,
            },
            {
                "rule_id": "rule_1b",
                "couplet": "1b",
                "conditions": [
                    {"trait_id": "gaster_shape", "operator": "equals", "value": "oval"}
                ],
                "terminal_taxon_id": None,
                "next_couplet": "2",
            },
            {
                "rule_id": "rule_2a",
                "couplet": "2a",
                "conditions": [
                    {"trait_id": "antenna_segments", "operator": "equals", "value": "10"}
                ],
                "terminal_taxon_id": "solenopsis",
                "next_couplet": None,
            },
            {
                "rule_id": "rule_2b",
                "couplet": "2b",
                "conditions": [
                    {"trait_id": "antenna_segments", "operator": "equals", "value": "11"}
                ],
                "terminal_taxon_id": None,
                "next_couplet": "7",  # Whitelisted boundary
            }
        ]
    }
    return manifest, traits, taxa, rules


def test_get_couplet_base_id():
    """Verifies that trailing lowercase letters are stripped correctly."""
    assert get_couplet_base_id("1a") == "1"
    assert get_couplet_base_id("10b") == "10"
    assert get_couplet_base_id("1") == "1"
    assert get_couplet_base_id("abc") == ""


def test_valid_kb_loading(valid_kb_data):
    """Verifies that a valid KB loads without errors."""
    manifest, traits, taxa, rules = valid_kb_data
    with tempfile.TemporaryDirectory() as temp_dir:
        create_mock_kb_files(temp_dir, manifest, traits, taxa, rules)
        kb = load_kb(temp_dir)
        assert kb["valid_source_ids"] == {"test_source"}
        assert "antenna_segments" in kb["trait_ids"]
        assert "crematogaster" in kb["taxon_ids"]
        assert "1" in kb["couplets"]
        assert "2" in kb["couplets"]


def test_missing_required_file(valid_kb_data):
    """Verifies that FileNotFoundError is raised if any KB file is missing."""
    manifest, traits, taxa, rules = valid_kb_data
    with tempfile.TemporaryDirectory() as temp_dir:
        create_mock_kb_files(temp_dir, manifest, traits, taxa, rules)
        # Remove a file
        os.remove(os.path.join(temp_dir, "key_rules.json"))
        with pytest.raises(FileNotFoundError):
            load_kb(temp_dir)


def test_invalid_source_id_rule(valid_kb_data):
    """Verifies that rule source_id validation raises ValueError if source_id is invalid."""
    manifest, traits, taxa, rules = valid_kb_data
    # Set rule source_id to an unknown value
    rules["rules"][0]["source_id"] = "unknown_source"
    with tempfile.TemporaryDirectory() as temp_dir:
        create_mock_kb_files(temp_dir, manifest, traits, taxa, rules)
        with pytest.raises(ValueError, match="Rule .* references unknown source_id"):
            load_kb(temp_dir)


def test_invalid_operator(valid_kb_data):
    """Verifies that unallowed operators raise ValueError."""
    manifest, traits, taxa, rules = valid_kb_data
    # Change operator to an unsupported one
    rules["rules"][0]["conditions"][0]["operator"] = "greater_than"
    with tempfile.TemporaryDirectory() as temp_dir:
        create_mock_kb_files(temp_dir, manifest, traits, taxa, rules)
        with pytest.raises(ValueError, match="uses unallowed operator"):
            load_kb(temp_dir)


def test_mutual_exclusion_both(valid_kb_data):
    """Verifies rule violates mutual exclusion by specifying both terminal_taxon_id and next_couplet."""
    manifest, traits, taxa, rules = valid_kb_data
    rules["rules"][0]["next_couplet"] = "2"  # Set both
    with tempfile.TemporaryDirectory() as temp_dir:
        create_mock_kb_files(temp_dir, manifest, traits, taxa, rules)
        with pytest.raises(ValueError, match="violates mutual exclusion: defines both"):
            load_kb(temp_dir)


def test_mutual_exclusion_neither(valid_kb_data):
    """Verifies rule violates mutual exclusion by specifying neither terminal_taxon_id nor next_couplet."""
    manifest, traits, taxa, rules = valid_kb_data
    rules["rules"][0]["terminal_taxon_id"] = None
    rules["rules"][0]["next_couplet"] = None
    with tempfile.TemporaryDirectory() as temp_dir:
        create_mock_kb_files(temp_dir, manifest, traits, taxa, rules)
        with pytest.raises(ValueError, match="violates mutual exclusion: defines neither"):
            load_kb(temp_dir)


def test_duplicate_trait_id(valid_kb_data):
    """Verifies duplicate trait IDs in schema raise ValueError."""
    manifest, traits, taxa, rules = valid_kb_data
    traits["traits"].append({
        "trait_id": "antenna_segments",  # Duplicate
        "name": "Duplicate",
        "body_region": "antenna",
        "allowed_values": ["10"],
        "visible_in_views": ["head"],
    })
    with tempfile.TemporaryDirectory() as temp_dir:
        create_mock_kb_files(temp_dir, manifest, traits, taxa, rules)
        with pytest.raises(ValueError, match="Duplicate trait_id"):
            load_kb(temp_dir)


def test_unreachable_couplet(valid_kb_data):
    """Verifies unreachable couplets raise ValueError."""
    manifest, traits, taxa, rules = valid_kb_data
    # Add a couplet 3 that is never referenced by couplet 1 or 2
    rules["rules"].append({
        "rule_id": "rule_3a",
        "couplet": "3a",
        "conditions": [
            {"trait_id": "gaster_shape", "operator": "equals", "value": "oval"}
        ],
        "terminal_taxon_id": "solenopsis",
        "next_couplet": None,
    })
    with tempfile.TemporaryDirectory() as temp_dir:
        create_mock_kb_files(temp_dir, manifest, traits, taxa, rules)
        with pytest.raises(ValueError, match="Unreachable couplets detected"):
            load_kb(temp_dir)


def test_cyclic_couplet_path(valid_kb_data):
    """Verifies cyclic couplet paths raise ValueError."""
    manifest, traits, taxa, rules = valid_kb_data
    # Make couplet 2 point back to couplet 1
    rules["rules"][3]["next_couplet"] = "1"
    with tempfile.TemporaryDirectory() as temp_dir:
        create_mock_kb_files(temp_dir, manifest, traits, taxa, rules)
        with pytest.raises(ValueError, match="Cyclic couplet path detected"):
            load_kb(temp_dir)


def test_unknown_next_couplet_reference(valid_kb_data):
    """Verifies unknown next_couplet reference raises ValueError."""
    manifest, traits, taxa, rules = valid_kb_data
    # Change couplet 1b to point to non-existent couplet 99
    rules["rules"][1]["next_couplet"] = "99"
    with tempfile.TemporaryDirectory() as temp_dir:
        create_mock_kb_files(temp_dir, manifest, traits, taxa, rules)
        with pytest.raises(ValueError, match="unknown next_couplet reference '99'"):
            load_kb(temp_dir)
