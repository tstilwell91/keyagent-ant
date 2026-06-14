import csv
import json
import os
import yaml
import pytest
from pathlib import Path
from antid.keys.trait_visibility_audit import run_trait_visibility_audit
from antid.keys.cli import main


@pytest.fixture
def synthetic_kb_and_selection(tmp_path):
    """Sets up a complete synthetic KB, selection CSV, template JSONL, and mock image files."""
    kb_dir = tmp_path / "mock_kb"
    kb_dir.mkdir()

    # 1. source_manifest.yaml
    manifest = {
        "source_id": "mock_key",
        "sources": [
            {"source_id": "mock_key", "name": "Mock Taxonomic Key"}
        ]
    }
    with open(kb_dir / "source_manifest.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(manifest, f)

    # 2. trait_schema.yaml
    trait_schema = {
        "traits": [
            {
                "trait_id": "mock_trait_1",
                "name": "Mock Trait 1",
                "body_region": "head",
                "allowed_values": ["present", "absent"],
                "visible_in_views": ["head"]
            },
            {
                "trait_id": "mock_trait_2",
                "name": "Mock Trait 2",
                "body_region": "gaster",
                "allowed_values": ["round", "oval"],
                "visible_in_views": ["dorsal", "profile"]
            },
            {
                "trait_id": "mock_trait_3",
                "name": "Mock Trait 3",
                "body_region": "leg",
                "allowed_values": ["hairy"],
                "visible_in_views": []  # missing view metadata on purpose!
            }
        ]
    }
    with open(kb_dir / "trait_schema.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(trait_schema, f)

    # 3. taxon_registry.yaml
    taxon_registry = {
        "taxa": [
            {"taxon_id": "mock_taxon_a", "scientific_name": "Mock taxon A", "rank": "genus"},
            {"taxon_id": "mock_taxon_b", "scientific_name": "Mock taxon B", "rank": "genus"}
        ]
    }
    with open(kb_dir / "taxon_registry.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(taxon_registry, f)

    # 4. key_rules.json
    key_rules = {
        "source_id": "mock_key",
        "rules": [
            {
                "rule_id": "rule_1",
                "couplet": "1a",
                "conditions": [
                    {"trait_id": "mock_trait_1", "operator": "equals", "value": "present"}
                ],
                "terminal_taxon_id": "mock_taxon_a",
                "next_couplet": None,
                "required_views": ["head"],
                "body_regions": ["head"]
            },
            {
                "rule_id": "rule_2",
                "couplet": "1b",
                "conditions": [
                    {"trait_id": "mock_trait_1", "operator": "equals", "value": "absent"}
                ],
                "terminal_taxon_id": "mock_taxon_b",
                "next_couplet": None,
                "required_views": ["head"],
                "body_regions": ["head"]
            }
        ]
    }
    with open(kb_dir / "key_rules.json", "w", encoding="utf-8") as f:
        json.dump(key_rules, f)

    # Images directory
    image_root = tmp_path / "images_root"
    image_root.mkdir()

    # Create real (empty) image files for spec_1
    spec1_dir = image_root / "spec_1"
    spec1_dir.mkdir()
    # Tiny valid 1x1 GIF bytes (Pillow can open this despite .jpg extension)
    gif_bytes = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
    with open(spec1_dir / "d.jpg", "wb") as f:
        f.write(gif_bytes)
    with open(spec1_dir / "h.jpg", "wb") as f:
        f.write(gif_bytes)
    with open(spec1_dir / "p.jpg", "wb") as f:
        f.write(gif_bytes)


    # We do NOT create files for spec_2 (missing files test)
    # We do NOT create profile path for spec_2 (missing path test)

    # Selection CSV
    selection_csv = tmp_path / "selection.csv"
    with open(selection_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "specimen_id", "catalog_number", "kb_taxon_id", "kb_scientific_name",
            "dataset_genus", "dataset_species", "source_split",
            "dorsal_image_path", "head_image_path", "profile_image_path",
            "duplicate_view_counts"
        ])
        writer.writerow([
            "spec_1", "spec_1", "mock_taxon_a", "Mock taxon A",
            "Mock", "a", "test",
            "spec_1/d.jpg", "spec_1/h.jpg", "spec_1/p.jpg",
            "dorsal:1,head:1,profile:1"
        ])
        writer.writerow([
            "spec_2", "spec_2", "mock_taxon_a", "Mock taxon A",
            "Mock", "a", "test",
            "spec_2/d.jpg", "spec_2/h.jpg", "",  # missing profile path
            "dorsal:1,head:1"
        ])

    # Template JSONL
    template_jsonl = tmp_path / "template.jsonl"
    with open(template_jsonl, "w", encoding="utf-8") as f:
        f.write(json.dumps({"specimen_id": "spec_1", "catalog_number": "spec_1"}) + "\n")
        f.write(json.dumps({"specimen_id": "spec_2", "catalog_number": "spec_2"}) + "\n")

    output_dir = tmp_path / "audit_output"

    return {
        "kb_dir": str(kb_dir),
        "selection_csv": str(selection_csv),
        "template_jsonl": str(template_jsonl),
        "image_root": str(image_root),
        "output_dir": str(output_dir)
    }


def test_trait_visibility_audit_full(synthetic_kb_and_selection):
    """Tests the full audit flow with our mock key and files."""
    summary = run_trait_visibility_audit(
        kb_dir=synthetic_kb_and_selection["kb_dir"],
        selection_csv=synthetic_kb_and_selection["selection_csv"],
        annotation_template_jsonl=synthetic_kb_and_selection["template_jsonl"],
        image_root=synthetic_kb_and_selection["image_root"],
        output_dir=synthetic_kb_and_selection["output_dir"]
    )

    # 1. Verify summary output structure and metrics
    assert summary["status"] == "success"
    assert summary["selected_specimens"] == 2
    assert summary["selected_taxa"] == 1  # Only mock_taxon_a represented
    assert summary["kb_trait_count"] == 3
    assert summary["kb_rule_count"] == 2
    assert summary["traits_used_in_rules"] == 1  # mock_trait_1 is used
    assert summary["traits_not_used_in_rules"] == 2  # mock_trait_2 & 3 not used
    assert summary["traits_with_view_metadata"] == 2  # mock_trait_1 & 2
    assert summary["traits_missing_view_metadata"] == 1  # mock_trait_3
    assert summary["specimens_ready"] == 1  # spec_1 is ready
    assert summary["specimens_missing_files"] == 0  # spec_2 is classified as missing_image_path (takes precedence!)

    # 2. Check specimen_image_readiness.csv
    spec_csv_path = Path(synthetic_kb_and_selection["output_dir"]) / "specimen_image_readiness.csv"
    assert spec_csv_path.exists()

    with open(spec_csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 2
    assert rows[0]["specimen_id"] == "spec_1"
    assert rows[0]["readiness_status"] == "ready"
    assert rows[0]["dorsal_exists"] == "true"
    assert rows[0]["head_exists"] == "true"
    assert rows[0]["profile_exists"] == "true"
    assert rows[0]["all_views_present"] == "true"
    assert rows[0]["all_view_files_exist"] == "true"

    assert rows[1]["specimen_id"] == "spec_2"
    assert rows[1]["readiness_status"] == "missing_image_path"
    assert rows[1]["all_views_present"] == "false"

    # 3. Check trait_schema_readiness.csv
    trait_csv_path = Path(synthetic_kb_and_selection["output_dir"]) / "trait_schema_readiness.csv"
    assert trait_csv_path.exists()

    with open(trait_csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        trait_rows = {r["trait_id"]: r for r in reader}

    assert len(trait_rows) == 3
    assert trait_rows["mock_trait_1"]["schema_readiness_status"] == "ready_for_visibility_mapping"
    assert trait_rows["mock_trait_1"]["used_in_key_rules"] == "true"
    assert trait_rows["mock_trait_1"]["key_rule_ids"] == "rule_1, rule_2"
    assert "mock_taxon_a" in trait_rows["mock_trait_1"]["affected_taxa"]
    assert "mock_taxon_b" in trait_rows["mock_trait_1"]["affected_taxa"]

    assert trait_rows["mock_trait_2"]["schema_readiness_status"] == "not_used_in_current_key"
    assert trait_rows["mock_trait_2"]["used_in_key_rules"] == "false"

    assert trait_rows["mock_trait_3"]["schema_readiness_status"] == "missing_view_metadata"

    # 4. Check specimen_trait_visibility_matrix.csv
    matrix_csv_path = Path(synthetic_kb_and_selection["output_dir"]) / "specimen_trait_visibility_matrix.csv"
    assert matrix_csv_path.exists()

    with open(matrix_csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        matrix_rows = list(reader)

    # 2 specimens * 3 traits = 6 rows
    assert len(matrix_rows) == 6

    # Verify that matrix never assigns physical morphological trait values!
    for row in matrix_rows:
        # Check that there are no columns containing trait values
        assert "value" not in row
        assert "observed_value" not in row
        assert "trait_value" not in row

    # Group matrix rows by specimen_id and trait_id
    grouped_matrix = {(r["specimen_id"], r["trait_id"]): r for r in matrix_rows}

    # spec_1 with mock_trait_1 (expected: head, spec has head): ready_for_image_review
    m1 = grouped_matrix[("spec_1", "mock_trait_1")]
    assert m1["visibility_status"] == "ready_for_image_review"
    assert m1["review_recommendation"] == "inspect_head"
    assert "spec_1/h.jpg" in m1["usable_image_paths"]

    # spec_2 with mock_trait_1 (expected: head, spec_2's head file doesn't exist on disk): missing_required_view
    m2 = grouped_matrix[("spec_2", "mock_trait_1")]
    assert m2["visibility_status"] == "missing_required_view"
    assert m2["review_recommendation"] == "expert_review_needed"

    # spec_1 with mock_trait_2 (expected: dorsal, profile; not used in rules): not_used_in_current_key
    m3 = grouped_matrix[("spec_1", "mock_trait_2")]
    assert m3["visibility_status"] == "not_used_in_current_key"
    assert m3["review_recommendation"] == "defer"

    # spec_1 with mock_trait_3 (missing view metadata): schema_missing_view_metadata
    m4 = grouped_matrix[("spec_1", "mock_trait_3")]
    assert m4["visibility_status"] == "schema_missing_view_metadata"
    assert m4["review_recommendation"] == "schema_review_needed"

    # 5. Check kb_subset_coverage.json
    coverage_json_path = Path(synthetic_kb_and_selection["output_dir"]) / "kb_subset_coverage.json"
    assert coverage_json_path.exists()

    with open(coverage_json_path, "r", encoding="utf-8") as f:
        coverage = json.load(f)

    assert coverage["represented_kb_taxa"] == ["mock_taxon_a"]
    assert coverage["unrepresented_kb_taxa"] == ["mock_taxon_b"]
    assert coverage["represented_traits_used"] == ["mock_trait_1"]
    assert "mock_taxon_b" in coverage["taxa_with_insufficient_specimens"]
    assert "rule_1" in coverage["represented_rules_exercised"]
    assert "rule_2" in coverage["unrepresented_rules"]


def test_cli_subcommand(synthetic_kb_and_selection, capsys, monkeypatch):
    """Tests the CLI registration and execution of audit-trait-visibility."""
    # Build CLI command arguments
    cli_args = [
        "cli.py", "audit-trait-visibility",
        "--kb-dir", synthetic_kb_and_selection["kb_dir"],
        "--selection-csv", synthetic_kb_and_selection["selection_csv"],
        "--annotation-template", synthetic_kb_and_selection["template_jsonl"],
        "--image-root", synthetic_kb_and_selection["image_root"],
        "--output-dir", synthetic_kb_and_selection["output_dir"]
    ]

    monkeypatch.setattr("sys.argv", cli_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0

    captured = capsys.readouterr()
    stdout_json = json.loads(captured.out)
    assert stdout_json["status"] == "success"
    assert stdout_json["selected_specimens"] == 2
