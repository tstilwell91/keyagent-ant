import os
import pytest
from pathlib import Path

from antid.data.audit_antweb_csv import run_audit, write_report


@pytest.fixture
def synthetic_csv(tmp_path) -> Path:
    """
    Creates a synthetic, small semicolon-delimited AntWeb CSV file.
    """
    csv_path = tmp_path / "synthetic_antweb.csv"
    
    # 8 rows total
    # Camponotus pennsylvanicus has 3 rows with full d, h, p coverage
    # Formica rufa has 2 rows with d, h (partial)
    # Solenopsis invicta has 1 row with p (partial)
    # 1 malformed scientific name row (should be ignored or handled)
    # 1 row with missing image_url
    content = (
        "catalog_number;scientific_name;shot_type;image_url;state;caste;caste_big;source\n"
        "casent1;Camponotus pennsylvanicus;d;http://x.org/1.jpg;Ohio;w;worker;antweb\n"
        "casent1;Camponotus pennsylvanicus;h;http://x.org/2.jpg;Ohio;w;worker;antweb\n"
        "casent1;Camponotus pennsylvanicus;p;http://x.org/3.jpg;Ohio;w;worker;antweb\n"
        "casent2;Formica rufa;d;http://x.org/4.jpg;Maine;dQ;queen;antweb\n"
        "casent2;Formica rufa;h;http://x.org/5.jpg;Maine;dQ;queen;antweb\n"
        "casent3;Solenopsis invicta;p;http://x.org/6.jpg;Texas;w;worker;antweb\n"
        "casent4;MalformedNameOnly;d;http://x.org/7.jpg;Florida;w;worker;antweb\n"
        "casent5;Aphaenogaster tennesseensis;d;;Florida;w;worker;antweb\n"
    )
    
    csv_path.write_text(content, encoding="utf-8")
    return csv_path


def test_run_audit_metrics(synthetic_csv):
    metrics = run_audit(str(synthetic_csv))
    
    # 8 rows total in CSV file
    assert metrics["total_rows"] == 8
    
    # Unique parsed species: camponotus_pennsylvanicus, formica_rufa, solenopsis_invicta
    assert metrics["unique_species"] == 3
    assert metrics["unique_genera"] == 3
    
    # Missing / Malformed
    assert metrics["missing_url"] == 1
    assert metrics["missing_sci_name"] == 1  # MalformedNameOnly fails parse

    # Distributions
    assert metrics["shot_type_counts"]["d"] == 3
    assert metrics["shot_type_counts"]["h"] == 2
    assert metrics["shot_type_counts"]["p"] == 2

    # Coverage metrics
    assert metrics["full_coverage_count"] == 1  # Camponotus pennsylvanicus has d, h, p
    assert metrics["partial_coverage_count"] == 2  # Formica rufa, Solenopsis invicta
    assert metrics["missing_coverage_count"] == 0


def test_write_report_creation(synthetic_csv, tmp_path):
    metrics = run_audit(str(synthetic_csv))
    report_path = tmp_path / "dataset_audit_report.md"
    
    write_report(metrics, str(report_path))
    
    assert report_path.exists()
    report_text = report_path.read_text(encoding="utf-8")
    
    # Check that report contains standard sections and values
    assert "# KeyAgent-Ant: Legacy Dataset Audit Report" in report_text
    assert "## Executive Summary" in report_text
    assert "- **Total Rows / Image Entries:** 8" in report_text
    assert "- **Unique Genera:** 3" in report_text
    assert "- **Unique Binomial Species:** 3" in report_text
    assert "camponotus_pennsylvanicus" in report_text
    assert "formica_rufa" in report_text
    assert "solenopsis_invicta" in report_text
