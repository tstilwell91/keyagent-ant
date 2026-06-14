"""Taxonomic Knowledge Base (KB) validation and reasoning package.

This package provides a deterministic validation and reasoning harness for KeyAgent-Ant's
taxonomic keys and trait schemas.
"""

from .kb_loader import load_kb
from .key_reasoner import reason_over_traits, KeyReasoner
from .evidence_schema import VisualCandidate, ModelEvidenceInput, ReasoningEvidencePacket
from .reasoning_adapter import build_reasoning_evidence_packet
from .prediction_artifact_adapter import (
    prediction_row_to_model_output,
    load_predictions_csv,
    convert_predictions_csv_to_model_outputs,
)
from .key_consistency_evaluator import (
    load_observed_traits_sidecar,
    evaluate_predictions_csv_with_kb,
)
from .trait_sidecar_tools import (
    validate_observed_traits_sidecar,
    summarize_trait_sidecar_coverage,
    generate_trait_annotation_template,
)

__all__ = [
    "load_kb",
    "reason_over_traits",
    "KeyReasoner",
    "VisualCandidate",
    "ModelEvidenceInput",
    "ReasoningEvidencePacket",
    "build_reasoning_evidence_packet",
    "prediction_row_to_model_output",
    "load_predictions_csv",
    "convert_predictions_csv_to_model_outputs",
    "load_observed_traits_sidecar",
    "evaluate_predictions_csv_with_kb",
    "validate_observed_traits_sidecar",
    "summarize_trait_sidecar_coverage",
    "generate_trait_annotation_template",
]
