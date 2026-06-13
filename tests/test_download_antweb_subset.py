import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import csv

from antid.data.download_antweb_subset import (
    parse_scientific_name,
    generate_filename,
    update_url,
    filter_and_sample_rows
)

# Test scientific name parsing (Task C)
def test_parse_scientific_name_basic():
    genus, species, folder = parse_scientific_name("Camponotus pennsylvanicus")
    assert genus == "Camponotus"
    assert species == "pennsylvanicus"
    assert folder == "camponotus_pennsylvanicus"

    genus, species, folder = parse_scientific_name("amblyopone_australis")
    assert genus == "Amblyopone"
    assert species == "australis"
    assert folder == "amblyopone_australis"


def test_parse_scientific_name_extra_tokens():
    # Keep only first two tokens
    genus, species, folder = parse_scientific_name("Camponotus pennsylvanicus sub_variety_author")
    assert genus == "Camponotus"
    assert species == "pennsylvanicus"
    assert folder == "camponotus_pennsylvanicus"


def test_parse_scientific_name_invalid():
    with pytest.raises(ValueError, match="cannot be empty"):
        parse_scientific_name("")
        
    with pytest.raises(ValueError, match="must have at least two tokens"):
        parse_scientific_name("Solitarytoken")


# Test filename generation (Task D)
def test_generate_filename_basic():
    # Normal case with catalog and shot_type
    filename = generate_filename("http://example.com/images/casent0123456_d_1_med.jpg", "casent0123456", "d", 2)
    assert filename == "casent0123456*d*2.jpg"


def test_generate_filename_missing_catalog_or_shot():
    # Missing catalog
    filename = generate_filename("http://example.com/images/foo.png", None, "p", 1)
    # Check it falls back to a deterministic hash
    assert filename.startswith("hash")
    assert "*p*1.png" in filename

    # Missing shot type
    filename = generate_filename("http://example.com/images/bar.JPG", "casent999", None, 3)
    assert filename == "casent999*unknown*3.jpg"


# Test URL updater
def test_update_url():
    assert update_url("http://www.antweb.org/images/foo.jpg") == "https://static.antweb.org/images/foo.jpg"
    assert update_url("https://www.antweb.org/images/bar.png") == "https://static.antweb.org/images/bar.png"
    assert update_url("https://already-static.org/test") == "https://already-static.org/test"


# Test filtering and deterministic sampling (Task E & H)
@pytest.fixture
def sample_rows():
    return [
        {"catalog_number": "cat1", "scientific_name": "Camponotus pennsylvanicus", "shot_type": "d", "image_url": "http://x.org/1.jpg", "caste": "worker"},
        {"catalog_number": "cat2", "scientific_name": "Camponotus pennsylvanicus", "shot_type": "h", "image_url": "http://x.org/2.jpg", "caste": "worker"},
        {"catalog_number": "cat3", "scientific_name": "Camponotus pennsylvanicus", "shot_type": "p", "image_url": "http://x.org/3.jpg", "caste": "queen"},
        {"catalog_number": "cat4", "scientific_name": "Formica rufa", "shot_type": "d", "image_url": "http://x.org/4.jpg", "caste": "worker"},
        {"catalog_number": "cat5", "scientific_name": "Formica rufa", "shot_type": "h", "image_url": "http://x.org/5.jpg", "caste": "male"},
        {"catalog_number": "cat6", "scientific_name": "Solenopsis invicta", "shot_type": "p", "image_url": "http://x.org/6.jpg", "caste": "worker"},
    ]


def test_filter_and_sample_no_limits(sample_rows):
    res = filter_and_sample_rows(sample_rows, seed=42)
    # All 3 unique species represented
    selected_species = set(item[3] for item in res)
    assert len(selected_species) == 3
    assert len(res) == 6


def test_filter_and_sample_species_limit(sample_rows):
    # Limit species to 2
    res = filter_and_sample_rows(sample_rows, seed=42, species_limit=2)
    selected_species = set(item[3] for item in res)
    assert len(selected_species) == 2


def test_filter_and_sample_per_species_limit(sample_rows):
    # Max 1 image per species
    res = filter_and_sample_rows(sample_rows, seed=42, per_species_limit=1)
    selected_species = [item[3] for item in res]
    # Total selected must be 3, each unique (1 per species)
    assert len(res) == 3
    assert len(set(selected_species)) == 3


def test_filter_and_sample_overall_limit(sample_rows):
    # Max total limit 2
    res = filter_and_sample_rows(sample_rows, seed=123, limit=2)
    assert len(res) == 2


def test_filter_and_sample_deterministic_seeding(sample_rows):
    # Seed 42 should always produce the exact same sequence
    res1 = filter_and_sample_rows(sample_rows, seed=42, limit=3)
    res2 = filter_and_sample_rows(sample_rows, seed=42, limit=3)
    res3 = filter_and_sample_rows(sample_rows, seed=999, limit=3)

    urls1 = [item[0]["image_url"] for item in res1]
    urls2 = [item[0]["image_url"] for item in res2]
    urls3 = [item[0]["image_url"] for item in res3]

    assert urls1 == urls2
    # Probability of different seed producing identical sequence is low
    assert urls1 != urls3


def test_filter_and_sample_shot_and_caste_filters(sample_rows):
    # Filter shot_type 'd' only
    res = filter_and_sample_rows(sample_rows, seed=42, shot_type_filter="d")
    assert len(res) == 2
    for r, _, _, _ in res:
        assert r["shot_type"] == "d"

    # Filter caste 'worker' only
    res = filter_and_sample_rows(sample_rows, seed=42, caste_filter="worker")
    assert len(res) == 4
    for r, _, _, _ in res:
        assert r["caste"] == "worker"
