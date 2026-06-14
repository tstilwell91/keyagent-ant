"""Taxonomic Knowledge Base (KB) validation and reasoning package.

This package provides a deterministic validation and reasoning harness for KeyAgent-Ant's
taxonomic keys and trait schemas.
"""

from .kb_loader import load_kb
from .key_reasoner import reason_over_traits, KeyReasoner
from .evidence_schema import VisualCandidate, ModelEvidenceInput, ReasoningEvidencePacket
from .reasoning_adapter import build_reasoning_evidence_packet

__all__ = [
    "load_kb",
    "reason_over_traits",
    "KeyReasoner",
    "VisualCandidate",
    "ModelEvidenceInput",
    "ReasoningEvidencePacket",
    "build_reasoning_evidence_packet",
]
