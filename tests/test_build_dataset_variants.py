import csv
import os
import tempfile
import pytest
from pathlib import Path

from antid.data.build_dataset_variants import (
    parse_scientific_name,
    normalize_image_url,
    map_shot_to_view_type,
    parse_legacy_csv,
    build_dataset_variants,
    validate_manifest,
    check_split_leakage,
)

# Tiny synthetic legacy CSV data
TINY_LEGACY_CSV_CONTENT = """catalog_number;scientific_name;shot_type;image_url;state;caste;caste_big;source
casent001;camponotus_maculatus;d;http://www.antweb.org/images/casent001/casent001_d_1_med.jpg;ok;w;worker;antweb
casent001;camponotus_maculatus;h;http://www.antweb.org/images/casent001/casent001_h_1_med.jpg;ok;w;worker;antweb
casent001;camponotus_maculatus;p;http://www.antweb.org/images/casent001/casent001_p_1_med.jpg;ok;w;worker;antweb
casent002;camponotus_maculatus;d;http://www.antweb.org/images/casent002/casent002_d_1_med.jpg;ok;w;worker;antweb
casent002;camponotus_maculatus;h;http://www.antweb.org/images/casent002/casent002_h_1_med.jpg;ok;w;worker;antweb
casent002;camponotus_maculatus;p;http://www.antweb.org/images/casent002/casent002_p_1_med.jpg;ok;w;worker;antweb
casent003;camponotus_maculatus;d;http://www.antweb.org/images/casent003/casent003_d_1_med.jpg;ok;dQ;queen;antweb
casent003;camponotus_maculatus;h;http://www.antweb.org/images/casent003/casent003_h_1_med.jpg;ok;dQ;queen;antweb
casent004;pheidole_megacephala;d;http://www.antweb.org/images/casent004/casent004_d_1_med.jpg;ok;w;worker;antweb
casent004;pheidole_megacephala;h;http://www.antweb.org/images/casent004/casent004_h_1_med.jpg;ok;w;worker;antweb
casent004;pheidole_megacephala;p;http://www.antweb.org/images/casent004/casent004_p_1_med.jpg;ok;w;worker;antweb
casent005;pheidole_megacephala;d;http://www.antweb.org/images/casent005/casent005_d_1_med.jpg;ok;w;worker;antweb
"""


def test_parse_scientific_name():
    genus, species = parse_scientific_name("Camponotus_maculatus")
    assert genus == "Camponotus"
    assert species == "maculatus"

    genus, species = parse_scientific_name("pheidole megacephala var_1")
    assert genus == "Pheidole"
    assert species == "megacephala"

    with pytest.raises(ValueError):
        parse_scientific_name("Camponotus")


def test_normalize_image_url():
    url = "http://www.antweb.org/images/casent0123/casent0123_d_1_med.jpg"
    normalized = normalize_image_url(url)
    assert normalized == "https://static.antweb.org/images/casent0123/casent0123_d_1_med.jpg"

    url_https = "https://antweb.org/images/casent0123/casent0123_d_1_med.jpg"
    normalized_https = normalize_image_url(url_https)
    assert normalized_https == "https://static.antweb.org/images/casent0123/casent0123_d_1_med.jpg"


def test_map_shot_to_view_type():
    assert map_shot_to_view_type("d") == "dorsal"
    assert map_shot_to_view_type("h") == "head"
    assert map_shot_to_view_type("p") == "profile"
    assert map_shot_to_view_type("x") == "unknown"


def test_parse_legacy_csv():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as tmp:
        tmp.write(TINY_LEGACY_CSV_CONTENT)
        tmp_name = tmp.name

    try:
        records = parse_legacy_csv(tmp_name)
        assert len(records) == 12  # All rows are valid and parseable
        assert records[0]["catalog_number"] == "casent001"
        assert records[0]["genus"] == "Camponotus"
        assert records[0]["species"] == "maculatus"
        assert records[0]["view_type"] == "dorsal"
        assert records[0]["caste"] == "worker"
        assert records[0]["image_url"].startswith("https://static.antweb.org/")
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def test_build_dataset_variants():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as tmp_in:
        tmp_in.write(TINY_LEGACY_CSV_CONTENT)
        tmp_in_name = tmp_in.name

    with tempfile.TemporaryDirectory() as tmp_out_dir:
        try:
            build_dataset_variants(tmp_in_name, tmp_out_dir, seed=42)

            v1_orig = Path(tmp_out_dir) / "v1_original_manifest.csv"
            v1_spec = Path(tmp_out_dir) / "v1_specimen_aware_manifest.csv"
            v2_cur = Path(tmp_out_dir) / "v2_curated_manifest.csv"

            assert v1_orig.exists()
            assert v1_spec.exists()
            assert v2_cur.exists()

            # Verify v1-original content (keeps all valid rows)
            with open(v1_orig, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                assert len(rows) == 12

            # Verify v2-curated:
            # - worker-only
            # - complete tri-view specimens only
            with open(v2_cur, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                
                # Let's see:
                # Specimens:
                # casent001: worker, has d, h, p -> complete! (3 rows)
                # casent002: worker, has d, h, p -> complete! (3 rows)
                # casent003: queen, has d, h -> skipped (queen)
                # casent004: worker, has d, h, p -> complete! (3 rows)
                # casent005: worker, has d only -> skipped (incomplete)
                # Total expected rows in v2: 3 + 3 + 3 = 9 rows (specimens: casent001, casent002, casent004)
                assert len(rows) == 9
                
                castes = set(r["caste"] for r in rows)
                assert castes == {"worker"}
                
                specimens = set(r["specimen_id"] for r in rows)
                assert specimens == {"casent001", "casent002", "casent004"}
                
                # Check that for each specimen we have exactly d, h, p
                for spec in specimens:
                    spec_rows = [r for r in rows if r["specimen_id"] == spec]
                    assert len(spec_rows) == 3
                    views = set(r["view_type"] for r in spec_rows)
                    assert views == {"dorsal", "head", "profile"}

            # Validate manifests
            assert validate_manifest(v1_orig, is_v2=False)
            assert validate_manifest(v1_spec, is_v2=False)
            assert validate_manifest(v2_cur, is_v2=True)

        finally:
            if os.path.exists(tmp_in_name):
                os.remove(tmp_in_name)


def test_capping_and_determinism():
    # Construct a dataset with 5 complete specimens for the same species
    # and verify that capping works and is deterministic.
    data_lines = ["catalog_number;scientific_name;shot_type;image_url;state;caste;caste_big;source"]
    for i in range(1, 6):
        for view in ["d", "h", "p"]:
            data_lines.append(f"casent00{i};camponotus_maculatus;{view};http://www.antweb.org/images/casent00{i}/casent00{i}_{view}_1_med.jpg;ok;w;worker;antweb")

    csv_content = "\n".join(data_lines)

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as tmp_in:
        tmp_in.write(csv_content)
        tmp_in_name = tmp_in.name

    with tempfile.TemporaryDirectory() as tmp_out_dir:
        try:
            # Let's run build with a cap of 30, but wait, the cap is 30 in build_dataset_variants.
            # If we want to test capping, let's make sure the capping logic itself works on a larger scale,
            # or we can test that the selection is deterministic under multiple runs with the same seed.
            build_dataset_variants(tmp_in_name, tmp_out_dir, seed=42)
            v2_path = Path(tmp_out_dir) / "v2_curated_manifest.csv"
            
            with open(v2_path, mode="r", newline="", encoding="utf-8") as f:
                rows1 = list(csv.DictReader(f))

            # Run again with same seed, should be identical
            build_dataset_variants(tmp_in_name, tmp_out_dir, seed=42)
            with open(v2_path, mode="r", newline="", encoding="utf-8") as f:
                rows2 = list(csv.DictReader(f))

            assert rows1 == rows2

            # Run with a different seed, might result in a different shuffled order (if we capped, but since count is 5 which is <= 30, it retains all 5)
            # To test cap of 30, we could generate 35 specimens and assert v2 retains exactly 30 specimens (90 rows).
            # Let's do that!
            data_lines_large = ["catalog_number;scientific_name;shot_type;image_url;state;caste;caste_big;source"]
            for i in range(1, 40):
                for view in ["d", "h", "p"]:
                    data_lines_large.append(f"casent{i:03d};camponotus_maculatus;{view};http://www.antweb.org/images/casent{i:03d}/casent{i:03d}_{view}_1_med.jpg;ok;w;worker;antweb")

            csv_content_large = "\n".join(data_lines_large)
            with open(tmp_in_name, "w") as f_large:
                f_large.write(csv_content_large)

            build_dataset_variants(tmp_in_name, tmp_out_dir, seed=42)
            with open(v2_path, mode="r", newline="", encoding="utf-8") as f:
                rows_capped = list(csv.DictReader(f))
            
            # Should have exactly 30 specimens * 3 views = 90 rows!
            assert len(rows_capped) == 90
            
            # Ensure specimens are capped
            spec_ids = set(r["specimen_id"] for r in rows_capped)
            assert len(spec_ids) == 30

        finally:
            if os.path.exists(tmp_in_name):
                os.remove(tmp_in_name)
